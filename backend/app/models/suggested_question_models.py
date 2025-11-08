"""
建議問題相關的數據模型
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class QuestionType(str, Enum):
    """問題類型"""
    SUMMARY = "summary"  # 總結類
    COMPARISON = "comparison"  # 比較類
    ANALYSIS = "analysis"  # 分析類
    TIME_BASED = "time_based"  # 時間相關
    DETAIL_QUERY = "detail_query"  # 詳細查詢
    CROSS_CATEGORY = "cross_category"  # 跨分類


class SuggestedQuestion(BaseModel):
    """單個建議問題"""
    id: str = Field(..., description="問題唯一ID")
    question: str = Field(..., description="問題文本")
    category: Optional[str] = Field(None, description="關聯的分類名稱")
    category_id: Optional[str] = Field(None, description="關聯的聚類ID")
    related_documents: List[str] = Field(default_factory=list, description="相關文檔ID列表")
    is_cross_category: bool = Field(False, description="是否跨分類問題")
    question_type: QuestionType = Field(..., description="問題類型")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="創建時間")
    last_used_at: Optional[datetime] = Field(None, description="最後使用時間")
    use_count: int = Field(0, description="使用次數")


class SuggestedQuestionsDocument(BaseModel):
    """用戶的建議問題文檔"""
    user_id: str = Field(..., description="用戶ID")
    questions: List[SuggestedQuestion] = Field(default_factory=list, description="問題列表")
    last_generated: datetime = Field(default_factory=datetime.utcnow, description="最後生成時間")
    total_documents: int = Field(0, description="生成時的文檔總數")
    version: int = Field(1, description="版本號")


class GenerateQuestionsRequest(BaseModel):
    """生成問題請求"""
    force_regenerate: bool = Field(False, description="是否強制重新生成")
    questions_per_category: int = Field(5, description="每個分類生成的問題數量")
    include_cross_category: bool = Field(True, description="是否包含跨分類問題")


class GenerateQuestionsResponse(BaseModel):
    """生成問題響應"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="響應消息")
    total_questions: int = Field(0, description="生成的問題總數")
    questions: List[SuggestedQuestion] = Field(default_factory=list, description="生成的問題列表")


class GetSuggestedQuestionsResponse(BaseModel):
    """獲取建議問題響應"""
    questions: List[SuggestedQuestion] = Field(..., description="問題列表")
    total: int = Field(..., description="問題總數")


class AIGeneratedQuestionsOutput(BaseModel):
    """AI 生成的問題輸出格式"""
    questions: List[dict] = Field(..., description="生成的問題列表")
    # 每個問題的格式：
    # {
    #   "question": "問題文本",
    #   "question_type": "summary|comparison|analysis|...",
    #   "category": "分類名稱（可選）",
    #   "is_cross_category": false,
    #   "reasoning": "生成理由（可選）"
    # }

