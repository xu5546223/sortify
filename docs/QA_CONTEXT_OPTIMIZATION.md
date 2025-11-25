# AI QA 上下文管理系統優化建議

> 評估日期：2025-11-25
> 評估範圍：上下文管理、歷史對話、文檔池管理

---

## 一、當前架構概覽

### 三層上下文管理

| 層級 | 組件 | 存儲位置 | 生命週期 |
|------|------|----------|----------|
| **歷史對話** | `messages[]` | MongoDB | 永久保存 |
| **文檔池** | `cached_document_data` | MongoDB | 對話級別 |
| **當前搜索結果** | chunk 內容 | 內存 | 單輪使用 |

### 核心組件

```
ConversationContextManager     # 統一上下文管理器
├── load_context()             # 根據目的載入上下文
├── add_qa_pair()              # 保存問答對
├── cleanup_low_relevance_docs() # 清理低分文檔 ✅ 已實現
└── get_retrieval_priority_docs() # 獲取優先文檔

ContextLoaderService           # 上下文載入服務
UnifiedContextHelper           # 統一上下文輔助工具
```

---

## 二、已實現的優秀設計 ✅

### 1. 漸進式披露策略
```
文檔池(摘要) → AI識別需要哪個文檔 → 按需查詢詳細內容
```
避免每輪都傳送大量文檔內容給 LLM。

### 2. 文檔池元數據豐富
```python
cached_document_data = {
    "doc_id": {
        "filename": str,
        "summary": str,           # 100-200字摘要
        "relevance_score": float,
        "access_count": int,
        "first_mentioned_round": int,
        "last_accessed_round": int,
        "key_concepts": [str],
        "semantic_tags": [str]
    }
}
```

### 3. 相關性衰減與清理機制
```python
# 已實現：低於 0.35 分 且 5 輪未訪問 → 自動清理
await self.cleanup_low_relevance_docs(
    min_score=0.35,
    max_idle_rounds=5
)
```

### 4. 多層緩存策略
- Redis：快速讀取最近消息
- MongoDB：持久化存儲 + 文檔池
- 內存：`_message_cache`, `_document_pool`

---

## 三、優化建議

### 🔴 高優先級

#### 1. 歷史對話長度控制 ✅ 已完成

**問題**：`messages[]` 會無限累積，長對話導致 MongoDB 文檔過大。

**已實現方案** (`app/crud/crud_conversations.py`)：

```python
# 歷史對話長度限制
MAX_MESSAGES_PER_CONVERSATION = 100  # 最大保留消息數

async def add_message_to_conversation(...) -> bool:
    """添加消息到對話（帶長度控制）"""
    # ... 添加消息邏輯 ...
    
    if result.modified_count > 0:
        # 檢查並清理超出長度限制的舊消息
        await _trim_conversation_messages(db, conversation_id, user_id)
        return True

async def _trim_conversation_messages(db, conversation_id, user_id) -> None:
    """裁剪對話消息，保持在長度限制內"""
    conversation = await db.conversations.find_one(
        {"_id": conversation_id, "user_id": user_id},
        {"message_count": 1}
    )
    
    message_count = conversation.get("message_count", 0)
    if message_count <= MAX_MESSAGES_PER_CONVERSATION:
        return
    
    # 移除最舊的消息
    messages_to_remove = message_count - MAX_MESSAGES_PER_CONVERSATION
    for _ in range(messages_to_remove):
        await db.conversations.update_one(
            {"_id": conversation_id, "user_id": user_id},
            {"$pop": {"messages": -1}}  # -1 移除第一條（最舊的）
        )
    
    # 更新 message_count
    await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"message_count": MAX_MESSAGES_PER_CONVERSATION}}
    )
```

---

#### 2. 統一截斷配置 ✅ 已完成

**問題**：不同地方使用不同的截斷長度，不一致。

**已實現方案** (`app/models/context_config.py`)：

```python
from pydantic_settings import BaseSettings

class ContextConfig(BaseSettings):
    """上下文管理配置"""
    
    # ==================== 歷史對話配置 ====================
    MAX_MESSAGES_PER_CONVERSATION: int = 20      # 最大保留消息數
    DEFAULT_HISTORY_LIMIT: int = 5               # 默認載入歷史消息數
    CLASSIFICATION_HISTORY_LIMIT: int = 10       # 意圖分類時載入的歷史消息數
    
    # ==================== 內容截斷配置 ====================
    CLASSIFICATION_CONTENT_MAX_LENGTH: int = 500    # 意圖分類時
    ANSWER_GEN_CONTENT_MAX_LENGTH: int = 2000       # 生成答案時
    CLARIFICATION_CONTENT_MAX_LENGTH: int = 1500    # 澄清問題時
    PREVIEW_MAX_LENGTH: int = 200                   # 列表預覽/摘要
    USER_QUESTION_MAX_LENGTH: int = 300             # 用戶問題（分類時）
    AI_ANSWER_MAX_LENGTH: int = 800                 # AI 回答（分類時）
    AI_ANSWER_WITH_CITATION_MAX_LENGTH: int = 600   # AI 回答（含引用）
    
    # ==================== 文檔池配置 ====================
    MAX_DOCUMENT_POOL_SIZE: int = 20
    MIN_RELEVANCE_SCORE: float = 0.35
    MAX_IDLE_ROUNDS: int = 5
    RELEVANCE_DECAY_RATE: float = 0.1
    
    class Config:
        env_prefix = "CONTEXT_"  # 環境變量前綴

context_config = ContextConfig()
```

