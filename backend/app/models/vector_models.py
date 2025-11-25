from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

class VectorDocumentStatus(str, Enum):
    """向量文檔狀態"""
    PENDING_EMBEDDING = "pending_embedding"  # 等待生成向量
    EMBEDDED = "embedded"  # 已生成向量
    EMBEDDING_FAILED = "embedding_failed"  # 向量生成失敗
    INDEXED = "indexed"  # 已索引到向量資料庫

class SemanticSummary(BaseModel):
    """語義摘要模型"""
    document_id: str = Field(..., description="對應的MongoDB文檔ID")
    summary_text: str = Field(..., description="語義摘要文本")
    file_type: Optional[str] = Field(None, description="文件類型")
    key_terms: List[str] = Field(default_factory=list, description="關鍵詞")
    full_ai_analysis: Optional[Dict[str, Any]] = Field(None, description="完整的 AI 結構化分析結果")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class VectorRecord(BaseModel):
    """向量記錄模型"""
    document_id: str = Field(..., description="對應的MongoDB文檔ID")
    owner_id: str = Field(..., description="文檔所有者的ID")
    vector_id: Optional[str] = Field(None, description="向量資料庫中的內部向量ID")
    embedding_vector: Optional[List[float]] = Field(None, description="向量數據")
    chunk_text: Optional[str] = Field(None, description="被向量化的原始文本塊或其摘要")
    embedding_model: str = Field(..., description="使用的Embedding模型")
    status: VectorDocumentStatus = Field(VectorDocumentStatus.PENDING_EMBEDDING)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="其他元數據，例如 vector_type")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = Field(None, description="錯誤信息")

class SemanticSearchRequest(BaseModel):
    """語義搜索請求"""
    query: str = Field(..., max_length=2000, description="搜索查詢")
    top_k: int = Field(default=10, ge=1, le=100, description="返回結果數量")
    similarity_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="相似度閾值")
    filter_conditions: Optional[Dict[str, Any]] = Field(None, description="過濾條件")
    collection_name: Optional[str] = Field(None, description="要搜索的集合名稱")
    
    # 新增：混合檢索配置
    enable_hybrid_search: bool = Field(default=True, description="啟用混合檢索策略")
    enable_diversity_optimization: bool = Field(default=True, description="啟用結果多樣性優化")
    query_expansion_factor: float = Field(default=1.5, ge=1.0, le=3.0, description="查詢擴展因子")
    rerank_top_k: int = Field(default=20, ge=10, le=50, description="重排序候選數量")
    
    # 新增：搜索類型指定（前端兼容性）
    search_type: Optional[str] = Field(default="hybrid", description="搜索類型：hybrid, summary_only, chunks_only, legacy, rrf_fusion")
    
    # 新增：RRF 融合檢索權重配置
    rrf_weights: Optional[Dict[str, float]] = Field(
        default=None, 
        description="RRF 融合檢索權重配置，格式: {'summary': 0.4, 'chunks': 0.6}"
    )
    rrf_k_constant: Optional[int] = Field(
        default=None, 
        ge=1, 
        le=200, 
        description="RRF 常數 k，用於降低高排名的影響力（預設：60）"
    )

class SemanticSearchResult(BaseModel):
    """語義搜索結果"""
    document_id: str = Field(..., description="匹配的文檔ID")
    similarity_score: float = Field(..., description="相似度分數")
    summary_text: str = Field(..., description="語義摘要文本")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元數據")

    # Phase 4: AI 邏輯分塊行號資訊 (用於精確引用)
    start_line: Optional[str] = Field(None, description="區塊起始行號 (例如 'L001')")
    end_line: Optional[str] = Field(None, description="區塊結束行號 (例如 'L010')")
    chunk_type: Optional[str] = Field(None, description="區塊類型 (header, paragraph, list, table 等)")

