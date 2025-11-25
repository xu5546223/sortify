"""
統一對話上下文管理器

核心職責:
1. 會話狀態管理: 追蹤整個對話的狀態和進度
2. 文檔池管理: 管理本次對話引用的所有文檔
3. 上下文載入: 統一的載入接口，自動選擇合適的格式
4. 上下文構建: 為不同階段構建專門優化的上下文
5. 緩存管理: 統一的 Redis + MongoDB 緩存策略

設計原則:
- 單一責任: 只負責上下文管理，不涉及業務邏輯
- 統一接口: 對外提供統一的 API，隱藏內部複雜性
- 格式適配: 根據使用場景自動提供最優格式
- 會話感知: 理解對話的連續性和文檔引用關係
"""

import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, UTC
from uuid import UUID
from enum import Enum
from dataclasses import dataclass, field
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.models.context_config import context_config

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class ContextPurpose(str, Enum):
    """上下文使用目的"""
    CLASSIFICATION = "classification"        # 意圖分類
    ANSWER_GENERATION = "answer_generation"  # 答案生成
    SEARCH_RETRIEVAL = "search_retrieval"    # 文檔檢索
    CLARIFICATION = "clarification"          # 澄清問題生成


@dataclass
class DocumentRef:
    """
    文檔引用 - 會話文檔池中的文檔記錄
    
    注意: 這個結構會序列化到 MongoDB 的 cached_document_data 字段中
    只保存摘要級別的信息，不保存完整文檔內容
    """
    document_id: str
    filename: str
    
    # 摘要信息 (層次1 - 約500 tokens)
    summary: Optional[str] = None           # 100-200字摘要
    key_concepts: List[str] = field(default_factory=list)  # 關鍵概念
    semantic_tags: List[str] = field(default_factory=list)  # 語義標籤
    
    # 會話級元數據
    first_mentioned_round: int = 1          # 首次提及的輪次
    last_accessed_round: int = 1            # 最後訪問的輪次
    relevance_score: float = 0.8            # 相關性評分 (0-1)
    access_count: int = 1                   # 訪問次數
    topic: Optional[str] = None             # 主題標籤
    
    def decay_relevance(self, current_round: int, decay_rate: float = 0.1):
        """隨時間衰減相關性"""
        rounds_passed = current_round - self.last_accessed_round
        self.relevance_score = max(0.3, self.relevance_score - (rounds_passed * decay_rate))
    
    def boost_relevance(self, boost: float = 0.1):
        """提升相關性（當再次被訪問時）"""
        self.relevance_score = min(1.0, self.relevance_score + boost)
        self.access_count += 1
    
    def boost_citation(self, citation_boost: float = 0.2):
        """提升相關性（當 AI 生成答案時引用了此文檔）"""
        self.relevance_score = min(1.0, self.relevance_score + citation_boost)
        logger.info(f"📌 文檔被引用，相關性提升: {self.filename} -> {self.relevance_score:.2f}")
    
    def to_dict(self) -> dict:
        """轉換為字典格式，用於序列化到 MongoDB"""
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "summary": self.summary,
            "key_concepts": self.key_concepts,
            "semantic_tags": self.semantic_tags,
            "first_mentioned_round": self.first_mentioned_round,
            "last_accessed_round": self.last_accessed_round,
            "relevance_score": self.relevance_score,
            "access_count": self.access_count,
            "topic": self.topic
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DocumentRef':
        """從字典創建 DocumentRef 實例"""
        return cls(
            document_id=data.get("document_id", ""),
            filename=data.get("filename", ""),
            summary=data.get("summary"),
            key_concepts=data.get("key_concepts", []),
            semantic_tags=data.get("semantic_tags", []),
            first_mentioned_round=data.get("first_mentioned_round", 1),
            last_accessed_round=data.get("last_accessed_round", 1),
            relevance_score=data.get("relevance_score", 0.8),
            access_count=data.get("access_count", 1),
            topic=data.get("topic")
        )