**已更新的文件**：
- `crud_conversations.py` - 使用 `MAX_MESSAGES_PER_CONVERSATION`
- `unified_context_helper.py` - 使用 `DEFAULT_HISTORY_LIMIT`, `ANSWER_GEN_CONTENT_MAX_LENGTH`
- `context_loader_service.py` - 使用 `PREVIEW_MAX_LENGTH`
- `question_classifier_service.py` - 使用多個截斷配置
- `conversation_context_manager.py` - 使用文檔池配置
- 所有 intent handlers - 移除硬編碼參數，使用統一配置默認值

---

### 🟡 中優先級

#### 3. 文檔池大小上限 ✅ 已完成

**問題**：文檔池只有低分清理，沒有總量上限。

**已實現方案** (`conversation_context_manager.py`)：

```python
async def _update_document_pool(self, new_document_ids: List[str]):
    """更新文檔池（帶大小限制）"""
    # ... 原有添加邏輯 ...
    
    # 檢查並裁剪文檔池大小
    max_pool_size = context_config.MAX_DOCUMENT_POOL_SIZE  # 默認 20
    if len(self._document_pool) > max_pool_size:
        await self._trim_document_pool(max_pool_size)

async def _trim_document_pool(self, max_size: int):
    """裁剪文檔池到指定大小"""
    # 計算優先級：相關性 * 0.7 + 時效性 * 0.3
    def compute_priority(doc_ref: DocumentRef) -> float:
        idle_rounds = self.current_round - doc_ref.last_accessed_round
        recency_score = 1 / (idle_rounds + 1)
        return doc_ref.relevance_score * 0.7 + recency_score * 0.3
    
    # 按優先級排序，保留前 max_size 個
    sorted_docs = sorted(
        self._document_pool.items(),
        key=lambda x: compute_priority(x[1]),
        reverse=True
    )
    
    to_remove = sorted_docs[max_size:]
    for doc_id, doc_ref in to_remove:
        del self._document_pool[doc_id]
```

**配置項** (`models/context_config.py`)：
- `MAX_DOCUMENT_POOL_SIZE: int = 20`

---

#### 4. 移除已廢棄的緩存引用 ✅ 已完成

**問題**：`conversation_cache_service` 已移除但代碼中仍有引用。

**已實現方案**：

移除 `context_loader_service.py` 中對 `conversation_cache_service` 的調用，
直接使用 MongoDB 查詢（對話數據 Redis 加速效果有限）：

```python
async def _load_from_cache(self, db, conversation_uuid, user_uuid):
    """
    從緩存載入對話上下文
    
    注意：conversation_cache_service 已廢棄，
    現在直接使用 MongoDB 查詢
    """
    # 直接返回 None，讓調用方使用 _load_from_database
    return None, [], None
```

---

### 🟢 低優先級

#### 5. 添加上下文使用統計

**目的**：監控上下文管理效果，便於調優。

```python
# conversation_context_manager.py

class ContextStats:
    """上下文使用統計"""
    total_loads: int = 0
    cache_hits: int = 0
    documents_cleaned: int = 0
    avg_pool_size: float = 0.0
    avg_history_length: float = 0.0

async def get_context_stats(self) -> ContextStats:
    """獲取上下文統計信息"""
    return ContextStats(
        total_loads=self._stats_total_loads,
        cache_hits=self._stats_cache_hits,
        documents_cleaned=self._stats_docs_cleaned,
        avg_pool_size=len(self._document_pool),
        avg_history_length=len(self._message_cache) if self._message_cache else 0
    )
```

---

#### 6. 測試腳本增強

**建議**：在 `test_qa_stream_flow.py` 中添加邊界測試：

```python
async def test_long_conversation():
    """測試長對話（50+ 輪）的上下文管理"""
    pass

async def test_document_pool_overflow():
    """測試文檔池滿載（20+ 文檔）時的清理"""
    pass

async def test_topic_switch():
    """測試跨主題切換時的上下文處理"""
    pass

async def test_relevance_decay():
    """測試相關性衰減機制"""
    # 模擬多輪對話，驗證文檔分數是否正確衰減
    pass
```

