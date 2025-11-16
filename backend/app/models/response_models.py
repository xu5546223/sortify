"""
通用響應模型

定義 API 成功響應的 Pydantic 模型。
"""

from pydantic import BaseModel, Field
from typing import Any, Optional, Generic, TypeVar, List
from datetime import datetime

T = TypeVar('T')


class MessageResponse(BaseModel):
    """簡單消息響應"""
    message: str = Field(..., description="響應消息")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "操作成功完成"
            }
        }


class BasicResponse(BaseModel):
    """基本響應模型"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="響應消息")
    data: Any = Field(None, description="響應數據")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "操作成功",
                "data": {"id": "123", "name": "範例"}
            }
        }


class SuccessResponse(BaseModel, Generic[T]):
    """
    泛型成功響應模型
    
    用於返回成功的操作結果，支持泛型數據類型。
    """
    success: bool = Field(default=True, description="操作是否成功")
    message: str = Field(..., description="成功消息")
    data: Optional[T] = Field(None, description="響應數據")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="響應時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "文檔上傳成功",
                "data": {"document_id": "abc123", "filename": "report.pdf"},
                "timestamp": "2025-11-16T08:30:00.000Z"
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """
    分頁響應模型
    
    用於返回分頁查詢結果。
    """
    items: List[T] = Field(..., description="當前頁數據")
    total: int = Field(..., description="總數量")
    page: int = Field(..., description="當前頁碼（從 1 開始）")
    page_size: int = Field(..., description="每頁數量")
    total_pages: int = Field(..., description="總頁數")
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [{"id": "1", "name": "項目1"}, {"id": "2", "name": "項目2"}],
                "total": 100,
                "page": 1,
                "page_size": 10,
                "total_pages": 10
            }
        }


class StatusResponse(BaseModel):
    """
    狀態響應模型
    
    用於返回操作或任務的狀態。
    """
    status: str = Field(..., description="狀態")
    message: Optional[str] = Field(None, description="狀態說明")
    progress: Optional[float] = Field(None, ge=0, le=100, description="進度百分比")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "processing",
                "message": "正在處理文檔...",
                "progress": 45.5
            }
        }


class HealthCheckResponse(BaseModel):
    """
    健康檢查響應模型
    
    用於系統健康檢查端點。
    """
    status: str = Field(..., description="整體健康狀態")
    services: dict = Field(default_factory=dict, description="各服務的健康狀態")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="檢查時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "services": {
                    "database": {"status": "healthy"},
                    "vector_db": {"status": "healthy"},
                    "ai_service": {"status": "healthy"}
                },
                "timestamp": "2025-11-16T08:30:00.000Z"
            }
        }