@dataclass
class Message:
    """標準化的消息結構"""
    role: str  # "user" | "assistant"
    content: str
    round_number: int
    created_at: datetime
    tokens_used: Optional[int] = None
    source_documents: Optional[List[str]] = None  # 本輪回答引用的文檔
    
    def to_dict(self) -> dict:
        """轉換為字典格式"""
        return {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def to_formatted_text(self, max_length: Optional[int] = None) -> str:
        """轉換為格式化文本"""
        role_name = "用戶" if self.role == "user" else "助手"
        content = self.content
        if max_length and len(content) > max_length:
            content = content[:max_length] + "..."
        return f"{role_name}: {content}"


@dataclass
class ContextBundle:
    """
    上下文包 - 根據不同目的打包的上下文數據
    
    這是統一接口返回的標準格式，不同目的會填充不同的字段
    """
    purpose: ContextPurpose
    
    # 對話歷史 (不同格式)
    conversation_history_list: Optional[List[Dict]] = None      # 列表格式
    conversation_history_text: Optional[str] = None             # 文本格式
    
    # 文檔池信息
    document_pool: Optional[Dict[str, DocumentRef]] = None      # 完整文檔池
    cached_documents_info: Optional[List[Dict]] = None          # 文檔摘要列表
    priority_document_ids: Optional[List[str]] = None           # 優先檢索文檔ID
    
    # 會話狀態
    current_round: Optional[int] = None
    message_count: Optional[int] = None
    session_state: Optional[Dict] = None
    
    # 檢索建議
    should_reuse_cached: bool = False
    search_expansion_needed: bool = True


class ConversationContextManager:
    """
    統一對話上下文管理器
    
    示例用法:
    
    # 創建管理器
    manager = ConversationContextManager(
        db=db,
        conversation_id="uuid",
        user_id="uuid"
    )
    
    # 為意圖分類載入上下文
    context = await manager.load_context(
        purpose=ContextPurpose.CLASSIFICATION
    )
    # 返回: conversation_history_list + cached_documents_info
    
    # 為答案生成載入上下文
    context = await manager.load_context(
        purpose=ContextPurpose.ANSWER_GENERATION,
        current_documents=retrieved_documents
    )
    # 返回: 格式化文本，明確分離歷史和當前文檔
    
    # 保存問答對
    await manager.add_qa_pair(
        question="早餐收據",
        answer="根據文檔...",
        source_documents=["doc_id_1"]
    )
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str,
        user_id: str,
        enable_caching: bool = True
    ):
        """
        初始化上下文管理器
        
        Args:
            db: MongoDB 連接
            conversation_id: 對話ID
            user_id: 用戶ID
            enable_caching: 是否啟用 Redis 緩存
        """
        self.db = db
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.enable_caching = enable_caching
        
        # 會話狀態
        self.conversation_uuid = UUID(conversation_id)
        self.user_uuid = UUID(user_id)
        self.current_round = 0
        
        # 內存緩存
        self._message_cache: Optional[List[Message]] = None
        self._document_pool: Optional[Dict[str, DocumentRef]] = None
        self._cache_loaded = False
        
        logger.debug(f"創建上下文管理器: conversation={conversation_id}, user={user_id}")
    
    async def load_context(
        self,
        purpose: ContextPurpose,
        current_documents: Optional[List[Any]] = None,
        max_history_messages: int = 10
    ) -> ContextBundle:
        """
        統一的上下文載入接口
        
        根據不同的使用目的，自動構建最優的上下文格式
        
        Args:
            purpose: 上下文使用目的
            current_documents: 當前檢索到的文檔 (僅 ANSWER_GENERATION 需要)
            max_history_messages: 最大歷史消息數
            
        Returns:
            ContextBundle: 上下文包
        """
        # 確保緩存已載入
        await self._ensure_cache_loaded()
        
        bundle = ContextBundle(purpose=purpose)
        bundle.current_round = self.current_round
        bundle.message_count = len(self._message_cache) if self._message_cache else 0
        
        if purpose == ContextPurpose.CLASSIFICATION:
            return await self._build_classification_context(bundle, max_history_messages)
        
        elif purpose == ContextPurpose.ANSWER_GENERATION:
            return await self._build_answer_generation_context(
                bundle, current_documents, max_history_messages
            )
        
        elif purpose == ContextPurpose.SEARCH_RETRIEVAL:
            return await self._build_search_context(bundle)
        
        elif purpose == ContextPurpose.CLARIFICATION:
            return await self._build_clarification_context(bundle, max_history_messages)
        
        return bundle
    
    async def add_qa_pair(
        self,
        question: str,
        answer: str,
        source_documents: Optional[List[str]] = None,
        tokens_used: int = 0
    ) -> bool:
        """
        保存問答對到對話，並更新文檔池
        
        Args:
            question: 用戶問題
            answer: AI回答
            source_documents: 引用的文檔ID列表
            tokens_used: 使用的token數
            
        Returns:
            bool: 是否保存成功
        """
        try:
            from app.crud import crud_conversations
            
            self.current_round += 1
            
            # 添加用戶問題
            await crud_conversations.add_message_to_conversation(
                db=self.db,
                conversation_id=self.conversation_uuid,
                user_id=self.user_uuid,
                role="user",
                content=question,
                tokens_used=None
            )
            
            # 添加AI回答
            await crud_conversations.add_message_to_conversation(
                db=self.db,
                conversation_id=self.conversation_uuid,
                user_id=self.user_uuid,
                role="assistant",
                content=answer,
                tokens_used=tokens_used
            )
            
            # ⚠️ 先確保文檔池已載入
            await self._ensure_cache_loaded()
            
            # 🔄 對所有未被引用的文檔進行相關性衰減
            if self._document_pool:
                source_doc_set = set(source_documents or [])
                decay_rate = context_config.RELEVANCE_DECAY_RATE
                
                for doc_id, doc_ref in self._document_pool.items():
                    if doc_id not in source_doc_set:
                        # 未被引用的文檔，進行衰減
                        old_score = doc_ref.relevance_score
                        doc_ref.decay_relevance(self.current_round, decay_rate)
                        if old_score != doc_ref.relevance_score:
                            logger.debug(
                                f"📉 文檔相關性衰減: {doc_ref.filename} "
                                f"{old_score:.2f} → {doc_ref.relevance_score:.2f}"
                            )
            
            # 更新文檔池（添加新文檔）
            if source_documents and len(source_documents) > 0:
                logger.debug(f"更新前文檔池: {len(self._document_pool)} 個文檔")
                await self._update_document_pool(source_documents)
                logger.debug(f"更新後文檔池: {len(self._document_pool)} 個文檔")
                
                # 🏷️ 強制添加引用標註（如果 AI 沒有標註）
                # 傳入 source_documents 以保持與 AI 看到的順序一致
                answer = self.enforce_citations(answer, source_document_ids=source_documents)
                
                # 📈 檢測答案中的引用並給相應文檔加分（使用文檔名匹配）
                await self.boost_cited_documents(answer)
            
            # 🗑️ 清理低相關性文檔
            await self.cleanup_low_relevance_docs()
            
            # 保存文檔池到 cached_document_data
            if self._document_pool:
                await self._save_document_pool_to_db()
                
                # 更新 cached_documents (文檔ID列表)
                all_doc_ids = list(self._document_pool.keys())
                await crud_conversations.update_cached_documents(
                    db=self.db,
                    conversation_id=self.conversation_uuid,
                    user_id=self.user_uuid,
                    document_ids=all_doc_ids,
                    document_data=None  # cached_document_data 已在上面保存
                )
            
            # ⚠️ 不要清除緩存！這樣下次保存時才能保留歷史文檔
            # await self._invalidate_cache()  # 移除這行！
            
            logger.info(f"✅ 保存問答對成功: round={self.current_round}, docs={len(source_documents or [])}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存問答對失敗: {e}", exc_info=True)
            return False
    
    async def cleanup_low_relevance_docs(
        self,
        min_score: float = None,
        max_idle_rounds: int = None
    ):
        """
        清理低相關性文檔
        
        Args:
            min_score: 最低分數閾值（低於此分數的文檔會被清理）
            max_idle_rounds: 最大閒置輪次（超過此輪次未訪問的低分文檔會被清理）
        """
        # 使用統一配置的默認值
        if min_score is None:
            min_score = context_config.MIN_RELEVANCE_SCORE
        if max_idle_rounds is None:
            max_idle_rounds = context_config.MAX_IDLE_ROUNDS
        
        if not self._document_pool:
            return
        
        to_remove = []
        current_round = self.current_round
        
        for doc_id, doc_ref in self._document_pool.items():
            idle_rounds = current_round - doc_ref.last_accessed_round
            
            # 清理條件：分數低於閾值 且 長期未訪問
            if doc_ref.relevance_score <= min_score and idle_rounds >= max_idle_rounds:
                to_remove.append((doc_id, doc_ref))
                logger.info(
                    f"🗑️ 標記清理文檔: {doc_ref.filename} "
                    f"(score: {doc_ref.relevance_score:.2f}, idle: {idle_rounds} 輪)"
                )
        
        # 執行清理
        if to_remove:
            for doc_id, doc_ref in to_remove:
                del self._document_pool[doc_id]
            
            logger.info(f"✅ 已清理 {len(to_remove)} 個低相關性文檔")
            
            # 保存更新後的文檔池
            await self._save_document_pool_to_db()
        else:
            logger.debug("✓ 無需清理文檔")
    
    async def get_retrieval_priority_docs(
        self,
        top_k: int = 5,
        min_relevance: float = 0.5
    ) -> List[str]:
        """
        獲取檢索優先文檔ID列表
        
        根據相關性評分返回最相關的文檔
        
        Args:
            top_k: 返回前K個文檔
            min_relevance: 最低相關性閾值
            
        Returns:
            List[str]: 文檔ID列表，按相關性排序
        """
        await self._ensure_cache_loaded()
        
        if not self._document_pool:
            return []
        
        # 先對所有文檔進行相關性衰減
        for doc_ref in self._document_pool.values():
            doc_ref.decay_relevance(self.current_round)
        
        # 自動清理低相關性文檔（每次檢索時觸發，使用統一配置）
        await self.cleanup_low_relevance_docs()
        
        # 按相關性排序
        sorted_docs = sorted(
            self._document_pool.values(),
            key=lambda x: (x.relevance_score, x.access_count),
            reverse=True
        )
        
        # 過濾並返回高相關性文檔
        priority_docs = [
            doc.document_id
            for doc in sorted_docs
            if doc.relevance_score >= min_relevance
        ][:top_k]
        
        logger.info(f"🎯 優先檢索文檔: {len(priority_docs)} 個 (閾值: {min_relevance})")
        return priority_docs
    
    async def should_reuse_cached_docs(
        self,
        query: str,
        similarity_threshold: float = 0.7
    ) -> bool:
        """
        判斷是否應該重用緩存文檔
        
        基於查詢相似度和文檔池狀態判斷
        
        Args:
            query: 當前查詢
            similarity_threshold: 相似度閾值
            
        Returns:
            bool: 是否應該重用緩存
        """
        await self._ensure_cache_loaded()
        
        # 如果文檔池為空，不重用
        if not self._document_pool:
            return False
        
        # 如果最近一輪有文檔引用，傾向於重用
        if self._message_cache and len(self._message_cache) > 0:
            last_msg = self._message_cache[-1]
            if last_msg.role == "assistant" and last_msg.source_documents:
                logger.info("📎 最近一輪有文檔引用，建議重用緩存")
                return True
        
        # TODO: 實現基於語義相似度的判斷
        # 這裡可以調用 embedding 服務比較查詢與文檔主題的相似度
        
        return False
    
    # ========== 私有方法 ==========
    
    async def _ensure_cache_loaded(self):
        """確保緩存已載入"""
        if self._cache_loaded:
            return
        
        await self._load_messages()
        await self._load_document_pool()
        self._cache_loaded = True
    
    async def _load_messages(self):
        """從數據庫載入消息"""
        try:
            from app.crud import crud_conversations
            
            messages = await crud_conversations.get_recent_messages(
                db=self.db,
                conversation_id=self.conversation_uuid,
                user_id=self.user_uuid,
                limit=50  # 載入更多消息用於分析
            )
            
            if messages:
                self._message_cache = [
                    Message(
                        role=msg.role,
                        content=msg.content,
                        round_number=(i + 1) // 2 + 1,  # 每兩條消息為一輪
                        created_at=msg.timestamp,  # ConversationMessage 使用 timestamp，不是 created_at
                        tokens_used=getattr(msg, 'tokens_used', None),
                        source_documents=getattr(msg, 'source_documents', None)
                    )
                    for i, msg in enumerate(messages)
                ]
                self.current_round = max(m.round_number for m in self._message_cache)
                logger.debug(f"載入了 {len(self._message_cache)} 條消息，當前輪次: {self.current_round}")
            else:
                self._message_cache = []
                self.current_round = 0
                
        except Exception as e:
            logger.error(f"載入消息失敗: {e}", exc_info=True)
            self._message_cache = []
    
    def enforce_citations(self, answer_text: str, source_document_ids: Optional[List[str]] = None) -> str:
        """
        強制添加引用標註（如果 AI 沒有標註）
        
        改進版：使用文檔 ID 作為引用標識，避免順序不一致問題
        
        Args:
            answer_text: AI 生成的答案文本
            source_document_ids: 本輪使用的文檔 ID 列表（按順序，與 AI 看到的順序一致）
            
        Returns:
            str: 添加引用標註後的答案文本
        """
        if not answer_text or not self._document_pool:
            logger.debug(f"跳過引用強制：answer_text={bool(answer_text)}, pool={bool(self._document_pool)}")
            return answer_text
        
        logger.info(f"📝 開始強制引用標註，文檔池大小: {len(self._document_pool)}")
        logger.debug(f"答案內容（前 200 字符）: {answer_text[:200]}")
        
        # 如果提供了 source_document_ids，使用它來建立編號映射
        # 否則使用文檔池中的順序（按相關性排序）
        if source_document_ids:
            # 使用與 AI 看到的相同順序
            filename_to_citation: Dict[str, int] = {}
            for idx, doc_id in enumerate(source_document_ids, 1):
                if doc_id in self._document_pool:
                    doc = self._document_pool[doc_id]
                    filename_to_citation[doc.filename] = idx
                    logger.debug(f"  文檔 {idx}: {doc.filename} (from source_documents)")
        else:
            # Fallback: 按相關性排序
            sorted_docs = sorted(
                self._document_pool.values(),
                key=lambda x: x.relevance_score,
                reverse=True
            )
            filename_to_citation = {}
            for idx, doc in enumerate(sorted_docs, 1):
                filename_to_citation[doc.filename] = idx
                logger.debug(f"  文檔 {idx}: {doc.filename} (score: {doc.relevance_score:.2f})")
        
        modified_text = answer_text
        added_count = 0
        
        # 按文件名長度降序排序（優先匹配長文件名，避免部分匹配）
        sorted_filenames = sorted(filename_to_citation.keys(), key=len, reverse=True)
        
        for filename in sorted_filenames:
            citation_num = filename_to_citation[filename]
            
            # 跳過已經有任何引用格式的（不限定編號）
            already_cited_pattern = rf'\[([^\]]*{re.escape(filename)}[^\]]*)\]\(citation:\d+\)'
            if re.search(already_cited_pattern, modified_text):
                logger.debug(f"文檔 {filename} 已有引用標註，跳過")
                continue
            
            # 查找未標註的文檔名提及
            # 匹配：文檔名（但不在 Markdown 鏈接中）
            # 使用負向前瞻和負向後顧避免匹配已經在鏈接中的文檔名
            pattern = rf'(?<!\]\()(?<!\[)({re.escape(filename)})(?!\]\(citation:)'
            
            def replace_with_citation(match):
                nonlocal added_count
                text = match.group(1)
                added_count += 1
                logger.info(f"  ✅ 為 '{text}' 添加引用 citation:{citation_num}")
                return f"[{text}](citation:{citation_num})"
            
            # 只替換第一次出現（避免過度標註）
            modified_text = re.sub(pattern, replace_with_citation, modified_text, count=1)
        
        if added_count > 0:
            logger.info(f"🔗 自動添加了 {added_count} 個引用標註")
        else:
            logger.warning("⚠️ 未添加任何引用標註（可能 AI 已經標註了，或文檔名未出現在答案中）")
        
        return modified_text
    
    async def boost_cited_documents(self, answer_text: str):
        """
        檢測答案中的引用並給相應文檔加分
        
        改進版：通過文檔名匹配而不是編號匹配，避免順序不一致問題
        
        Args:
            answer_text: AI 生成的答案文本
        """
        if not answer_text or not self._document_pool:
            logger.debug(f"跳過引用加分：answer_text={bool(answer_text)}, pool={bool(self._document_pool)}")
            return
        
        logger.info(f"🔍 開始檢測引用，文檔池大小: {len(self._document_pool)}")
        logger.debug(f"答案內容（前 200 字符）: {answer_text[:200]}")
        
        # 使用正則表達式匹配 [文本](citation:數字) 格式
        # 提取引用中的文本（通常包含文檔名）
        citation_pattern = r'\[([^\]]+)\]\(citation:(\d+)\)'
        matches = re.findall(citation_pattern, answer_text)
        
        if not matches:
            logger.warning("⚠️ 答案中未發現任何引用標註 [xxx](citation:N)")
            return
        
        # 提取引用中的文本（可能是文檔名或包含文檔名）
        cited_texts = [match[0] for match in matches]
        logger.info(f"📌 檢測到 {len(cited_texts)} 個引用文本: {cited_texts}")
        
        # 通過文檔名匹配（而不是編號）
        boosted_count = 0
        boosted_docs = set()  # 避免重複加分
        
        for cited_text in cited_texts:
            # 在文檔池中查找匹配的文檔
            for doc_id, doc in self._document_pool.items():
                if doc_id in boosted_docs:
                    continue
                    
                # 檢查文檔名是否出現在引用文本中
                if doc.filename in cited_text or cited_text in doc.filename:
                    doc.boost_citation(citation_boost=0.2)
                    boosted_docs.add(doc_id)
                    boosted_count += 1
                    logger.info(f"  ✅ 文檔 '{doc.filename}' 被引用，相關性提升")
                    break
        
        if boosted_count > 0:
            logger.info(f"✅ 已給 {boosted_count} 個被引用文檔加分")
            # 保存更新後的文檔池
            await self._save_document_pool_to_db()
        else:
            logger.warning("⚠️ 未能匹配任何文檔（引用文本可能不包含文檔名）")
    
    async def _load_document_pool(self):
        """
        從數據庫載入文檔池
        
        優先從 cached_document_data 載入（已包含摘要），
        如果不存在則從文檔庫查詢並構建
        """
        try:
            from app.crud import crud_conversations
            from app.crud.crud_documents import get_documents_by_ids
            
            # 先嘗試從 cached_document_data 載入
            cached_doc_ids, cached_doc_data = await crud_conversations.get_cached_documents(
                db=self.db,
                conversation_id=self.conversation_uuid,
                user_id=self.user_uuid
            )
            
            if not cached_doc_ids:
                self._document_pool = {}
                return
            
            self._document_pool = {}
            
            # 如果有 cached_document_data，檢查是否需要修復
            if cached_doc_data and isinstance(cached_doc_data, dict):
                logger.debug(f"從數據庫讀取到 cached_document_data: {len(cached_doc_data)} 個文檔")
                
                # 檢查是否有 "unknown" 文件名（舊數據）
                has_unknown = any(
                    doc_data.get('filename') == 'unknown' 
                    for doc_data in cached_doc_data.values() 
                    if isinstance(doc_data, dict)
                )
                
                if has_unknown:
                    # 有舊數據，需要重新查詢修復
                    logger.info(f"檢測到舊的文檔池數據（包含 unknown），重新查詢修復...")
                else:
                    # 數據完整，直接使用
                    logger.debug(f"開始從 cached_document_data 載入文檔池，總共 {len(cached_doc_data)} 個文檔")
                    for doc_id, doc_data in cached_doc_data.items():
                        if isinstance(doc_data, dict):
                            try:
                                self._document_pool[doc_id] = DocumentRef.from_dict(doc_data)
                            except Exception as e:
                                logger.warning(f"⚠️ 載入文檔 {doc_id} 失敗: {e}")
                        else:
                            logger.warning(f"⚠️ 文檔 {doc_id} 的數據格式錯誤: {type(doc_data)}")
                    
                    logger.debug(f"從 cached_document_data 載入了文檔池: {len(self._document_pool)} 個文檔（原始數據 {len(cached_doc_data)} 個）")
                    return
            
            # 如果沒有 cached_document_data，從文檔庫查詢並構建
            logger.info("cached_document_data 為空，從文檔庫構建文檔池")
            documents = await get_documents_by_ids(self.db, cached_doc_ids)
            
            for idx, doc in enumerate(documents, 1):
                doc_id = str(doc.id)
                
                # 提取摘要和關鍵信息
                summary = ""
                key_concepts = []
                semantic_tags = []
                
                try:
                    # 從 enriched_data 獲取
                    if hasattr(doc, 'enriched_data') and isinstance(doc.enriched_data, dict):
                        summary = doc.enriched_data.get('summary', '')
                        key_concepts = doc.enriched_data.get('key_concepts', [])
                        semantic_tags = doc.enriched_data.get('semantic_tags', [])
                    
                    # 從 analysis 獲取（備用）
                    if not summary and hasattr(doc, 'analysis') and doc.analysis:
                        if hasattr(doc.analysis, 'ai_analysis_output'):
                            ai_output = doc.analysis.ai_analysis_output
                            if isinstance(ai_output, dict):
                                key_info = ai_output.get('key_information', {})
                                if isinstance(key_info, dict):
                                    summary = key_info.get('content_summary', '')
                                    key_concepts = key_info.get('key_concepts', [])
                                    semantic_tags = key_info.get('semantic_tags', [])
                except Exception as e:
                    logger.warning(f"提取文檔 {doc_id} 信息失敗: {e}")
                
                # 創建文檔引用（只保存摘要級別）
                self._document_pool[doc_id] = DocumentRef(
                    document_id=doc_id,
                    filename=doc.filename,
                    summary=summary[:200] if summary else None,  # 限制摘要長度
                    key_concepts=key_concepts[:10] if key_concepts else [],  # 最多10個概念
                    semantic_tags=semantic_tags[:5] if semantic_tags else [],  # 最多5個標籤
                    first_mentioned_round=1,
                    last_accessed_round=self.current_round,
                    relevance_score=0.8,
                )
            
            # 保存到 cached_document_data（下次直接用）
            await self._save_document_pool_to_db()
            
            logger.debug(f"構建並保存了文檔池: {len(self._document_pool)} 個文檔")
            
        except Exception as e:
            logger.error(f"載入文檔池失敗: {e}", exc_info=True)
            self._document_pool = {}
    
    async def _update_document_pool(self, new_document_ids: List[str]):
        """更新文檔池，添加新文檔或更新現有文檔"""
        # 確保文檔池已初始化
        if self._document_pool is None:
            self._document_pool = {}
        
        # 批量查詢新文檔信息（優化性能）
        new_doc_ids = [doc_id for doc_id in new_document_ids if doc_id not in self._document_pool]
        
        if new_doc_ids:
            try:
                from app.crud.crud_documents import get_documents_by_ids
                new_documents = await get_documents_by_ids(self.db, new_doc_ids)
                
                # 建立 doc_id -> document 的映射
                doc_map = {str(doc.id): doc for doc in new_documents}
            except Exception as e:
                logger.warning(f"批量查詢新文檔失敗: {e}")
                doc_map = {}
        else:
            doc_map = {}
        
        for doc_id in new_document_ids:
            if doc_id in self._document_pool:
                # 已存在，提升相關性
                self._document_pool[doc_id].boost_relevance()
                self._document_pool[doc_id].last_accessed_round = self.current_round
            else:
                # 新文檔，從查詢結果中獲取信息
                doc = doc_map.get(doc_id)
                if doc:
                    # 成功獲取文檔信息，提取 summary 和關鍵信息
                    summary = ""
                    key_concepts = []
                    semantic_tags = []
                    
                    try:
                        # 從 enriched_data 獲取
                        if hasattr(doc, 'enriched_data') and isinstance(doc.enriched_data, dict):
                            summary = doc.enriched_data.get('summary', '')
                            key_concepts = doc.enriched_data.get('key_concepts', [])
                            semantic_tags = doc.enriched_data.get('semantic_tags', [])
                        
                        # 從 analysis 獲取（備用）
                        if not summary and hasattr(doc, 'analysis') and doc.analysis:
                            if hasattr(doc.analysis, 'ai_analysis_output'):
                                ai_output = doc.analysis.ai_analysis_output
                                if isinstance(ai_output, dict):
                                    key_info = ai_output.get('key_information', {})
                                    if isinstance(key_info, dict):
                                        summary = key_info.get('content_summary', '')
                                        key_concepts = key_info.get('key_concepts', [])
                                        semantic_tags = key_info.get('semantic_tags', [])
                    except Exception as e:
                        logger.warning(f"提取文檔 {doc_id} 信息失敗: {e}")
                    
                    self._document_pool[doc_id] = DocumentRef(
                        document_id=doc_id,
                        filename=doc.filename,
                        summary=summary[:200] if summary else None,  # 限制摘要長度
                        key_concepts=key_concepts[:10] if key_concepts else [],  # 最多10個概念
                        semantic_tags=semantic_tags[:5] if semantic_tags else [],  # 最多5個標籤
                        first_mentioned_round=self.current_round,
                        last_accessed_round=self.current_round,
                        relevance_score=1.0  # 新提及的文檔相關性最高
                    )
                else:
                    # 查詢失敗，使用占位符
                    logger.warning(f"文檔 {doc_id} 不存在，使用占位符")
                    self._document_pool[doc_id] = DocumentRef(
                        document_id=doc_id,
                        filename=f"Document_{doc_id[:8]}",
                        first_mentioned_round=self.current_round,
                        last_accessed_round=self.current_round,
                        relevance_score=1.0
                    )
        
        # 檢查並裁剪文檔池大小
        max_pool_size = context_config.MAX_DOCUMENT_POOL_SIZE
        if len(self._document_pool) > max_pool_size:
            await self._trim_document_pool(max_pool_size)
    
    async def _trim_document_pool(self, max_size: int):
        """
        裁剪文檔池到指定大小
        
        按照 (相關性 * 0.7 + 時效性 * 0.3) 的優先級排序，
        保留優先級最高的文檔，移除其餘的。
        
        Args:
            max_size: 文檔池最大大小
        """
        if len(self._document_pool) <= max_size:
            return
        
        # 計算每個文檔的優先級分數
        def compute_priority(doc_ref: DocumentRef) -> float:
            # 時效性：最近訪問的文檔分數更高
            idle_rounds = self.current_round - doc_ref.last_accessed_round
            recency_score = 1 / (idle_rounds + 1)  # 避免除以零
            
            # 綜合分數：相關性權重 0.7，時效性權重 0.3
            return doc_ref.relevance_score * 0.7 + recency_score * 0.3
        
        # 按優先級排序
        sorted_docs = sorted(
            self._document_pool.items(),
            key=lambda x: compute_priority(x[1]),
            reverse=True
        )
        
        # 計算需要移除的文檔
        to_remove = sorted_docs[max_size:]
        
        logger.info(
            f"🗑️ 文檔池已滿 ({len(self._document_pool)}/{max_size})，"
            f"移除 {len(to_remove)} 個低優先級文檔"
        )
        
        # 執行移除
        for doc_id, doc_ref in to_remove:
            logger.debug(
                f"  移除: {doc_ref.filename} "
                f"(score: {doc_ref.relevance_score:.2f}, "
                f"idle: {self.current_round - doc_ref.last_accessed_round} 輪)"
            )
            del self._document_pool[doc_id]
        
        logger.info(f"✅ 文檔池裁剪完成，當前大小: {len(self._document_pool)}")
    
    async def _save_document_pool_to_db(self):
        """
        保存文檔池到 MongoDB 的 cached_document_data 字段
        只在文檔池更新時調用
        """
        try:
            if not self._document_pool:
                return
            
            # 轉換為字典格式
            cached_doc_data = {
                doc_id: doc_ref.to_dict()
                for doc_id, doc_ref in self._document_pool.items()
            }
            
            logger.debug(f"準備保存文檔池: {len(self._document_pool)} 個文檔, 文檔ID: {list(self._document_pool.keys())[:3]}...")
            
            # 更新到數據庫
            from app.crud import crud_conversations
            
            # ✅ 同时更新 cached_documents 数组和 cached_document_data
            doc_ids = list(self._document_pool.keys())
            result = await self.db.conversations.update_one(
                {
                    "_id": self.conversation_uuid,
                    "user_id": self.user_uuid
                },
                {
                    "$set": {
                        "cached_documents": doc_ids,  # ✅ 更新文档ID数组
                        "cached_document_data": cached_doc_data,
                        "updated_at": datetime.now(UTC)
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.debug(f"✅ 已保存文檔池到數據庫: {len(self._document_pool)} 個文檔")
            else:
                logger.warning(f"⚠️ 文檔池保存未修改數據庫（可能數據相同）")
            
        except Exception as e:
            logger.warning(f"保存文檔池失敗: {e}")
    
    async def _invalidate_cache(self):
        """清除緩存"""
        self._cache_loaded = False
        self._message_cache = None
        self._document_pool = {}  # 設置為空字典而不是 None
        
        # 清除 Redis 緩存
        if self.enable_caching:
            try:
                from app.services.cache import unified_cache, CacheNamespace
                cache_key = f"{self.user_uuid}:{self.conversation_uuid}"
                await unified_cache.delete(key=cache_key, namespace=CacheNamespace.CONVERSATION)
            except Exception as e:
                logger.warning(f"清除 Redis 緩存失敗: {e}")
    
    async def _build_classification_context(
        self,
        bundle: ContextBundle,
        max_messages: int
    ) -> ContextBundle:
        """構建用於意圖分類的上下文"""
        # 列表格式的歷史
        if self._message_cache:
            bundle.conversation_history_list = [
                msg.to_dict()
                for msg in self._message_cache[-max_messages:]
            ]
        
        # 文檔摘要列表（按相關性排序）
        # ⚠️ 重要：reference_number 必須與 AI 生成答案時看到的順序一致
        # 這樣用戶說「第一個文件」時，AI 才能正確理解
        if self._document_pool:
            # 按相關性排序文檔（這個順序會傳給 AI）
            sorted_docs = sorted(
                self._document_pool.values(),
                key=lambda x: x.relevance_score,
                reverse=True
            )
            
            # ⭐ 關鍵：保存排序後的文檔順序，供後續引用解析使用
            # reference_number 從 1 開始，與 citation:1, citation:2 對應
            bundle.cached_documents_info = [
                {
                    "document_id": doc.document_id,
                    "filename": doc.filename,
                    "reference_number": idx,  # ⭐ 這個編號與 citation:N 對應
                    "summary": doc.summary or "",
                    "relevance_score": doc.relevance_score,
                    "access_count": doc.access_count,
                    "key_concepts": doc.key_concepts[:5] if doc.key_concepts else [],
                    "semantic_tags": doc.semantic_tags[:3] if doc.semantic_tags else []
                }
                for idx, doc in enumerate(sorted_docs, 1)
            ]
            
            # ⭐ 同時保存文檔順序映射，供後續使用
            # 這確保了 reference_number -> document_id 的映射是穩定的
            logger.debug(f"📋 文檔池順序（用於引用）: {[(d['reference_number'], d['filename']) for d in bundle.cached_documents_info[:5]]}")
        
        return bundle
    
    async def _build_answer_generation_context(
        self,
        bundle: ContextBundle,
        current_documents: Optional[List[Any]],
        max_messages: int
    ) -> ContextBundle:
        """構建用於答案生成的上下文（明確分離歷史和當前文檔）"""
        # 格式化對話歷史
        if self._message_cache:
            history_lines = [
                msg.to_formatted_text(max_length=800)
                for msg in self._message_cache[-max_messages:]
            ]
            bundle.conversation_history_text = "\n".join(history_lines)
        
        # 文檔池引用（僅供參考）
        if self._document_pool:
            bundle.document_pool = self._document_pool
        
        return bundle
    
    async def _build_search_context(
        self,
        bundle: ContextBundle
    ) -> ContextBundle:
        """構建用於文檔檢索的上下文"""
        # 優先文檔ID
        bundle.priority_document_ids = await self.get_retrieval_priority_docs()
        
        # 檢索建議
        bundle.should_reuse_cached = len(bundle.priority_document_ids) > 0
        bundle.search_expansion_needed = len(bundle.priority_document_ids) < 3
        
        return bundle
    
    async def _build_clarification_context(
        self,
        bundle: ContextBundle,
        max_messages: int
    ) -> ContextBundle:
        """構建用於澄清問題生成的上下文"""
        # 保留完整對話歷史（不截斷）
        if self._message_cache:
            history_lines = [
                msg.to_formatted_text(max_length=None)  # 不截斷
                for msg in self._message_cache[-max_messages:]
            ]
            bundle.conversation_history_text = "\n".join(history_lines)
        
        # 文檔池信息
        if self._document_pool:
            bundle.cached_documents_info = [
                {
                    "document_id": doc.document_id,
                    "filename": doc.filename,
                    "summary": doc.summary or ""
                }
                for doc in self._document_pool.values()
            ]
        
        return bundle


# 全局工廠函數
async def create_context_manager(
    db: AsyncIOMotorDatabase,
    conversation_id: str,
    user_id: str
) -> ConversationContextManager:
    """
    創建上下文管理器的工廠函數
    
    Args:
        db: MongoDB 連接
        conversation_id: 對話ID
        user_id: 用戶ID
        
    Returns:
        ConversationContextManager: 上下文管理器實例
    """
    return ConversationContextManager(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
        enable_caching=True
    )
