"""
资源所有权检查工具

这是一个纯工具模块，用于统一处理资源所有权验证逻辑。
创建日期: 2024-11-15
用途: 减少重复的权限检查代码
"""

from fastapi import HTTPException, status
from uuid import UUID
from typing import Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import log_event
from app.models.log_models import LogLevel


class OwnershipChecker:
    """
    資源所有權檢查器
    
    提供統一的方法來檢查用戶是否有權訪問資源。
    減少在多個 API 端點中重複的權限檢查邏輯。
    """
    
    @staticmethod
    def check_ownership(
        resource_owner_id: UUID,
        current_user_id: UUID,
        resource_type: str = "Resource",
        resource_id: Optional[str] = None
    ) -> None:
        """
        檢查用戶是否擁有資源的所有權
        
        Args:
            resource_owner_id: 資源擁有者的 ID
            current_user_id: 當前用戶的 ID
            resource_type: 資源類型名稱（用於錯誤消息）
            resource_id: 資源 ID（可選，用於錯誤消息）
        
        Raises:
            HTTPException: 如果用戶不是資源擁有者，拋出 403 錯誤
        
        Example:
            >>> OwnershipChecker.check_ownership(
            ...     document.owner_id,
            ...     current_user.id,
            ...     "Document",
            ...     str(document.id)
            ... )
        """
        if resource_owner_id != current_user_id:
            detail = f"You don't have permission to access this {resource_type}"
            if resource_id:
                detail += f" (ID: {resource_id})"
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail
            )
    
    @staticmethod
    async def require_ownership(
        resource: Any,
        current_user: Any,
        owner_field: str = "owner_id",
        resource_type: str = "Resource",
        log_unauthorized: bool = False,
        db: Optional[AsyncIOMotorDatabase] = None
    ) -> None:
        """
        要求資源所有權（更便捷的版本）
        
        自動從資源對象中提取 owner_id 並檢查權限。
        
        Args:
            resource: 資源對象（必須有 owner_field 屬性）
            current_user: 當前用戶對象（必須有 id 屬性）
            owner_field: 資源對象中表示擁有者 ID 的字段名，默認為 "owner_id"
            resource_type: 資源類型名稱（用於錯誤消息）
        
        Raises:
            HTTPException: 如果資源不存在（None）或用戶不是擁有者
        
        Example:
            >>> document = await get_document(document_id)
            >>> OwnershipChecker.require_ownership(document, current_user, resource_type="Document")
        """
        # 首先檢查資源是否存在
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{resource_type} not found"
            )
        
        # 獲取資源的擁有者 ID
        if not hasattr(resource, owner_field):
            raise ValueError(
                f"Resource object does not have '{owner_field}' attribute. "
                f"Please specify the correct owner_field parameter."
            )
        
        resource_owner_id = getattr(resource, owner_field)
        
        # 獲取資源 ID（如果有）用於錯誤消息和日志
        resource_id = None
        if hasattr(resource, 'id'):
            resource_id = str(resource.id)
        elif hasattr(resource, '_id'):
            resource_id = str(resource._id)
        
        # 檢查所有權
        if resource_owner_id != current_user.id:
            # 記錄未授權訪問（如果啟用）
            if log_unauthorized and db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.WARNING,
                    message=f"Unauthorized {resource_type} access attempt",
                    source="ownership_checker.require_ownership",
                    user_id=str(current_user.id),
                    details={
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "resource_owner_id": str(resource_owner_id),
                        "username": getattr(current_user, 'username', None)
                    }
                )
            
            # 抛出權限錯誤
            detail = f"You don't have permission to access this {resource_type}"
            if resource_id:
                detail += f" (ID: {resource_id})"
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail
            )
    
    @staticmethod
    def is_owner(
        resource: Any,
        current_user: Any,
        owner_field: str = "owner_id"
    ) -> bool:
        """
        檢查用戶是否是資源的擁有者（不拋出異常的版本）
        
        Args:
            resource: 資源對象
            current_user: 當前用戶對象
            owner_field: 資源對象中表示擁有者 ID 的字段名
        
        Returns:
            bool: 如果是擁有者返回 True，否則返回 False
        
        Example:
            >>> if OwnershipChecker.is_owner(document, current_user):
            ...     # 執行某些操作
        """
        if resource is None or current_user is None:
            return False
        
        if not hasattr(resource, owner_field):
            return False
        
        resource_owner_id = getattr(resource, owner_field)
        return resource_owner_id == current_user.id
