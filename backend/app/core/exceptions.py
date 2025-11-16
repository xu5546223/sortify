"""
自定義異常類框架

定義應用程式的異常層次結構，提供更精確的錯誤處理和更好的錯誤信息。
"""

from typing import Optional, Dict, Any
from fastapi import status


class SortifyBaseException(Exception):
    """
    所有 Sortify 應用自定義異常的基類
    
    Attributes:
        message: 錯誤信息
        error_code: 內部錯誤代碼
        details: 額外的錯誤詳情
        status_code: HTTP 狀態碼（用於 API 響應）
    """
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式（用於 API 響應）"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


# ==================== 文檔相關異常 ====================

class DocumentError(SortifyBaseException):
    """文檔處理相關的基礎異常"""
    pass


class DocumentNotFoundError(DocumentError):
    """找不到文檔"""
    def __init__(self, document_id: str, **kwargs):
        super().__init__(
            message=f"找不到文檔: {document_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"document_id": document_id},
            **kwargs
        )


class DocumentProcessingError(DocumentError):
    """文檔處理失敗"""
    def __init__(self, filename: str, reason: str, **kwargs):
        super().__init__(
            message=f"處理文檔 '{filename}' 失敗: {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"filename": filename, "reason": reason},
            **kwargs
        )


class UnsupportedFileTypeError(DocumentError):
    """不支持的文件類型"""
    def __init__(self, file_type: str, **kwargs):
        super().__init__(
            message=f"不支持的文件類型: {file_type}",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            details={"file_type": file_type},
            **kwargs
        )


class FileSizeLimitExceededError(DocumentError):
    """文件大小超過限制"""
    def __init__(self, size: int, max_size: int, **kwargs):
        super().__init__(
            message=f"文件大小 ({size} bytes) 超過限制 ({max_size} bytes)",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={"size": size, "max_size": max_size},
            **kwargs
        )


# ==================== AI 服務相關異常 ====================

class AIServiceError(SortifyBaseException):
    """AI 服務相關的基礎異常"""
    pass


class AIModelNotAvailableError(AIServiceError):
    """AI 模型不可用"""
    def __init__(self, model_name: str, **kwargs):
        super().__init__(
            message=f"AI 模型不可用: {model_name}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"model_name": model_name},
            **kwargs
        )


class AIGenerationError(AIServiceError):
    """AI 生成內容失敗"""
    def __init__(self, task_type: str, reason: str, **kwargs):
        super().__init__(
            message=f"AI 生成失敗 ({task_type}): {reason}",
            details={"task_type": task_type, "reason": reason},
            **kwargs
        )


class AIQuotaExceededError(AIServiceError):
    """AI API 配額超限"""
    def __init__(self, service: str, **kwargs):
        super().__init__(
            message=f"{service} API 配額已用盡",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"service": service},
            **kwargs
        )


class PromptValidationError(AIServiceError):
    """Prompt 驗證失敗"""
    def __init__(self, reason: str, **kwargs):
        super().__init__(
            message=f"Prompt 驗證失敗: {reason}",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"reason": reason},
            **kwargs
        )


# ==================== 向量搜索相關異常 ====================

class VectorSearchError(SortifyBaseException):
    """向量搜索相關的基礎異常"""
    pass


class VectorDatabaseError(VectorSearchError):
    """向量資料庫操作失敗"""
    def __init__(self, operation: str, reason: str, **kwargs):
        super().__init__(
            message=f"向量資料庫操作失敗 ({operation}): {reason}",
            details={"operation": operation, "reason": reason},
            **kwargs
        )


class EmbeddingGenerationError(VectorSearchError):
    """Embedding 生成失敗"""
    def __init__(self, text_length: int, reason: str, **kwargs):
        super().__init__(
            message=f"生成 Embedding 失敗: {reason}",
            details={"text_length": text_length, "reason": reason},
            **kwargs
        )