class AIQARequest(BaseModel):
    """AI問答請求"""
    question: str = Field(..., description="User's question to be answered")
    document_ids: Optional[List[str]] = Field(None, description="Optional list of specific document IDs to search within")
    context_limit: Optional[int] = Field(10, ge=1, le=50, description="Maximum number of context documents to include")
    use_semantic_search: Optional[bool] = Field(True, description="Enable semantic/vector search")
    use_structured_filter: Optional[bool] = Field(False, description="Enable structured filtering based on query analysis")
    session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")
    conversation_id: Optional[str] = Field(None, description="對話ID，用於關聯歷史記憶和上下文")
    model_preference: Optional[str] = Field(None, description="Preferred AI model for this request")
    use_ai_detailed_query: Optional[bool] = Field(True, description="Enable AI to generate specific queries for detailed data extraction from documents.")
    
    # 新增的用戶可調整參數
    detailed_text_max_length: Optional[int] = Field(8000, ge=1000, le=20000, description="Maximum length of detailed text content extracted from documents")
    max_chars_per_doc: Optional[int] = Field(3000, ge=500, le=8000, description="Maximum characters per individual document before truncation")
    query_rewrite_count: Optional[int] = Field(3, ge=1, le=8, description="Number of different query rewrites to generate for better search coverage")
    max_documents_for_selection: Optional[int] = Field(8, ge=3, le=15, description="Maximum number of candidate documents for AI selection")
    similarity_threshold: Optional[float] = Field(0.3, ge=0.1, le=0.8, description="Minimum similarity score threshold for document selection")
    ai_selection_limit: Optional[int] = Field(3, ge=1, le=8, description="Maximum number of documents AI can select for detailed query")
    enable_query_expansion: Optional[bool] = Field(True, description="Enable intelligent query expansion and synonym matching")
    context_window_overlap: Optional[float] = Field(0.1, ge=0.0, le=0.5, description="Overlap ratio between context windows when processing long documents")
    
    # AI 輸出控制參數
    ensure_chinese_output: Optional[bool] = Field(None, description="確保AI回答使用中文輸出，如果未指定則使用全域設定")
    
    # 新增: 工作流控制參數
    skip_classification: Optional[bool] = Field(False, description="跳過問題分類,直接使用標準流程")
    workflow_action: Optional[str] = Field(None, description="工作流操作: approve_search, skip_search, confirm_documents, provide_clarification")
    clarification_text: Optional[str] = Field(None, description="用戶對澄清問題的回答文本")
    force_strategy: Optional[str] = Field(None, description="強制使用特定策略: simple, standard, complex")
    workflow_step: Optional[str] = Field(None, description="當前工作流步驟(用於前端逐步執行)")

class QueryRewriteResult(BaseModel):
    """查詢重寫結果 - 支持智能意圖分析和動態策略路由"""
    original_query: str = Field(..., description="原始查詢")
    rewritten_queries: List[str] = Field(..., description="重寫後的查詢列表")
    extracted_parameters: Dict[str, Any] = Field(default_factory=dict, description="提取的結構化參數")
    intent_analysis: Optional[str] = Field(None, description="意圖分析")
    
    # 新增：智能策略路由字段
    query_granularity: Optional[str] = Field(None, description="問題粒度：thematic, detailed, unknown")
    search_strategy_suggestion: Optional[str] = Field(None, description="建議的搜索策略：summary_only, rrf_fusion, keyword_enhanced_rrf")
    reasoning: Optional[str] = Field(None, description="AI 對原始問題的分析推理過程")

# 新增：用於表示向量搜索的單個原始結果
class SemanticContextDocument(BaseModel):
    """向量搜索階段返回的原始上下文信息"""
    document_id: str = Field(..., description="匹配的文檔ID")
    summary_or_chunk_text: str = Field(..., description="向量庫中的摘要或文本片段")
    similarity_score: float = Field(..., description="相似度分數")
    metadata: Optional[Dict[str, Any]] = Field(None, description="來自向量庫的元數據")

class LLMContextDocument(BaseModel):
    """提供給LLM的單個文檔上下文信息"""
    document_id: str = Field(..., description="文檔ID")
    content_used: str = Field(..., description="實際提供給LLM的文本內容")
    source_type: str = Field(..., description="內容來源類型（例如 'summary', 'extracted_text', 'full_content'）")

class AIQAResponse(BaseModel):
    """AI問答響應"""
    answer: str = Field(..., description="AI生成的答案")
    source_documents: List[str] = Field(..., description="參考文檔ID列表")
    confidence_score: Optional[float] = Field(None, description="信心分數")
    tokens_used: int = Field(..., description="消耗的Token數量")
    processing_time: float = Field(..., description="處理時間（秒）")
    query_rewrite_result: Optional[QueryRewriteResult] = Field(None, description="查詢重寫結果的詳細過程")
    semantic_search_contexts: Optional[List[SemanticContextDocument]] = Field(None, description="向量搜索階段返回的原始上下文列表")
    llm_context_documents: Optional[List[LLMContextDocument]] = Field(None, description="實際提供給LLM進行答案生成的文檔上下文片段")
    session_id: Optional[str] = Field(None, description="會話ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ai_generated_query_reasoning: Optional[str] = Field(None, description="Reasoning behind the AI-generated MongoDB query for detailed data retrieval.")
    detailed_document_data_from_ai_query: Optional[List[Dict[str, Any]]] = Field(None, description="List of specific data fetched from documents using AI-generated MongoDB queries.")
    
    # 新增: 工作流狀態相關欄位
    classification: Optional[Any] = Field(None, description="問題分類結果")  # QuestionClassification
    workflow_state: Optional[Dict[str, Any]] = Field(None, description="當前工作流狀態")
    next_action: Optional[str] = Field(None, description="下一步需要的操作: approve_search, approve_answer, provide_clarification")
    pending_approval: Optional[str] = Field(None, description="等待批准的類型: search, answer, clarification")
    error_message: Optional[str] = Field(None, description="錯誤信息(如果有)")

# 新增：用於批量處理請求的模型
class BatchProcessRequest(BaseModel):
    document_ids: List[str] = Field(..., description="要批量處理的文檔ID列表") 