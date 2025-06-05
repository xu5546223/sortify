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

class SemanticSearchResult(BaseModel):
    """語義搜索結果"""
    document_id: str = Field(..., description="匹配的文檔ID")
    similarity_score: float = Field(..., description="相似度分數")
    summary_text: str = Field(..., description="語義摘要文本")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元數據")

class AIQARequest(BaseModel):
    """AI問答請求"""
    question: str = Field(..., max_length=2000, description="用戶問題")
    context_limit: int = Field(default=5, ge=1, le=20, description="上下文文檔數量限制")
    use_semantic_search: bool = Field(default=True, description="是否使用語義搜索")
    use_structured_filter: bool = Field(default=True, description="是否使用結構化過濾")
    session_id: Optional[str] = Field(None, description="會話ID，用於追蹤多輪對話")
    document_ids: Optional[List[str]] = Field(None, description="用於上下文的特定文檔ID列表 (可選)")
    model_preference: Optional[str] = Field(None, description="偏好的AI模型 (例如 'gemini-pro', 'gpt-4')")
    use_ai_detailed_query: Optional[bool] = Field(False, description="Enable AI to generate specific queries for detailed data extraction from documents.")

class QueryRewriteResult(BaseModel):
    """查詢重寫結果"""
    original_query: str = Field(..., description="原始查詢")
    rewritten_queries: List[str] = Field(..., description="重寫後的查詢列表")
    extracted_parameters: Dict[str, Any] = Field(default_factory=dict, description="提取的結構化參數")
    intent_analysis: Optional[str] = Field(None, description="意圖分析")

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
    detailed_document_data_from_ai_query: Optional[Dict[str, Any]] = Field(None, description="Specific data fetched from a document using an AI-generated MongoDB query.")

# 新增：用於批量處理請求的模型
class BatchProcessRequest(BaseModel):
    document_ids: List[str] = Field(..., description="要批量處理的文檔ID列表") 