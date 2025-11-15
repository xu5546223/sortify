"""
資源獲取和驗證輔助函數

這個模塊提供了常用的資源獲取和驗證模式，減少重複代碼。
創建日期: 2024-11-15
用途: 統一資源獲取、404檢查、權限驗證的流程
"""

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, TypeVar, Callable, Awaitable
from uuid import UUID

from .ownership_checker import OwnershipChecker

# 泛型類型，代表任何資源模型
T = TypeVar('T')


async def get_resource_or_404(
    getter_func: Callable[[AsyncIOMotorDatabase, UUID], Awaitable[Optional[T]]],
    db: AsyncIOMotorDatabase,
    resource_id: UUID,
    resource_type: str = "Resource"
) -> T:
    """
    獲取資源，如果不存在則拋出 404 錯誤
    
    這是一個通用函數，可以用於任何 CRUD 的 get 操作。
    
    Args:
        getter_func: 獲取資源的異步函數，例如 crud_documents.get_document_by_id
        db: 數據庫連接
        resource_id: 資源 ID
        resource_type: 資源類型名稱（用於錯誤消息）
    
    Returns:
        資源對象
    
    Raises:
        HTTPException: 如果資源不存在，拋出 404 錯誤
    
    Example:
        >>> document = await get_resource_or_404(
        ...     crud_documents.get_document_by_id,
        ...     db,
        ...     document_id,
        ...     "Document"
        ... )
    """
    resource = await getter_func(db, resource_id)
    
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_type} with ID {resource_id} not found"
        )
    
    return resource


async def get_owned_resource_or_404(
    getter_func: Callable[[AsyncIOMotorDatabase, UUID], Awaitable[Optional[T]]],
    db: AsyncIOMotorDatabase,
    resource_id: UUID,
    current_user: any,
    resource_type: str = "Resource",
    owner_field: str = "owner_id",
    log_unauthorized: bool = False
) -> T:
    """
    獲取資源並驗證所有權，如果不存在或無權限則拋出錯誤
    
    這是最常用的模式：先獲取資源（404檢查），再檢查權限（403檢查）。
    
    Args:
        getter_func: 獲取資源的異步函數
        db: 數據庫連接
        resource_id: 資源 ID
        current_user: 當前用戶對象
        resource_type: 資源類型名稱
        owner_field: 資源對象中表示擁有者 ID 的字段名
        log_unauthorized: 是否記錄未授權訪問（403）
    
    Returns:
        資源對象
    
    Raises:
        HTTPException: 404 如果不存在，403 如果無權限
    
    Example:
        >>> document = await get_owned_resource_or_404(
        ...     crud_documents.get_document_by_id,
        ...     db,
        ...     document_id,
        ...     current_user,
        ...     "Document",
        ...     log_unauthorized=True  # 記錄權限拒絕
        ... )
        >>> # 現在可以安全地使用 document，已經確認存在且有權限
    """
    # 首先獲取資源（404 檢查）
    resource = await get_resource_or_404(
        getter_func,
        db,
        resource_id,
        resource_type
    )
    
    # 然後檢查所有權（403 檢查）
    await OwnershipChecker.require_ownership(
        resource,
        current_user,
        owner_field=owner_field,
        resource_type=resource_type,
        log_unauthorized=log_unauthorized,
        db=db if log_unauthorized else None
    )
    
    return resource


def validate_resource_exists(
    resource: Optional[T],
    resource_type: str = "Resource",
    resource_id: Optional[str] = None
) -> T:
    """
    驗證資源存在（同步版本，用於已經獲取的資源）
    
    當你已經獲取了資源，只需要驗證它不是 None 時使用。
    
    Args:
        resource: 資源對象（可能為 None）
        resource_type: 資源類型名稱
        resource_id: 資源 ID（可選，用於錯誤消息）
    
    Returns:
        資源對象（保證不為 None）
    
    Raises:
        HTTPException: 如果資源為 None，拋出 404 錯誤
    
    Example:
        >>> document = await some_get_function()
        >>> document = validate_resource_exists(document, "Document", str(document_id))
    """
    if resource is None:
        detail = f"{resource_type} not found"
        if resource_id:
            detail += f" (ID: {resource_id})"
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail
        )
    
    return resource
