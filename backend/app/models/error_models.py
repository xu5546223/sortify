"""
錯誤響應模型

定義 API 錯誤響應的 Pydantic 模型，與自定義異常系統配合使用。
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class ErrorDetail(BaseModel):
    """錯誤詳情模型"""
    
    field: Optional[str] = Field(None, description="相關欄位名稱")
    message: str = Field(..., description="錯誤描述")
    type: Optional[str] = Field(None, description="錯誤類型")
    
    class Config:
        json_schema_extra = {
            "example": {
                "field": "email",
                "message": "電子郵件格式無效",
                "type": "value_error.email"
            }
        }


class ErrorResponse(BaseModel):
    """
    統一的錯誤響應模型
    
    用於所有 API 錯誤響應，提供一致的錯誤信息結構。
    """
    
    error_code: str = Field(..., description="錯誤代碼（用於識別錯誤類型）")
    message: str = Field(..., description="人類可讀的錯誤信息")
    details: Dict[str, Any] = Field(default_factory=dict, description="額外的錯誤詳情")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="錯誤發生時間")
    path: Optional[str] = Field(None, description="發生錯誤的 API 路徑")
    request_id: Optional[str] = Field(None, description="請求追踪 ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "DocumentNotFoundError",
                "message": "找不到文檔: abc123",
                "details": {
                    "document_id": "abc123"
                },
                "timestamp": "2025-11-16T08:30:00.000Z",
                "path": "/api/v1/documents/abc123",
                "request_id": "req_xyz789"
            }
        }


class ValidationErrorResponse(BaseModel):
    """
    驗證錯誤響應模型
    
    用於請求參數驗證失敗的情況。
    """
    
    error_code: str = Field(default="ValidationError", description="錯誤代碼")
    message: str = Field(default="請求驗證失敗", description="錯誤信息")
    errors: List[ErrorDetail] = Field(..., description="驗證錯誤列表")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="錯誤發生時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "ValidationError",
                "message": "請求驗證失敗",
                "errors": [
                    {
                        "field": "email",
                        "message": "電子郵件格式無效",
                        "type": "value_error.email"
                    },
                    {
                        "field": "password",
                        "message": "密碼長度必須至少 8 個字符",
                        "type": "value_error.str.min_length"
                    }
                ],
                "timestamp": "2025-11-16T08:30:00.000Z"
            }
        }


class ServiceHealthError(BaseModel):
    """
    服務健康檢查錯誤模型
    
    用於服務不可用或健康檢查失敗的情況。
    """
    
    service_name: str = Field(..., description="服務名稱")
    status: str = Field(..., description="服務狀態")
    error: Optional[str] = Field(None, description="錯誤信息")
    last_check: datetime = Field(default_factory=datetime.utcnow, description="最後檢查時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "service_name": "vector_db_service",
                "status": "unhealthy",
                "error": "連接超時",
                "last_check": "2025-11-16T08:30:00.000Z"
            }
        }


class BatchOperationError(BaseModel):
    """
    批量操作錯誤模型
    
    用於批量操作部分失敗的情況。
    """
    
    total: int = Field(..., description="總操作數量")
    successful: int = Field(..., description="成功數量")
    failed: int = Field(..., description="失敗數量")
    errors: List[ErrorResponse] = Field(default_factory=list, description="錯誤詳情列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total": 10,
                "successful": 7,
                "failed": 3,
                "errors": [
                    {
                        "error_code": "DocumentNotFoundError",
                        "message": "找不到文檔: doc1",
                        "details": {"document_id": "doc1"},
                        "timestamp": "2025-11-16T08:30:00.000Z"
                    }
                ]
            }
        }


class APIErrorResponse(BaseModel):
    """
    通用 API 錯誤響應（用於文檔生成）
    
    這是 OpenAPI 文檔中顯示的錯誤響應格式。
    """
    
    detail: str = Field(..., description="錯誤詳情")
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "操作失敗的詳細信息"
            }
        }


# ==================== 特定領域的錯誤響應 ====================

class DocumentErrorResponse(ErrorResponse):
    """文檔相關錯誤響應"""
    
    document_id: Optional[str] = Field(None, description="相關文檔 ID")
    filename: Optional[str] = Field(None, description="文件名稱")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "DocumentProcessingError",
                "message": "處理文檔失敗",
                "details": {
                    "reason": "PDF 結構損壞"
                },
                "document_id": "abc123",
                "filename": "report.pdf",
                "timestamp": "2025-11-16T08:30:00.000Z"
            }
        }


class AIServiceErrorResponse(ErrorResponse):
    """AI 服務錯誤響應"""
    
    model_name: Optional[str] = Field(None, description="AI 模型名稱")
    task_type: Optional[str] = Field(None, description="任務類型")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "AIGenerationError",
                "message": "AI 生成失敗",
                "details": {
                    "reason": "模型配額已用盡"
                },
                "model_name": "gemini-1.5-flash",
                "task_type": "image_analysis",
                "timestamp": "2025-11-16T08:30:00.000Z"
            }
        }


class AuthErrorResponse(ErrorResponse):
    """認證錯誤響應"""
    
    auth_type: Optional[str] = Field(None, description="認證類型")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "InvalidCredentialsError",
                "message": "用戶名或密碼錯誤",
                "details": {},
                "auth_type": "password",
                "timestamp": "2025-11-16T08:30:00.000Z"
            }
        }
