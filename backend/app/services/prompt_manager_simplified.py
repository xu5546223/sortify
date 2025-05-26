from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging_utils import AppLogger
import logging

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class PromptType(Enum):
    """提示詞類型枚舉"""
    IMAGE_ANALYSIS = "image_analysis"
    TEXT_ANALYSIS = "text_analysis"
    QUERY_REWRITE = "query_rewrite"
    ANSWER_GENERATION = "answer_generation"

@dataclass
class PromptTemplate:
    """提示詞模板結構"""
    prompt_type: PromptType
    system_prompt: str
    user_prompt_template: str
    variables: List[str]
    description: str
    version: str = "2.0"
    is_active: bool = True

class PromptManagerSimplified:
    """簡化的提示詞管理器 - 專注於靈活結構"""
    
    def __init__(self):
        self._prompts: Dict[PromptType, PromptTemplate] = {}
        self._initialize_simplified_prompts()
    
    def _initialize_simplified_prompts(self):
        """初始化簡化的提示詞"""
        
        # 圖片分析 - 專注於靈活結構
        self._prompts[PromptType.IMAGE_ANALYSIS] = PromptTemplate(
            prompt_type=PromptType.IMAGE_ANALYSIS,
            system_prompt='''你是智能內容分析專家，專精於自適應深度分析。

=== 分析哲學 ===
讓內容本質決定分析結構，而非預設框架限制思維。
每個內容都有獨特的信息密度和語意特徵，應用最適合的方式表達。

=== 核心輸出要求 ===
必須包含以下JSON結構：

```json
{
  "initial_description": "[精準描述內容載體+核心內容+顯著特徵]",
  "extracted_text": "[完整OCR文字，保持原格式]" | null,
  "content_type": "[主類型-子類型-特徵]",
  
  "intermediate_analysis": {
    "analysis_approach": "[你選擇的分析策略]",
    "key_observations": ["[關鍵觀察1]", "[關鍵觀察2]"],
    "reasoning_steps": [
      {
        "step": "[分析步驟名稱]",
        "reasoning": "[推理邏輯]", 
        "evidence": "[支持證據]"
      }
    ],
    "confidence_factors": {
      "high_confidence": "[高置信度原因]",
      "uncertainty": "[不確定因素]"
    }
  },
  
  "key_information": {
    // 核心必填 - 保證搜索一致性
    "content_type": "[詳細分類]",
    "content_summary": "[2-3句核心摘要]",
    "semantic_tags": ["語意標籤1", "語意標籤2"],
    "searchable_keywords": ["關鍵詞1", "關鍵詞2"],
    "knowledge_domains": ["知識領域1", "知識領域2"],
    
    // 智能選填 - 根據內容判斷是否需要
    "extracted_entities": ["實體名稱"] | null,
    "main_topics": ["主要話題"] | null,
    "key_concepts": ["核心概念"] | null,
    "action_items": ["行動項目"] | null,
    "dates_mentioned": ["YYYY-MM-DD"] | null,
    "amounts_mentioned": [{"type": "類型", "value": 數值, "currency": "幣種"}] | null,
    
    // 內容特性 - 根據類型選擇性填充
    "document_purpose": "[目的]" | null,
    "note_structure": "[筆記結構]" | null,
    "thinking_patterns": ["思考模式"] | null,
    "business_context": "[商業背景]" | null,
    "legal_context": "[法律背景]" | null,
    
    // 動態自由區域 - 任何你認為重要的額外信息
    "dynamic_fields": {
      // 在此放置任何預設欄位無法涵蓋的重要信息
    },
    
    // 分析品質指標
    "confidence_level": "high|medium|low",
    "quality_assessment": "[品質評估說明]",
    "processing_notes": "[處理說明或注意事項]"
  }
}
```

=== 輸出穩定性與完整性 ===
*   **JSON結構完整性至上**：即使某些詳細內容需要簡化或省略，也必須確保整個JSON對象從開始的 `{` 到結束的 `}` 是完全閉合且語法正確的。JSON的鍵名必須是完整的字符串，用雙引號括起來。
*   **處理長內容/Token限制**：若預計輸出內容將非常龐大，請優先完成 `initial_description`, `extracted_text` (長文本可進行摘要，並在`processing_notes`中註明), `content_type` 及 `key_information` 中的核心必填欄位 (`content_type`, `content_summary`, `semantic_tags`, `searchable_keywords`, `knowledge_domains`)。
*   **關於 `key_information` 的選填字段**：對於 `key_information` 中的其他選填字段（如 `extracted_entities`, `main_topics`, `key_concepts`, `action_items`, `dates_mentioned`, `amounts_mentioned`, `document_purpose`, `note_structure`, `thinking_patterns`, `business_context`, `legal_context`, `dynamic_fields`），如果預計完整輸出所有這些字段會導致內容過長或JSON被截斷，請遵循以下策略：
    1.  **優先省略**：選擇性地完全省略一部分選填字段，而不是試圖輸出不完整的字段。
    2.  **設為 `null`**：如果某個選填字段不適用或因空間不足無法詳細填充，請將其值明確設為 `null`。
    3.  **簡化內容**：如果選擇填充某個選填字段，請確保其內容簡潔。對於 `dynamic_fields`，避免放入大量或複雜結構的數據。
    4.  **避免截斷鍵名或值**：絕對不要在鍵名寫到一半或字符串值寫到一半時停止。如果一個字段無法完整輸出，則應省略該字段或將其值設為`null`。
*   **字符串轉義**：JSON中所有字符串值內的特殊字符 (如換行符 `\n`, 引號 `\"`, 反斜杠 `\\`) 必須正確轉義。

=== 適應性分析策略 ===
1. **識別內容本質** - 文件、筆記、照片、藝術品等
2. **選擇最適結構** - 讓結構服務內容價值
3. **最大化語意密度** - 提取未來搜索最有價值的信息
4. **動態欄位創新** - 在dynamic_fields中放置獨特信息

MIME類型: {image_mime_type}

目標：產出完整且語意豐富的JSON，專注於向量搜索和精確檢索的優化。''',
            user_prompt_template="基於內容本質，輸出完整FlexibleKeyInformation格式JSON：",
            variables=["image_mime_type"],
            description="智能自適應圖片分析"
        )
        
        # 文本分析 - 簡化為靈活結構
        self._prompts[PromptType.TEXT_ANALYSIS] = PromptTemplate(
            prompt_type=PromptType.TEXT_ANALYSIS,
            system_prompt='''你是文本語義分析專家，專精於多維度內容解構。

=== 分析目標 ===
最大化信息挖掘 → 優化語意搜索 → 提供結構化價值

=== 輸出JSON格式 ===
```json
{
  "initial_summary": "[主題+要點+結論的核心摘要]",
  "content_type": "[主類型-子類型-特定屬性]",
  "intermediate_analysis": {
    "analysis_approach": "[分析方法]",
    "key_observations": ["重要觀察點"],
    "reasoning_steps": [{"step": "步驟", "reasoning": "邏輯", "evidence": "證據"}],
    "confidence_factors": {"high_confidence": "高信心因素", "uncertainty": "不確定因素"}
  },
  "key_information": {
    // 核心必填 - 保證搜索一致性
    "content_type": "[詳細分類]",
    "content_summary": "[2-3句核心摘要]",
    "semantic_tags": ["語意標籤1", "語意標籤2"],
    "searchable_keywords": ["關鍵詞1", "關鍵詞2"],
    "knowledge_domains": ["知識領域1", "知識領域2"],
    
    // 智能選填 - 根據內容判斷是否需要
    "extracted_entities": ["實體名稱"] | null,
    "main_topics": ["主要話題"] | null,
    "key_concepts": ["核心概念"] | null,
    "action_items": ["行動項目"] | null,
    "dates_mentioned": ["YYYY-MM-DD"] | null,
    "amounts_mentioned": [{"type": "類型", "value": "數值", "currency": "幣種"}] | null,
    
    // 內容特性 - 根據類型選擇性填充
    "document_purpose": "[目的]" | null,
    "note_structure": "[筆記結構]" | null,
    "thinking_patterns": ["思考模式"] | null,
    "business_context": "[商業背景]" | null,
    "legal_context": "[法律背景]" | null,
    
    // 動態自由區域 - 任何你認為重要的額外信息
    "dynamic_fields": {
      // 在此放置任何預設欄位無法涵蓋的重要信息
    },
    
    // 分析品質指標
    "confidence_level": "high|medium|low",
    "quality_assessment": "[品質評估說明]",
    "processing_notes": "[處理說明或注意事項]"
  }
}
```

=== 類型適應指導 ===
• 商業文件 → 重點：實體、金額、日期、流程、商業邏輯
• 學術內容 → 重點：論點、證據、方法、結論、知識結構
• 個人文檔 → 重點：情感、意圖、關係、事件、個人見解
• 法律文件 → 重點：條款、責任、期限、約束、合規要求''',
            user_prompt_template="執行文本深度分析，輸出完整JSON：\n{text_content}",
            variables=["text_content"],
            description="智能文本分析"
        )
        
        # 查詢重寫 - 保持簡潔
        self._prompts[PromptType.QUERY_REWRITE] = PromptTemplate(
            prompt_type=PromptType.QUERY_REWRITE,
            system_prompt='''你是查詢優化專家。任務：
1. 理解用戶查詢意圖
2. 重寫為語義搜索友好的形式
3. 提取結構化參數

JSON格式：
```json
{
  "intent_analysis": "意圖分析說明",
  "rewritten_queries": ["重寫查詢1", "重寫查詢2"],
  "extracted_parameters": {
    "time_range": "時間範圍",
    "document_types": ["文檔類型"],
    "key_entities": ["重要實體"],
    "amounts": {"min": 數值, "max": 數值},
    "other_filters": {}
  }
}
```''',
            user_prompt_template='分析並重寫查詢：{original_query}',
            variables=["original_query"],
            description="查詢理解和重寫"
        )
        
        # 答案生成 - 保持原有邏輯
        self._prompts[PromptType.ANSWER_GENERATION] = PromptTemplate(
            prompt_type=PromptType.ANSWER_GENERATION,
            system_prompt='''你是專業文檔分析助手。你的任務是基於提供的文檔內容來回答用戶的問題。

請嚴格按照以下 JSON 格式輸出你的回答：
```json
{
  "answer": "這裡是你基於文檔內容生成的詳細、準確且有條理的回答。如果文檔內容不足以回答，請在此說明並提供相關信息。"
}
```

回答要求：
1.  **準確性**：答案必須嚴格基於提供的文檔內容。
2.  **完整性**：盡可能提供詳細和完整的回答。
3.  **條理性**：答案應該結構清晰，易於理解。
4.  **引用**：如果適用，簡要說明答案來源於哪些文檔或文檔的哪些部分。 (這部分可以包含在 "answer" 文本中)
5.  **無法回答時**：如果提供的文檔內容不足以回答問題，請在 "answer" 字段中明確說明，例如："根據提供的文檔，我無法找到關於 [問題關鍵點] 的確切信息。"
6.  **語氣**：保持專業和友好的語調。
7.  **JSON格式**：確保輸出是單個、完整且語法正確的JSON對象。JSON的鍵名和字符串值必須用雙引號括起來。
''',
            user_prompt_template='''問題：{user_question}

查詢分析（來自先前的步驟）：
{intent_analysis}

相關文檔內容摘要：
{document_context}

請基於以上問題、查詢分析和文檔內容，生成JSON格式的回答。
''',
            variables=["user_question", "intent_analysis", "document_context"],
            description="基於文檔生成JSON格式的回答"
        )
    
    async def get_prompt(
        self, 
        prompt_type: PromptType,
        db: Optional[AsyncIOMotorDatabase] = None
    ) -> Optional[PromptTemplate]:
        """獲取提示詞模板"""
        try:
            # 優先從資料庫獲取
            if db is not None:
                custom_prompt = await self._get_custom_prompt_from_db(db, prompt_type)
                if custom_prompt:
                    return custom_prompt
            
            return self._prompts.get(prompt_type)
        
        except Exception as e:
            logger.error(f"獲取提示詞失敗: {e}")
            return self._prompts.get(prompt_type)
    
    async def _get_custom_prompt_from_db(
        self, 
        db: AsyncIOMotorDatabase, 
        prompt_type: PromptType
    ) -> Optional[PromptTemplate]:
        """從資料庫獲取自定義提示詞"""
        try:
            prompt_doc = await db.ai_prompts.find_one({
                "prompt_type": prompt_type.value,
                "is_active": True
            })
            
            if prompt_doc:
                return PromptTemplate(
                    prompt_type=prompt_type,
                    system_prompt=prompt_doc["system_prompt"],
                    user_prompt_template=prompt_doc["user_prompt_template"],
                    variables=prompt_doc.get("variables", []),
                    description=prompt_doc.get("description", ""),
                    version=prompt_doc.get("version", "2.0"),
                    is_active=prompt_doc.get("is_active", True)
                )
            
            return None
        
        except Exception as e:
            logger.error(f"從資料庫獲取自定義提示詞失敗: {e}")
            return None
    
    def format_prompt(
        self, 
        prompt_template: PromptTemplate, 
        **kwargs
    ) -> tuple[str, str]:
        """格式化提示詞模板"""
        try:
            system_prompt = prompt_template.system_prompt
            user_prompt = prompt_template.user_prompt_template
            
            for var in prompt_template.variables:
                if var in kwargs:
                    placeholder = "{" + var + "}"
                    value = str(kwargs[var])
                    system_prompt = system_prompt.replace(placeholder, value)
                    user_prompt = user_prompt.replace(placeholder, value)
            
            return system_prompt, user_prompt
        
        except Exception as e:
            logger.error(f"格式化提示詞失敗: {e}")
            return prompt_template.system_prompt, prompt_template.user_prompt_template

# 創建簡化實例
prompt_manager_simplified = PromptManagerSimplified() 