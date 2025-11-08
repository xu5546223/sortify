"""
後台任務管理器
"""

import asyncio
import uuid
import logging
from typing import Dict, Optional, Callable, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.background_task_models import (
    BackgroundTask,
    TaskStatus,
    TaskType,
    TaskProgressUpdate
)
from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.INFO).get_logger()

COLLECTION_NAME = "background_tasks"


class BackgroundTaskManager:
    """後台任務管理器"""
    
    def __init__(self):
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_task(
        self,
        db: AsyncIOMotorDatabase,
        task_type: TaskType,
        user_id: str,
        total_items: int = 0
    ) -> str:
        """
        創建新任務
        
        Args:
            db: 數據庫連接
            task_type: 任務類型
            user_id: 用戶ID
            total_items: 總項目數
            
        Returns:
            str: 任務ID
        """
        task_id = str(uuid.uuid4())
        
        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            user_id=user_id,
            status=TaskStatus.PENDING,
            total_items=total_items
        )
        
        collection = db[COLLECTION_NAME]
        await collection.insert_one(task.model_dump())
        
        logger.info(f"創建後台任務: {task_id}, 類型: {task_type}, 用戶: {user_id}")
        
        return task_id
    
    async def update_task_status(
        self,
        db: AsyncIOMotorDatabase,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None
    ):
        """更新任務狀態"""
        collection = db[COLLECTION_NAME]
        
        update_data = {
            "status": status.value
        }
        
        if status == TaskStatus.RUNNING and not await self._get_task_field(db, task_id, "started_at"):
            update_data["started_at"] = datetime.utcnow()
        
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            update_data["completed_at"] = datetime.utcnow()
        
        if error_message:
            update_data["error_message"] = error_message
        
        await collection.update_one(
            {"task_id": task_id},
            {"$set": update_data}
        )
        
        logger.info(f"任務 {task_id} 狀態更新為: {status}")
    
    async def update_task_progress(
        self,
        db: AsyncIOMotorDatabase,
        task_id: str,
        progress: int,
        current_step: str,
        completed_items: int
    ):
        """更新任務進度"""
        collection = db[COLLECTION_NAME]
        
        await collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": progress,
                "current_step": current_step,
                "completed_items": completed_items
            }}
        )
        
        logger.debug(f"任務 {task_id} 進度: {progress}%, 步驟: {current_step}")
    
    async def set_task_result(
        self,
        db: AsyncIOMotorDatabase,
        task_id: str,
        result: Dict[str, Any]
    ):
        """設置任務結果"""
        collection = db[COLLECTION_NAME]
        
        await collection.update_one(
            {"task_id": task_id},
            {"$set": {"result": result}}
        )
        
        logger.info(f"任務 {task_id} 結果已設置")
    
    async def get_task_status(
        self,
        db: AsyncIOMotorDatabase,
        task_id: str
    ) -> Optional[BackgroundTask]:
        """獲取任務狀態"""
        collection = db[COLLECTION_NAME]
        
        task_doc = await collection.find_one({"task_id": task_id})
        
        if not task_doc:
            return None
        
        task_doc.pop('_id', None)
        return BackgroundTask(**task_doc)
    
    async def _get_task_field(
        self,
        db: AsyncIOMotorDatabase,
        task_id: str,
        field: str
    ) -> Any:
        """獲取任務的特定字段"""
        collection = db[COLLECTION_NAME]
        task_doc = await collection.find_one(
            {"task_id": task_id},
            {field: 1}
        )
        return task_doc.get(field) if task_doc else None
    
    def start_background_task(
        self,
        task_id: str,
        coro: Callable
    ):
        """
        啟動後台任務
        
        Args:
            task_id: 任務ID
            coro: 協程函數
        """
        task = asyncio.create_task(coro)
        self._running_tasks[task_id] = task
        
        # 任務完成後清理
        def cleanup(t):
            self._running_tasks.pop(task_id, None)
        
        task.add_done_callback(cleanup)
        
        logger.info(f"後台任務 {task_id} 已啟動")
    
    async def cleanup_old_tasks(
        self,
        db: AsyncIOMotorDatabase,
        days: int = 7
    ):
        """清理舊任務記錄"""
        from datetime import timedelta
        
        collection = db[COLLECTION_NAME]
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = await collection.delete_many({
            "created_at": {"$lt": cutoff_date},
            "status": {"$in": [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]}
        })
        
        logger.info(f"清理了 {result.deleted_count} 個舊任務記錄")


# 全局實例
background_task_manager = BackgroundTaskManager()

