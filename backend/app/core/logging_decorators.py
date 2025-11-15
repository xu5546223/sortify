"""
统一日志装饰器

基于现有的 logging_utils.py 和 log_models.py 创建的装饰器系统。
目的：减少重复的日志调用代码，统一日志记录模式。

创建日期: 2024-11-15
"""

from functools import wraps
from typing import Callable, Optional, Any
import time
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import log_event
from app.models.log_models import LogLevel


def log_api_operation(
    operation_name: Optional[str] = None,
    log_success: bool = True,
    log_failure: bool = True,
    include_duration: bool = True,
    success_level: LogLevel = LogLevel.INFO,
    failure_level: LogLevel = LogLevel.ERROR
):
    """
    API 操作日志装饰器
    
    自动记录 API 操作的成功和失败情况，包括执行时间。
    
    Args:
        operation_name: 操作名称（如果为 None，使用函数名）
        log_success: 是否记录成功操作
        log_failure: 是否记录失败操作
        include_duration: 是否包含执行时间
        success_level: 成功日志级别
        failure_level: 失败日志级别
    
    用法:
        @log_api_operation(operation_name="创建文档", log_success=True)
        async def create_document(
            db: AsyncIOMotorDatabase = Depends(get_db),
            current_user: User = Depends(get_current_active_user),
            ...
        ):
            # 业务逻辑
            return result
    
    注意：
    - 函数必须接受 db 参数（用于日志记录）
    - 可选：接受 current_user 参数（会自动记录 user_id）
    - 可选：接受 request 参数（会自动记录 request_id）
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            op_name = operation_name or func.__name__
            
            # 从参数中提取常用的上下文信息
            db = kwargs.get('db')
            current_user = kwargs.get('current_user')
            request = kwargs.get('request')
            
            # 提取 IDs
            user_id = str(current_user.id) if current_user else None
            request_id = getattr(request.state, 'request_id', None) if request else None
            
            try:
                # 执行原函数
                result = await func(*args, **kwargs)
                
                # 记录成功日志
                if log_success and db is not None:
                    duration = time.time() - start_time if include_duration else None
                    
                    await log_event(
                        db=db,
                        level=success_level,
                        message=f"{op_name} completed successfully",
                        source=f"api.{func.__module__}.{func.__name__}",
                        user_id=user_id,
                        request_id=request_id,
                        details={
                            "operation": op_name,
                            "duration_seconds": round(duration, 3) if duration else None
                        }
                    )
                
                return result
                
            except Exception as e:
                # 记录失败日志
                if log_failure and db is not None:
                    duration = time.time() - start_time if include_duration else None
                    
                    await log_event(
                        db=db,
                        level=failure_level,
                        message=f"{op_name} failed: {str(e)}",
                        source=f"api.{func.__module__}.{func.__name__}",
                        user_id=user_id,
                        request_id=request_id,
                        details={
                            "operation": op_name,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "duration_seconds": round(duration, 3) if duration else None
                        }
                    )
                
                # 重新抛出异常
                raise
        
        return wrapper
    return decorator


def log_unauthorized_access(
    resource_type: str = "Resource"
):
    """
    未授权访问日志装饰器
    
    专门用于记录权限拒绝的情况（403错误）。
    配合 ownership_checker 使用。
    
    Args:
        resource_type: 资源类型名称
    
    用法:
        @log_unauthorized_access(resource_type="Document")
        async def get_document(
            document_id: UUID,
            db: AsyncIOMotorDatabase = Depends(get_db),
            current_user: User = Depends(get_current_active_user)
        ):
            document = await get_owned_resource_or_404(...)
            return document
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db = kwargs.get('db')
            current_user = kwargs.get('current_user')
            
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # 只记录 403 错误（权限拒绝）
                if hasattr(e, 'status_code') and e.status_code == 403:
                    if db and current_user:
                        # 尝试从参数中获取资源 ID
                        resource_id = None
                        if 'document_id' in kwargs:
                            resource_id = str(kwargs['document_id'])
                        elif 'resource_id' in kwargs:
                            resource_id = str(kwargs['resource_id'])
                        elif len(args) > 0:
                            resource_id = str(args[0])
                        
                        await log_event(
                            db=db,
                            level=LogLevel.WARNING,
                            message=f"Unauthorized {resource_type} access attempt",
                            source=f"api.{func.__module__}.{func.__name__}",
                            user_id=str(current_user.id),
                            details={
                                "resource_type": resource_type,
                                "resource_id": resource_id,
                                "username": getattr(current_user, 'username', None)
                            }
                        )
                raise
        
        return wrapper
    return decorator