---

## 四、實施優先級

| 優先級 | 項目 | 狀態 | 影響範圍 |
|--------|------|------|----------|
| 🔴 高 | 歷史對話長度控制 | ✅ 已完成 | crud_conversations.py |
| 🔴 高 | 統一截斷配置 | ✅ 已完成 | 新增 models/context_config.py + 多個文件 |
| 🟡 中 | 文檔池大小上限 | ✅ 已完成 | conversation_context_manager.py |
| 🟡 中 | 移除廢棄緩存引用 | ✅ 已完成 | context_loader_service.py |
| 🟢 低 | 上下文統計 | ⏳ 待實施 | conversation_context_manager.py |
| 🟢 低 | 測試腳本增強 | ⏳ 待實施 | test_qa_stream_flow.py |

---

## 五、主流工具上下文管理機制調研

> 調研日期：2025-11-25
> 調研對象：Cursor、Windsurf、Claude、ChatGPT、Gemini

---

### 1. Cursor IDE

**架構特點**：
| 組件 | 實現方式 |
|------|----------|
| **代碼上下文** | `@file` / `@folder` 語法，將完整文件內容注入 `<attached-files>` 區塊 |
| **語義搜索** | 向量數據庫索引整個代碼庫，查詢時用 LLM 重排序過濾 |
| **長期記憶** | `.cursorrules` 文件，作為 System Prompt 的一部分 |
| **對話歷史** | 建議保持對話簡短，避免長上下文污染 |

**關鍵設計**：
```
用戶 @file → 完整文件內容注入 → LLM 處理
語義查詢 → 向量搜索 → LLM 重排序 → 返回最相關文件
```

**最佳實踐**：
- 文件保持 < 500 行，避免 apply-model 出錯
- 文件頂部添加語義註釋，幫助 embedding 模型理解
- 使用唯一文件名，減少歧義

---

### 2. Windsurf (Cascade)

**架構特點**：
| 組件 | 實現方式 |
|------|----------|
| **自動記憶** | Cascade 自動識別並存儲有用上下文，綁定到 workspace |
| **用戶記憶** | 用戶可手動創建 `create memory ...` |
| **Rules** | 本地/全局規則文件，指導 AI 行為 |
| **記憶隔離** | 自動記憶僅在原始 workspace 內可用 |

**關鍵設計**：
```
自動記憶：Cascade 主動識別 → 存儲到 workspace → 跨 session 保留
用戶記憶：用戶指令 → 手動存儲 → 更精確控制
```

**特色**：
- 自動記憶不消耗 credits
- Workspace 隔離確保上下文相關性
- Rules 支持本地和全局兩級

---

### 3. Claude (Anthropic)

**架構特點**：
| 組件 | 實現方式 |
|------|----------|
| **Memory 文件** | `CLAUDE.md` Markdown 文件，層級結構 |
| **載入方式** | **全量載入**到 Context Window（非 RAG） |
| **層級結構** | Enterprise → Project → User（級聯覆蓋） |
| **管理命令** | `/memory` 編輯、`#` 快速添加、`@path/to/import` 模組化 |

**關鍵設計**：
```
CLAUDE.md 文件 → 啟動時全量載入到 Context → 200K token 窗口內搜索
                 ↓
         與 RAG 的區別：不做語義檢索，依賴大 Context Window
```

**已知問題 - "Fading Memory"**：
- 當 `CLAUDE.md` 過大時，模型難以定位相關信息
- 信號被噪音淹沒
- 官方建議：保持 Memory 精簡，大文檔用 `@docs/` 按需引用

**最佳實踐**：
- 保持 `CLAUDE.md` 精簡，只放每次都需要的信息
- 項目文檔放 `docs/` 目錄，用 `@docs/filename.md` 按需引用
- 使用 `/clear` 重置上下文、`/compact` 壓縮對話

---

### 4. ChatGPT (OpenAI)

**架構特點**：
| 組件 | 實現方式 |
|------|----------|
| **Model Set Context** | `bio` 工具存儲的記憶，帶時間戳 |
| **Assistant Response Preferences** | 系統自動學習的用戶偏好（帶 Confidence 標籤） |
| **Notable Past Conversation Topics** | 過去對話主題摘要 |
| **Recent Conversation Content** | 最近對話內容 |
| **User Interaction Metadata** | 用戶互動元數據 |

