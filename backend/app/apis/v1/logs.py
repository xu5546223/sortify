from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...dependencies import get_db
from ...models.log_models import LogEntryPublic, LogLevel # LogEntryDB is for DB, LogEntryPublic for API response
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
    skip: int = Query(0, ge=0, description="跳過的記錄數量"),
    limit: int = Query(100, ge=1, le=500, description="返回的記錄數量上限"),
    level: Optional[LogLevel] = Query(None, description="日誌級別篩選"),
    source: Optional[str] = Query(None, description="日誌來源篩選 (例如: documents_api)"),
    module: Optional[str] = Query(None, description="模塊名稱篩選"),
    function: Optional[str] = Query(None, description="函數名稱篩選"),
    user_id: Optional[str] = Query(None, description="用戶ID篩選"),
    device_id: Optional[str] = Query(None, description="裝置ID篩選"),
    request_id: Optional[str] = Query(None, description="請求ID篩選"),
    message_contains: Optional[str] = Query(None, description="日誌訊息包含的文字 (不區分大小寫)"),
    start_time: Optional[datetime] = Query(None, description="開始時間篩選 (ISO 8601 格式)"),
    end_time: Optional[datetime] = Query(None, description="結束時間篩選 (ISO 8601 格式)"),
):
    logs_db_list = await crud_logs.get_log_entries(
        db=db,
        skip=skip,
        limit=limit,
        level=level,
        source=source,
        module=module,
        function=function,
        user_id=user_id,
        device_id=device_id,
        request_id=request_id,
        message_contains=message_contains,
        start_time=start_time,
        end_time=end_time,
    )
    # Convert LogEntryDB to LogEntryPublic if necessary, or rely on Pydantic's response_model conversion
    # For now, assuming LogEntryDB can be directly used if LogEntryPublic is compatible or response_model handles it.
    # If LogEntryDB has fields not in LogEntryPublic, explicit conversion or aliasing in LogEntryPublic is needed.
    return [LogEntryPublic(**log.model_dump()) for log in logs_db_list]

@router.get(
    "/count",
    response_model=int,
    summary="獲取日誌總數",
    description="根據提供的篩選條件計算日誌條目的總數。"
)
async def count_logs(
    db: AsyncIOMotorDatabase = Depends(get_db),
    level: Optional[LogLevel] = Query(None, description="日誌級別篩選"),
    source: Optional[str] = Query(None, description="日誌來源篩選"),
    module: Optional[str] = Query(None, description="模塊名稱篩選"),
    function: Optional[str] = Query(None, description="函數名稱篩選"),
    user_id: Optional[str] = Query(None, description="用戶ID篩選"),
    device_id: Optional[str] = Query(None, description="裝置ID篩選"),
    request_id: Optional[str] = Query(None, description="請求ID篩選"),
    message_contains: Optional[str] = Query(None, description="日誌訊息包含的文字 (不區分大小寫)"),
    start_time: Optional[datetime] = Query(None, description="開始時間篩選 (ISO 8601 格式)"),
    end_time: Optional[datetime] = Query(None, description="結束時間篩選 (ISO 8601 格式)"),
):
    count = await crud_logs.count_log_entries(
        db=db,
        level=level,
        source=source,
        module=module,
        function=function,
        user_id=user_id,
        device_id=device_id,
        request_id=request_id,
        message_contains=message_contains,
        start_time=start_time,
        end_time=end_time,
    )
    return count 