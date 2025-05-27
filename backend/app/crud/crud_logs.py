import re # 新增導入 re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from ..models.log_models import LogEntryCreate, LogEntryDB, LogLevel

LOGS_COLLECTION = "logs"

async def create_log_entry(db: AsyncIOMotorDatabase, log_entry_data: LogEntryCreate) -> LogEntryDB:
    """
    在資料庫中創建一個新的日誌條目。
    實際的日誌記錄應該通過一個集中的日誌服務或工具來完成，
    這裡的 CRUD 主要是為了能夠手動或特定情況上記錄，以及供後續查詢。
    """
    log_entry_db = LogEntryDB(**log_entry_data.model_dump())
    await db[LOGS_COLLECTION].insert_one(log_entry_db.model_dump(by_alias=True))
    return log_entry_db

async def get_log_entries(
    db: AsyncIOMotorDatabase,
    skip: int = 0,
    limit: int = 100,
    level: Optional[LogLevel] = None,
    source: Optional[str] = None,
    module: Optional[str] = None,
    function: Optional[str] = None,
    user_id: Optional[str] = None,
    device_id: Optional[str] = None,
    request_id: Optional[str] = None,
    message_contains: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> List[LogEntryDB]:
    """
    從資料庫獲取日誌條目列表，支持篩選和分頁。
    """
    query: Dict[str, Any] = {}
    if level:
        query["level"] = level.value
    if source:
        query["source"] = source
    if module:
        query["module"] = module
    if function:
        query["function"] = function
    if user_id:
        query["user_id"] = user_id
    if device_id:
        query["device_id"] = device_id
    if request_id:
        query["request_id"] = request_id
    if message_contains:
        query["message"] = {"$regex": re.escape(message_contains), "$options": "i"} # 使用 re.escape

    time_filter = {}
    if start_time:
        time_filter["$gte"] = start_time
    if end_time:
        time_filter["$lte"] = end_time
    if time_filter:
        query["timestamp"] = time_filter

    cursor = db[LOGS_COLLECTION].find(query).sort("timestamp", DESCENDING).skip(skip).limit(limit)
    log_entries = await cursor.to_list(length=limit)
    return [LogEntryDB(**log) for log in log_entries]

async def count_log_entries(
    db: AsyncIOMotorDatabase,
    level: Optional[LogLevel] = None,
    source: Optional[str] = None,
    module: Optional[str] = None,
    function: Optional[str] = None,
    user_id: Optional[str] = None,
    device_id: Optional[str] = None,
    request_id: Optional[str] = None,
    message_contains: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> int:
    """
    計算符合篩選條件的日誌條目總數。
    """
    query: Dict[str, Any] = {}
    if level:
        query["level"] = level.value
    if source:
        query["source"] = source
    if module:
        query["module"] = module
    if function:
        query["function"] = function
    if user_id:
        query["user_id"] = user_id
    if device_id:
        query["device_id"] = device_id
    if request_id:
        query["request_id"] = request_id
    if message_contains:
        query["message"] = {"$regex": re.escape(message_contains), "$options": "i"} # 使用 re.escape

    time_filter = {}
    if start_time:
        time_filter["$gte"] = start_time
    if end_time:
        time_filter["$lte"] = end_time
    if time_filter:
        query["timestamp"] = time_filter
        
    count = await db[LOGS_COLLECTION].count_documents(query)
    return count 