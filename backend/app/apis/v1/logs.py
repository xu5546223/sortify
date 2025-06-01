from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...dependencies import get_db
from ...models.log_models import LogEntryPublic, LogLevel
from ...models.user_models import User
from ...core.security import get_current_active_user
from ...crud import crud_logs
from ...core.logging_utils import log_event # Added
from ...models.log_models import LogLevel # Added


router = APIRouter()

@router.get(
    "/",
    response_model=List[LogEntryPublic],
    summary="獲取日誌列表",
    description="根據提供的篩選條件獲取日誌條目列表，支持分頁。"
)
async def list_logs(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user), # Add auth dependency
    skip: int = Query(0, ge=0, description="跳過的記錄數量"),
    limit: int = Query(100, ge=1, le=500, description="返回的記錄數量上限"),
    level: Optional[LogLevel] = Query(None, description="日誌級別篩選"),
    source: Optional[str] = Query(None, description="日誌來源篩選 (例如: documents_api)"),
    module: Optional[str] = Query(None, description="模塊名稱篩選"),
    function: Optional[str] = Query(None, description="函數名稱篩選"),
    user_id: Optional[str] = Query(None, description="用戶ID篩選 (目前僅限當前用戶或管理員)"),
    device_id: Optional[str] = Query(None, description="裝置ID篩選"),
    request_id: Optional[str] = Query(None, description="請求ID篩選"),
    message_contains: Optional[str] = Query(None, description="日誌訊息包含的文字 (不區分大小寫)"),
    start_time: Optional[datetime] = Query(None, description="開始時間篩選 (ISO 8601 格式)"),
    end_time: Optional[datetime] = Query(None, description="結束時間篩選 (ISO 8601 格式)"),
):
    user_id_to_filter = str(current_user.id)
    request_id_val = None # Not available from current dependencies, would need Request object

    # Log unauthorized access attempt if user_id is for someone else and current_user is not admin
    # Assuming current_user.is_admin check would be here if admin functionality was complete
    if user_id and user_id != user_id_to_filter:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="Unauthorized attempt to list logs for another user.",
            source="api.logs.list_logs",
            user_id=str(current_user.id),
            request_id=request_id_val,
            details={"target_user_id": user_id, "current_user_id": user_id_to_filter}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view logs for the specified user." # User-friendly message
        )
    
    applied_filters = {
        "level": level.value if level else None, # Log enum value
        "source": source,
        "module": module,
        "function": function,
        "user_id_filter": user_id_to_filter, # This is the actual user_id being filtered by
        "device_id": device_id,
        "request_id_filter": request_id, # This is the filter criteria, not the current request's ID
        "message_contains": message_contains,
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None,
        "skip": skip,
        "limit": limit
    }

    logs_db_list = await crud_logs.get_log_entries(
        db=db,
        skip=skip,
        limit=limit,
        level=level,
        source=source,
        module=module,
        function=function,
        user_id=user_id_to_filter, # Always filter by current user or validated user_id
        device_id=device_id,
        request_id=request_id,
        message_contains=message_contains,
        start_time=start_time,
        end_time=end_time,
    )

    await log_event(
        db=db,
        level=LogLevel.INFO,
        message="Log entries retrieved.",
        source="api.logs.list_logs",
        user_id=str(current_user.id),
        request_id=request_id_val, # This would be the current request's ID if available
        details={
            "filters_applied": applied_filters,
            "retrieved_count": len(logs_db_list)
        }
    )
    return [LogEntryPublic(**log.model_dump()) for log in logs_db_list]

@router.get(
    "/count",
    response_model=int,
    summary="獲取日誌總數",
    description="根據提供的篩選條件計算日誌條目的總數。"
)
async def count_logs(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user), # Add auth dependency
    level: Optional[LogLevel] = Query(None, description="日誌級別篩選"),
    source: Optional[str] = Query(None, description="日誌來源篩選"),
    module: Optional[str] = Query(None, description="模塊名稱篩選"),
    function: Optional[str] = Query(None, description="函數名稱篩選"),
    user_id: Optional[str] = Query(None, description="用戶ID篩選 (目前僅限當前用戶或管理員)"),
    device_id: Optional[str] = Query(None, description="裝置ID篩選"),
    request_id: Optional[str] = Query(None, description="請求ID篩選"),
    message_contains: Optional[str] = Query(None, description="日誌訊息包含的文字 (不區分大小寫)"),
    start_time: Optional[datetime] = Query(None, description="開始時間篩選 (ISO 8601 格式)"),
    end_time: Optional[datetime] = Query(None, description="結束時間篩選 (ISO 8601 格式)"),
):
    user_id_to_filter = str(current_user.id)
    request_id_val = None # Not available from current dependencies

    # Log unauthorized access attempt
    if user_id and user_id != user_id_to_filter:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="Unauthorized attempt to count logs for another user.",
            source="api.logs.count_logs",
            user_id=str(current_user.id),
            request_id=request_id_val,
            details={"target_user_id": user_id, "current_user_id": user_id_to_filter}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to count logs for the specified user." # User-friendly message
        )

    applied_filters = {
        "level": level.value if level else None,
        "source": source,
        "module": module,
        "function": function,
        "user_id_filter": user_id_to_filter,
        "device_id": device_id,
        "request_id_filter": request_id,
        "message_contains": message_contains,
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None
    }

    count = await crud_logs.count_log_entries(
        db=db,
        level=level,
        source=source,
        module=module,
        function=function,
        user_id=user_id_to_filter, # Always filter by current user or validated user_id
        device_id=device_id,
        request_id=request_id,
        message_contains=message_contains,
        start_time=start_time,
        end_time=end_time,
    )

    await log_event(
        db=db,
        level=LogLevel.DEBUG,
        message="Log entry count retrieved.",
        source="api.logs.count_logs",
        user_id=str(current_user.id),
        request_id=request_id_val,
        details={
            "filters_applied": applied_filters,
            "retrieved_count": count
        }
    )
    return count 