from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Union
from app.services.ai.unified_ai_config import TaskType

class TokenUsage(BaseModel):
    prompt_tokens: int = Field(..., description="輸入提示詞所使用的 Token 數量")
    completion_tokens: int = Field(..., description="模型生成回應所使用的 Token 數量")
    total_tokens: int = Field(..., description="總共使用的 Token 數量")
    error_message: Optional[str] = Field(None, description="錯誤訊息（如果API調用失敗）")

class AIPromptRequest(BaseModel):
    user_prompt: str = Field(..., description="使用者的提示詞", max_length=100000)
    system_prompt: Optional[str] = Field(None, description="系統級別的提示詞 (可選)")
    model: Optional[str] = Field(None, description="要使用的 AI 模型 (可選，若不指定則會依序查找DB設定或全局預設)")

class AIResponse(BaseModel):
    answer: str = Field(..., description="AI 模型生成的回應內容")
    token_usage: TokenUsage = Field(..., description="本次呼叫的 Token 使用資訊")
    model_used: str = Field(..., description="實際使用的 AI 模型")

class AIMongoDBQueryDetailOutput(BaseModel):
    """
    Represents the AI's suggested MongoDB query components for retrieving
    specific details from a single, known document.
    """
    projection: Optional[Dict[str, Any]] = Field(None, description="MongoDB projection dictionary to select specific fields. e.g., {\"title\": 1, \"sections.content\": 1}")
    sub_filter: Optional[Dict[str, Any]] = Field(None, description="MongoDB filter dictionary to apply conditions on sub-fields or array elements within the document. e.g., {\"sections.title\": \"Introduction\"} or {\"keywords\": {\"$in\": [\"AI\", \"MongoDB\"]}}")
    reasoning: Optional[str] = Field(None, description="AI's explanation for why it chose the projection and/or sub-filter.")

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
    
    # 新增: 結構化實體提取 (用於動態分類系統)
    structured_entities: Optional[Dict[str, Any]] = Field(None, description="結構化實體提取")
    # structured_entities 結構:
    # {
    #   "vendor": str,  # 店家或機構名稱
    #   "people": List[str],  # 人物列表
    #   "locations": List[str],  # 地點列表
    #   "organizations": List[str],  # 機構組織列表
    #   "items": List[Dict[str, Any]],  # 品項清單 [{"name": "御飯糰", "quantity": 1, "price": 35}]
    #   "amounts": List[Dict[str, Any]],  # 金額列表 [{"value": 80, "currency": "TWD", "context": "總計"}]
    #   "dates": List[Dict[str, str]]  # 日期列表 [{"date": "2024-05-21", "context": "交易日期"}]
    # }
    
    # 新增: 自動標題生成
    auto_title: Optional[str] = Field(None, description="AI自動生成的文檔標題(6-15字)")

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
    """智能查詢重寫輸出模型 - 支持意圖分析和動態策略路由"""
    reasoning: str = Field(..., description="對原始問題的分析過程和推理")
    
    query_granularity: str = Field(
        ..., 
        description="問題粒度：'thematic' (主題級/概括性) 或 'detailed' (細節級/精確性) 或 'unknown' (不確定)"
    )
    
    rewritten_queries: List[str] = Field(
        ..., 
        description="基於分析結果生成的多個優化查詢，數量應為3到5個"
    )
    
    search_strategy_suggestion: str = Field(
        ...,
        description="根據問題粒度和內容建議的搜索策略：'summary_only', 'rrf_fusion', 或 'keyword_enhanced_rrf'"
    )
    
    # 保留原有的 extracted_parameters 以保持向後兼容
    extracted_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="提取的查詢參數，包含時間範圍、實體、領域等結構化信息"
    )
    
    # 擴展的意圖分析信息
    intent_analysis: str = Field(
        default="Intent analysis not provided",
        description="深度意圖分析結果"
    )

# 原有的向後兼容版本
class AIQueryRewriteOutputLegacy(BaseModel):
    rewritten_queries: List[str] = Field(default_factory=list)
    extracted_parameters: Dict[str, Any] = Field(default_factory=dict)
    intent_analysis: str = "Intent analysis not provided"

class AIGeneratedAnswerOutput(BaseModel):
    answer_text: str = "Could not generate a valid answer."
    # Potentially add other fields like confidence if the LLM provides it directly

class AIDocumentSelectionOutput(BaseModel):
    """
    Represents the AI's decision on which documents are most relevant
    for a detailed query based on their summaries.
    """
    selected_document_ids: List[str] = Field(default_factory=list, description="A list of document IDs that the AI has chosen as most relevant for a detailed query.")
    reasoning: Optional[str] = Field(None, description="AI's explanation for why it chose these specific documents.")

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


# === 聚類標籤生成輸出模型 ===

class AIClusterLabelOutput(BaseModel):
    """聚類標籤生成輸出 - 用於動態文檔分類(單個聚類)"""
    cluster_name: str = Field(..., description="生成的聚類名稱 (簡潔, 3-10字)")
    cluster_description: Optional[str] = Field(None, description="聚類的詳細描述")
    common_themes: List[str] = Field(default_factory=list, description="共通主題列表")
    suggested_keywords: List[str] = Field(default_factory=list, description="建議的關鍵詞")
    confidence: Optional[float] = Field(None, description="命名置信度(0.0-1.0)")
    reasoning: Optional[str] = Field(None, description="命名推理過程")
    
    model_config = ConfigDict(extra='allow')

class ClusterLabelItem(BaseModel):
    """單個聚類標籤項"""
    cluster_index: int = Field(..., description="聚類索引")
    label: str = Field(..., description="聚類標籤/名稱")
    description: Optional[str] = Field(None, description="聚類描述")
    keywords: Optional[List[str]] = Field(None, description="關鍵詞列表")

class AIBatchClusterLabelsOutput(BaseModel):
    """批量聚類標籤生成輸出 - 一次生成多個聚類的標籤"""
    labels: List[ClusterLabelItem] = Field(..., description="所有聚類的標籤列表")
    total_clusters: Optional[int] = Field(None, description="總聚類數量")
    generation_notes: Optional[str] = Field(None, description="生成說明")
    
    model_config = ConfigDict(extra='allow') 