def log_database_operation(
    operation_name: Optional[str] = None,
    log_success: bool = False,  # 默认不记录成功（避免日志过多）
    log_failure: bool = True
):
    """
    数据库操作日志装饰器
    
    用于 CRUD 层的函数，记录数据库操作。
    
    Args:
        operation_name: 操作名称
        log_success: 是否记录成功操作（默认 False，避免日志过多）
        log_failure: 是否记录失败操作
    
    用法:
        @log_database_operation(operation_name="创建文档记录")
        async def create_document(db: AsyncIOMotorDatabase, ...):
            # CRUD 操作
            return document
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            db = kwargs.get('db') or (args[0] if args else None)
            
            try:
                result = await func(*args, **kwargs)
                
                if log_success and db:
                    await log_event(
                        db=db,
                        level=LogLevel.DEBUG,
                        message=f"Database operation: {op_name} succeeded",
                        source=f"crud.{func.__module__}.{func.__name__}"
                    )
                
                return result
                
            except Exception as e:
                if log_failure and db:
                    await log_event(
                        db=db,
                        level=LogLevel.ERROR,
                        message=f"Database operation: {op_name} failed: {str(e)}",
                        source=f"crud.{func.__module__}.{func.__name__}",
                        details={
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        }
                    )
                raise
        
        return wrapper
    return decorator


class LogContext:
    """
    日志上下文管理器（简化版）
    
    用于在一个代码块中自动记录开始和结束。
    
    用法:
        async with LogContext(db, "批量处理文档", current_user) as ctx:
            # 执行操作
            ctx.add_detail("processed_count", 10)
    """
    
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        operation_name: str,
        current_user: Any = None,
        log_start: bool = False,
        log_end: bool = True
    ):
        self.db = db
        self.operation_name = operation_name
        self.current_user = current_user
        self.log_start = log_start
        self.log_end = log_end
        self.start_time = None
        self.details = {}
    
    async def __aenter__(self):
        self.start_time = time.time()
        
        if self.log_start:
            await log_event(
                db=self.db,
                level=LogLevel.INFO,
                message=f"{self.operation_name} started",
                source="context_manager",
                user_id=str(self.current_user.id) if self.current_user else None
            )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type is not None:
            # 发生异常
            if self.log_end:
                await log_event(
                    db=self.db,
                    level=LogLevel.ERROR,
                    message=f"{self.operation_name} failed: {str(exc_val)}",
                    source="context_manager",
                    user_id=str(self.current_user.id) if self.current_user else None,
                    details={
                        **self.details,
                        "duration_seconds": round(duration, 3),
                        "error_type": exc_type.__name__ if exc_type else None
                    }
                )
        else:
            # 正常完成
            if self.log_end:
                await log_event(
                    db=self.db,
                    level=LogLevel.INFO,
                    message=f"{self.operation_name} completed",
                    source="context_manager",
                    user_id=str(self.current_user.id) if self.current_user else None,
                    details={
                        **self.details,
                        "duration_seconds": round(duration, 3)
                    }
                )
        
        return False  # 不抑制异常
    
    def add_detail(self, key: str, value: Any):
        """添加额外的详细信息到日志"""
        self.details[key] = value


# 便捷的日志记录函数

async def log_info(db: AsyncIOMotorDatabase, message: str, **kwargs):
    """快速记录 INFO 级别日志"""
    await log_event(db=db, level=LogLevel.INFO, message=message, **kwargs)


async def log_warning(db: AsyncIOMotorDatabase, message: str, **kwargs):
    """快速记录 WARNING 级别日志"""
    await log_event(db=db, level=LogLevel.WARNING, message=message, **kwargs)


async def log_error(db: AsyncIOMotorDatabase, message: str, **kwargs):
    """快速记录 ERROR 级别日志"""
    await log_event(db=db, level=LogLevel.ERROR, message=message, **kwargs)
