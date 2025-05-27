from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...dependencies import get_db
from ...models.log_models import LogEntryPublic, LogLevel
from ...models.user_models import User # Import User
from ...core.security import get_current_active_user # Import auth dependency
from ...crud import crud_logs

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
    # TODO: Implement admin role check to allow viewing other users' logs
    # For now, if user_id is provided, it must match the current user.
    if user_id and user_id != user_id_to_filter:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權查看其他使用者的日誌"
        )
    
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
    # TODO: Implement admin role check
    if user_id and user_id != user_id_to_filter:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權計算其他使用者的日誌數量"
        )

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
    return count 