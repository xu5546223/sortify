from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from app.services.unified_ai_config import TaskType

class TokenUsage(BaseModel):
    prompt_tokens: int = Field(..., description="輸入提示詞所使用的 Token 數量")
    completion_tokens: int = Field(..., description="模型生成回應所使用的 Token 數量")
    total_tokens: int = Field(..., description="總共使用的 Token 數量")

class AIPromptRequest(BaseModel):
    user_prompt: str = Field(..., description="使用者的提示詞", max_length=100000)
    system_prompt: Optional[str] = Field(None, description="系統級別的提示詞 (可選)")
    model: Optional[str] = Field(None, description="要使用的 AI 模型 (可選，若不指定則會依序查找DB設定或全局預設)")

class AIResponse(BaseModel):
    answer: str = Field(..., description="AI 模型生成的回應內容")
    token_usage: TokenUsage = Field(..., description="本次呼叫的 Token 使用資訊")
    model_used: str = Field(..., description="實際使用的 AI 模型")

# === 核心通用結構 ===

class BaseKeyInformation(BaseModel):
    """關鍵訊息的基礎類別，包含通用的分析相關欄位"""
    confidence_level: Optional[str] = Field(None, description="分析置信度 (high|medium|low)")
    quality_assessment: Optional[str] = Field(None, description="內容品質評估")
    processing_notes: Optional[str] = Field(None, description="特殊處理說明或注意事項")

# === 靈活智能結構（主要使用） ===

class FlexibleIntermediateAnalysis(BaseModel):
    """靈活的中間分析結構，讓AI自己決定分析步驟"""
    analysis_approach: str = Field(..., description="AI選擇的分析方法")
    key_observations: List[str] = Field(default_factory=list, description="關鍵觀察點")
    reasoning_steps: List[Dict[str, str]] = Field(default_factory=list, description="推理步驟，格式：[{'step': '步驟', 'reasoning': '理由', 'evidence': '證據'}]")
    confidence_factors: Dict[str, str] = Field(default_factory=dict, description="置信度影響因素")

class FlexibleKeyInformation(BaseKeyInformation):
    """靈活的關鍵信息結構，讓AI自己決定要填充的欄位"""
    # 核心必填欄位（保證一致性）
    content_type: str = Field(..., description="內容類型分類")
    content_summary: str = Field(..., description="內容摘要 (2-3句話)")
    
    # 語意搜索優化欄位（重要性較高）
    semantic_tags: List[str] = Field(default_factory=list, description="語意標籤，適合向量搜索")
    searchable_keywords: List[str] = Field(default_factory=list, description="可搜索的關鍵詞")
    knowledge_domains: List[str] = Field(default_factory=list, description="涉及的知識領域")
    
    # 動態欄位區域（AI自由決定）
    dynamic_fields: Dict[str, Any] = Field(default_factory=dict, description="AI根據內容動態決定的欄位")
    
    # 結構化常用欄位（選填，AI判斷是否需要）
    extracted_entities: Optional[List[str]] = Field(None, description="提取的實體名稱（人名、地名、機構等）")
    main_topics: Optional[List[str]] = Field(None, description="主要主題")
    key_concepts: Optional[List[str]] = Field(None, description="核心概念")
    action_items: Optional[List[str]] = Field(None, description="行動項目或任務")
    dates_mentioned: Optional[List[str]] = Field(None, description="提及的日期")
    amounts_mentioned: Optional[List[Dict[str, Any]]] = Field(None, description="提及的金額或數量")
    
    # 文檔特性（AI判斷適用性）
    document_purpose: Optional[str] = Field(None, description="文檔目的或用途")
    target_audience: Optional[str] = Field(None, description="目標受眾")
    urgency_level: Optional[str] = Field(None, description="緊急程度")
    
    # 個人筆記特性（當內容為筆記時填充）
    note_structure: Optional[str] = Field(None, description="筆記結構類型")
    thinking_patterns: Optional[List[str]] = Field(None, description="思考模式")
    
    # 商業文檔特性（當內容為商業文檔時填充）
    business_context: Optional[str] = Field(None, description="商業背景")
    stakeholders: Optional[List[str]] = Field(None, description="相關利益方")
    
    # 法律/官方文檔特性（當內容為法律文檔時填充）
    legal_context: Optional[str] = Field(None, description="法律背景")
    compliance_requirements: Optional[List[str]] = Field(None, description="合規要求")

