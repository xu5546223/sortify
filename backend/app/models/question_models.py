"""
問題分類相關模型定義

用於智能問答系統的問題意圖分類和工作流管理
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QuestionIntent(str, Enum):
    """問題意圖類型枚舉"""
    GREETING = "greeting"  # 寒暄問候
    CHITCHAT = "chitchat"  # 閒聊
    CLARIFICATION_NEEDED = "clarification_needed"  # 需要澄清
    SIMPLE_FACTUAL = "simple_factual"  # 簡單事實查詢（通用知識或歷史中有完整答案）
    DOCUMENT_SEARCH = "document_search"  # 文檔搜索（不確定在哪個文檔）
    DOCUMENT_DETAIL_QUERY = "document_detail_query"  # 文檔詳細查詢（已知文檔，需要詳細數據）⭐ 新增
    COMPLEX_ANALYSIS = "complex_analysis"  # 複雜分析（多文檔整合分析）


class QuestionClassification(BaseModel):
    """問題分類結果"""
    intent: QuestionIntent = Field(..., description="問題意圖類型")
    confidence: float = Field(..., ge=0.0, le=1.0, description="分類置信度")
    reasoning: str = Field(..., description="分類理由")
    requires_documents: bool = Field(default=False, description="是否需要查找文檔")
    requires_context: bool = Field(default=False, description="是否需要對話上下文")
    suggested_strategy: str = Field(..., description="建議的處理策略")
    
    # 澄清相關欄位
    clarification_question: Optional[str] = Field(None, description="澄清問題")
    suggested_responses: Optional[List[str]] = Field(None, description="建議的回答選項")
    
    # 額外信息
    query_complexity: Optional[str] = Field(None, description="查詢複雜度: simple, moderate, complex")
    estimated_api_calls: Optional[int] = Field(None, description="預估 API 調用次數")
    
    # 文檔詳細查詢專用欄位
    target_document_ids: Optional[List[str]] = Field(None, description="目標文檔ID列表（用於 document_detail_query）")
    target_document_reasoning: Optional[str] = Field(None, description="選擇這些文檔的原因")
    
    class Config:
        use_enum_values = True


class QuestionClassifierConfig(BaseModel):
    """問題分類器配置"""
    enabled: bool = Field(default=True, description="是否啟用問題分類器")
    model: str = Field(default="gemini-2.0-flash-exp", description="使用的 AI 模型")
    max_input_tokens: int = Field(default=1000, description="最大輸入 token 數")
    max_output_tokens: int = Field(default=512, description="最大輸出 token 數,避免JSON被截斷")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="溫度參數,越低越穩定")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="置信度閾值")
    
    # 快速通道配置
    enable_greeting_shortcut: bool = Field(default=True, description="啟用寒暄快速通道")
    enable_chitchat_shortcut: bool = Field(default=True, description="啟用閒聊快速通道")
    auto_approve_simple_queries: bool = Field(default=False, description="自動批准簡單查詢")


class ConversationContext(BaseModel):
    """對話上下文信息"""
    conversation_id: str
    recent_messages: List[Dict[str, Any]] = Field(default_factory=list, description="最近的消息")
    cached_document_ids: List[str] = Field(default_factory=list, description="已緩存的文檔ID")
    cached_document_data: Optional[List[Dict[str, Any]]] = Field(None, description="已緩存的文檔數據")
    message_count: int = Field(default=0, description="消息總數")
    
    class Config:
        arbitrary_types_allowed = True


class WorkflowStepInfo(BaseModel):
    """工作流步驟信息"""
    step_name: str = Field(..., description="步驟名稱")
    status: str = Field(..., description="狀態: pending, processing, completed, skipped, failed")
    start_time: Optional[float] = Field(None, description="開始時間戳")
    end_time: Optional[float] = Field(None, description="結束時間戳")
    api_calls: int = Field(default=0, description="此步驟的 API 調用次數")
    details: Optional[Dict[str, Any]] = Field(None, description="步驟詳細信息")


class QAWorkflowState(BaseModel):
    """問答工作流狀態"""
    current_step: str = Field(..., description="當前步驟")
    classification: Optional[QuestionClassification] = Field(None, description="問題分類結果")
    steps_completed: List[WorkflowStepInfo] = Field(default_factory=list, description="已完成的步驟")
    pending_action: Optional[str] = Field(None, description="等待的操作: approve_search, approve_answer, provide_clarification")
    can_skip_to_answer: bool = Field(default=False, description="是否可以跳過直接回答")
    total_api_calls: int = Field(default=0, description="總 API 調用次數")
    
    # 文檔相關
    found_documents: Optional[List[Dict[str, Any]]] = Field(None, description="找到的文檔")
    selected_documents: Optional[List[str]] = Field(None, description="選中的文檔ID")
    
    # 錯誤處理
    errors: List[str] = Field(default_factory=list, description="錯誤信息列表")
    fallback_used: bool = Field(default=False, description="是否使用了回退策略")

