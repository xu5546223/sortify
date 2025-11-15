from datetime import datetime, timedelta, UTC
from typing import List, Optional, Dict, Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from ..models.dashboard_models import SystemStats, ActivityItem
from ..models.document_models import DocumentStatus
# from ..models.user_models import ConnectedDeviceDB # No longer directly used by name, but collection is
from ..models.log_models import LogLevel, LogEntryDB # Assuming LogEntryDB has 'id'
from .crud_documents import DOCUMENT_COLLECTION
from .crud_users import DEVICE_COLLECTION_NAME as CONNECTED_DEVICES_COLLECTION
from .crud_logs import LOGS_COLLECTION


async def get_system_stats(db: AsyncIOMotorDatabase) -> SystemStats:
    """
    從資料庫聚合系統統計數據。
    """
    stats = SystemStats()

    # 文件統計
    stats.total_documents = await db[DOCUMENT_COLLECTION].count_documents({})
    stats.processed_documents = await db[DOCUMENT_COLLECTION].count_documents({
        "status": {"$in": [DocumentStatus.COMPLETED.value, DocumentStatus.TEXT_EXTRACTED.value, DocumentStatus.ANALYSIS_COMPLETED.value]}
    })
    stats.pending_documents = await db[DOCUMENT_COLLECTION].count_documents({
        "status": {"$in": [DocumentStatus.UPLOADED.value, DocumentStatus.PENDING_EXTRACTION.value, DocumentStatus.PENDING_ANALYSIS.value]}
    })

    # 裝置/使用者統計
    stats.total_registered_devices = await db[CONNECTED_DEVICES_COLLECTION].count_documents({})
    # 假設 is_active 標記了當前連線的裝置
    stats.active_connections = await db[CONNECTED_DEVICES_COLLECTION].count_documents({"is_active": True})


    # AI 相關統計 (如果後續有記錄 token 的 collection)
    # stats.ai_analyses_triggered = await db["ai_usage_logs"].count_documents({"type": "analysis"})
    # token_sum_result = await db["ai_usage_logs"].aggregate([
    #     {"$group": {"_id": None, "total_tokens": {"$sum": "$tokens_consumed"}}}
    # ]).to_list(length=1)
    # if token_sum_result:
    #     stats.ai_tokens_consumed_total = token_sum_result[0].get("total_tokens")

    # 儲存空間統計 (需要實際讀取文件大小)
    total_size_bytes = 0
    # Using aggregation framework for potentially better performance on large datasets
    pipeline = [
        {"$group": {"_id": None, "totalSize": {"$sum": "$size"}}}
    ]
    size_aggregation_result = await db[DOCUMENT_COLLECTION].aggregate(pipeline).to_list(length=1)
    if size_aggregation_result and size_aggregation_result[0].get("totalSize") is not None:
        total_size_bytes = size_aggregation_result[0]["totalSize"]
    
    stats.total_storage_used_mb = round(total_size_bytes / (1024 * 1024), 2) if total_size_bytes > 0 else 0.0

    # 日誌統計
    twenty_four_hours_ago = datetime.now(UTC) - timedelta(hours=24)
    stats.error_logs_last_24h = await db[LOGS_COLLECTION].count_documents({
        "level": LogLevel.ERROR.value,
        "timestamp": {"$gte": twenty_four_hours_ago}
    })

    return stats

async def get_recent_activities(
    db: AsyncIOMotorDatabase,
    skip: int = 0,
    limit: int = 20,
    user_id: Optional[str] = None, # 篩選特定使用者的活動
    activity_types_filter: Optional[List[str]] = None # 篩選特定類型的活動 (對應 log_entry.source or module.function)
) -> List[ActivityItem]:
    """
    獲取最近的活動列表，主要從日誌中提取。
    """
    query: Dict[str, Any] = {}
    
    if user_id:
        query["user_id"] = user_id
    
    if activity_types_filter:
        # This is a simplified filter. A more robust solution might involve a dedicated 'activity_type' field in logs
        # or a more complex query using $or for source, module, function combinations.
        # For now, let's assume activity_types_filter contains potential 'source' values or 'module.function' strings.
        # This part would need careful design based on how activity types are logged.
        # Example: query["source"] = {"$in": activity_types_filter} 
        # Or, if it's based on a combination:
        # query["$or"] = [{"source": act_type} for act_type in activity_types_filter] # Simplified
        pass # Placeholder for more complex activity_type filtering
    
    log_cursor = db[LOGS_COLLECTION].find(query).sort("timestamp", DESCENDING).skip(skip).limit(limit)
    log_entries_raw = await log_cursor.to_list(length=limit)
    
    activities: List[ActivityItem] = []
    for log_raw in log_entries_raw:
        log_entry = LogEntryDB(**log_raw) 
        
        activity_type = "general_log"
        if log_entry.source:
            activity_type = log_entry.source
        elif log_entry.module and log_entry.function:
            activity_type = f"{log_entry.module}.{log_entry.function}"
        
        related_item_id_val = None
        if log_entry.details:
            related_item_id_val = log_entry.details.get("document_id") or \
                                  log_entry.details.get("user_id") or \
                                  log_entry.details.get("device_id") or \
                                  log_entry.details.get("id") # Generic id from details

        activities.append(
            ActivityItem(
                id=log_entry.id, 
                timestamp=log_entry.timestamp,
                activity_type=activity_type,
                summary=log_entry.message,
                user_id=log_entry.user_id,
                device_id=log_entry.device_id,
                related_item_id=str(related_item_id_val) if related_item_id_val else None,
                details=log_entry.details
            )
        )
    return activities

async def count_recent_activities(
    db: AsyncIOMotorDatabase,
    user_id: Optional[str] = None,
    activity_types_filter: Optional[List[str]] = None
) -> int:
    """
    計算符合篩選條件的"活動"總數。
    """
    query: Dict[str, Any] = {}
    if user_id:
        query["user_id"] = user_id

    # if activity_types_filter: # Mirroring the logic in get_recent_activities
        # pass # Placeholder for more complex activity_type filtering

    count = await db[LOGS_COLLECTION].count_documents(query)
    return count 