# === 主要輸出模型 ===

class AIImageAnalysisOutput(BaseModel):
    """圖片分析輸出 - 統一使用靈活結構"""
    initial_summary: str = Field(..., description="圖片的初步摘要或描述")
    extracted_text: Optional[str] = Field(None, description="從圖片中提取的全部可見文字")
    content_type: str = Field(..., description="AI識別的內容類型")
    intermediate_analysis: Union[FlexibleIntermediateAnalysis, Dict[str, Any]] = Field(..., description="AI的中間分析過程")
    key_information: Union[FlexibleKeyInformation, Dict[str, Any]] = Field(..., description="提取的結構化關鍵信息")
    model_used: Optional[str] = Field(None, description="實際用於分析的AI模型名稱")
    error_message: Optional[str] = Field(None, description="分析過程中的錯誤訊息")

class AITextAnalysisOutput(BaseModel):
    """文本分析輸出 - 統一使用靈活結構"""
    initial_summary: str = Field(..., description="文本的初步摘要")
    content_type: str = Field(..., description="AI識別的內容類型")
    intermediate_analysis: Union[FlexibleIntermediateAnalysis, Dict[str, Any]] = Field(..., description="AI的中間分析過程")
    key_information: Union[FlexibleKeyInformation, Dict[str, Any]] = Field(..., description="提取的結構化關鍵信息")
    model_used: Optional[str] = Field(None, description="實際用於分析的AI模型名稱")
    error_message: Optional[str] = Field(None, description="分析過程中的錯誤訊息")

# === New Model Definitions ===

class AIQueryRewriteOutput(BaseModel):
    rewritten_queries: List[str] = Field(default_factory=list)
    extracted_parameters: Dict[str, Any] = Field(default_factory=dict)
    intent_analysis: str = "Intent analysis not provided"

class AIGeneratedAnswerOutput(BaseModel):
    answer_text: str = "Could not generate a valid answer."
    # Potentially add other fields like confidence if the LLM provides it directly

class AIDocumentKeyInformation(BaseModel):
    # Define fields that are expected within key_information
    # This is an example, adjust based on actual consistent fields
    content_summary: Optional[str] = None
    main_topics: List[str] = Field(default_factory=list)
    # Add other dynamic_fields or specific known fields if they have a somewhat consistent structure
    # For truly dynamic fields, keeping them as Dict[str, Any] might be necessary
    dynamic_fields: Dict[str, Any] = Field(default_factory=dict) 
    # Add other fields like 'rewritten_queries', 'extracted_parameters' if they can appear here for some reason

class AIDocumentAnalysisOutputDetail(BaseModel):
    initial_summary: Optional[str] = None
    initial_description: Optional[str] = None # For images
    content_type: Optional[str] = None # e.g., "text_analysis_result", "image_analysis_result"
    key_information: Optional[AIDocumentKeyInformation] = None
    # Add other top-level fields from the 'ai_analysis_output' dictionary if they are consistent
    # error_message: Optional[str] = None # If errors can be part of this structured output

# === 向後兼容（暫時保留，用於錯誤回退） ===

# 簡化的中間分析步驟（僅用於回退）
class IntermediateAnalysisStep(BaseModel):
    potential_field: str = Field(..., description="潛在的關鍵信息欄位名稱")
    text_fragment: Optional[str] = Field(None, description="支持判斷的原始文字片段")
    reasoning: str = Field(..., description="判斷理由或分析說明")

# 向後兼容的別名
AIImageAnalysisOutputFlexible = AIImageAnalysisOutput  # 別名，實際上是同一個類 