**關鍵設計**：
```
System Prompt 結構：
├── Model Set Context (用戶可管理的記憶)
│   └── "1. [2025-05-02]. The user likes ice cream..."
├── Assistant Response Preferences (系統學習，帶 Confidence)
│   └── "User prefers structured formatting... Confidence=high"
├── Notable Past Conversation Topics
├── Recent Conversation Content
└── User Interaction Metadata
```

**特色**：
- 雙層記憶：用戶可控 + 系統自動學習
- Confidence 標籤用於推理時權重調整
- 用戶無法直接查看/修改系統學習的偏好

---

### 5. Google Gemini

**架構特點**：
| 組件 | 實現方式 |
|------|----------|
| **隱式緩存** | 自動啟用，相同前綴請求自動命中緩存 |
| **顯式緩存** | 手動創建緩存，設置 TTL（默認 1 小時） |
| **緩存策略** | 大內容放前面，短時間內發送相似請求 |

**關鍵設計**：
```
隱式緩存：相同 prefix → 自動緩存命中 → 降低成本
顯式緩存：create_cache(content, ttl) → 後續請求引用 cache_id
```

**適用場景**：
- 大量 System Instructions 的 Chatbot
- 重複分析長視頻/大文檔
- 頻繁查詢代碼庫

**最低 Token 要求**：
| 模型 | 最低 Token |
|------|-----------|
| Gemini 2.5 Pro | 1,024 |
| Gemini 2.5 Flash | 1,024 |

---

### 6. 對比總結

| 工具 | 記憶存儲 | 載入方式 | 清理機制 | 特色 |
|------|----------|----------|----------|------|
| **Cursor** | `.cursorrules` + 向量庫 | 按需檢索 | 無自動清理 | 語義搜索 + LLM 重排序 |
| **Windsurf** | Workspace 記憶 | 自動載入 | Workspace 隔離 | 自動 + 手動記憶 |
| **Claude** | `CLAUDE.md` 文件 | **全量載入** | 用戶手動管理 | 層級結構、透明可控 |
| **ChatGPT** | System Prompt 區塊 | 全量注入 | 系統自動學習 | 雙層記憶、Confidence |
| **Gemini** | Context Cache | TTL 過期 | 自動過期 | 隱式 + 顯式緩存 |
| **Sortify** | MongoDB + Redis | 按需載入 | **相關性衰減** | 文檔池 + 漸進式披露 |

---

### 7. 對 Sortify 的啟發

#### ✅ 你已經做得比主流工具更好的地方：

1. **相關性衰減機制** - Claude/ChatGPT 都沒有自動衰減
2. **文檔池元數據** - 比 Cursor 的純向量搜索更豐富
3. **漸進式披露** - 類似 Claude 的 `@docs/` 按需引用

#### 🔧 可以借鑒的設計：

| 來源 | 可借鑒點 | 對應優化 |
|------|----------|----------|
| **Claude** | Memory 文件分層（Enterprise → Project → User） | 可考慮用戶級 + 對話級配置分離 |
| **ChatGPT** | Confidence 標籤 | 文檔池可加入 `confidence` 欄位 |
| **Gemini** | TTL 過期機制 | 文檔池可加入絕對過期時間 |
| **Windsurf** | Workspace 隔離 | 已有對話級隔離，可考慮項目級 |
| **Cursor** | 文件大小建議 < 500 行 | 可在文檔分析時提示用戶 |

#### 🚀 進階優化方向：

```python
# 借鑒 ChatGPT 的 Confidence 機制
class DocumentRef:
    relevance_score: float = 0.8
    confidence: str = "high"  # 新增：high/medium/low
    
    def should_include_in_context(self) -> bool:
        """根據 confidence 決定是否包含在上下文中"""
        if self.confidence == "high":
            return self.relevance_score >= 0.3
        elif self.confidence == "medium":
            return self.relevance_score >= 0.5
        else:
            return self.relevance_score >= 0.7

# 借鑒 Gemini 的 TTL 機制
class DocumentRef:
    created_at: datetime
    ttl_hours: int = 24  # 新增：絕對過期時間
    
    def is_expired(self) -> bool:
        return datetime.now() - self.created_at > timedelta(hours=self.ttl_hours)
```

---

## 六、總結

當前系統的核心設計是**合理且完善**的：
- ✅ 三層上下文分離清晰
- ✅ 漸進式披露策略正確
- ✅ 相關性衰減與清理已實現
- ✅ 文檔池元數據豐富

**與主流工具對比**：
- 比 Claude 更智能（有自動衰減，Claude 需手動管理）
- 比 ChatGPT 更透明（用戶可見文檔池，ChatGPT 偏好不可見）
- 比 Cursor 更精細（有元數據，Cursor 只有向量）

主要需要補充的是**防護性機制**：
- 歷史對話長度上限
- 文檔池大小上限
- 統一配置管理

這些優化可以在不改變核心架構的情況下逐步實施。