class NoSearchResultsError(VectorSearchError):
    """搜索無結果"""
    def __init__(self, query: str, **kwargs):
        super().__init__(
            message="未找到相關內容",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"query": query},
            **kwargs
        )


# ==================== 用戶認證相關異常 ====================

class AuthenticationError(SortifyBaseException):
    """認證相關的基礎異常"""
    def __init__(self, message: str = "認證失敗", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            **kwargs
        )


class InvalidCredentialsError(AuthenticationError):
    """無效的憑證"""
    def __init__(self, **kwargs):
        super().__init__(
            message="用戶名或密碼錯誤",
            **kwargs
        )


class TokenExpiredError(AuthenticationError):
    """Token 已過期"""
    def __init__(self, **kwargs):
        super().__init__(
            message="認證 Token 已過期",
            **kwargs
        )


class InsufficientPermissionsError(SortifyBaseException):
    """權限不足"""
    def __init__(self, required_permission: str, **kwargs):
        super().__init__(
            message=f"權限不足，需要: {required_permission}",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"required_permission": required_permission},
            **kwargs
        )


# ==================== 資料庫相關異常 ====================

class DatabaseError(SortifyBaseException):
    """資料庫操作相關的基礎異常"""
    pass


class DatabaseConnectionError(DatabaseError):
    """資料庫連接失敗"""
    def __init__(self, database: str, reason: str, **kwargs):
        super().__init__(
            message=f"連接 {database} 失敗: {reason}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"database": database, "reason": reason},
            **kwargs
        )


class DataValidationError(DatabaseError):
    """資料驗證失敗"""
    def __init__(self, field: str, reason: str, **kwargs):
        super().__init__(
            message=f"資料驗證失敗 ({field}): {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"field": field, "reason": reason},
            **kwargs
        )


# ==================== 快取相關異常 ====================

class CacheError(SortifyBaseException):
    """快取操作相關的基礎異常"""
    pass


class CacheConnectionError(CacheError):
    """快取連接失敗"""
    def __init__(self, cache_type: str, reason: str, **kwargs):
        super().__init__(
            message=f"{cache_type} 連接失敗: {reason}",
            details={"cache_type": cache_type, "reason": reason},
            **kwargs
        )


# ==================== 外部服務相關異常 ====================

class ExternalServiceError(SortifyBaseException):
    """外部服務相關的基礎異常"""
    pass


class GmailAPIError(ExternalServiceError):
    """Gmail API 錯誤"""
    def __init__(self, operation: str, reason: str, **kwargs):
        super().__init__(
            message=f"Gmail API 操作失敗 ({operation}): {reason}",
            details={"operation": operation, "reason": reason},
            **kwargs
        )


class GoogleAPIError(ExternalServiceError):
    """Google API 錯誤"""
    def __init__(self, service: str, reason: str, **kwargs):
        super().__init__(
            message=f"Google {service} API 失敗: {reason}",
            details={"service": service, "reason": reason},
            **kwargs
        )


# ==================== 工具函數 ====================

def handle_exception(exc: Exception) -> SortifyBaseException:
    """
    將標準異常轉換為自定義異常
    
    Args:
        exc: 原始異常
        
    Returns:
        對應的自定義異常
    """
    if isinstance(exc, SortifyBaseException):
        return exc
    
    # 根據異常類型轉換
    error_mapping = {
        FileNotFoundError: lambda e: DocumentNotFoundError(str(e)),
        PermissionError: lambda e: InsufficientPermissionsError("file_access"),
        ValueError: lambda e: DataValidationError("value", str(e)),
        ConnectionError: lambda e: DatabaseConnectionError("unknown", str(e)),
    }
    
    converter = error_mapping.get(type(exc))
    if converter:
        return converter(exc)
    
    # 預設包裝為基礎異常
    return SortifyBaseException(
        message=str(exc),
        error_code="UNEXPECTED_ERROR",
        details={"original_error": type(exc).__name__}
    )
