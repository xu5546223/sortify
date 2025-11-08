"""
向量化任务队列
用于管理文档向量化的并发和顺序
"""

import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid

from app.core.logging_utils import AppLogger, log_event, LogLevel

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class VectorizationQueue:
    """
    向量化任务队列
    
    特性：
    1. 控制并发数量（最多同时处理 N 个文件）
    2. 按顺序处理任务（FIFO）
    3. 提供任务状态查询
    4. 支持任务批量处理优化
    """
    
    def __init__(self, max_concurrent_tasks: int = 2):
        """
        初始化队列
        
        Args:
            max_concurrent_tasks: 最多同时处理的任务数量
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.completed_tasks: List[Dict[str, Any]] = []
        self.processing = False
        self._worker_tasks: List[asyncio.Task] = []
        
        logger.info(f"向量化队列初始化完成，最大并发数: {max_concurrent_tasks}")
    
    async def add_task(self, document_id: str, db: AsyncIOMotorDatabase) -> None:
        """
        添加向量化任务到队列
        
        Args:
            document_id: 文档ID（字符串格式）
            db: 数据库连接
        """
        task_info = {
            "document_id": document_id,
            "db": db,
            "added_at": datetime.now(),
            "status": "queued"
        }
        
        await self.queue.put(task_info)
        logger.info(f"✅ 文档 {document_id} 已加入向量化队列，当前队列长度: {self.queue.qsize()}")
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"文档 {document_id} 加入向量化队列",
            source="vectorization_queue.add_task",
            details={
                "document_id": document_id,
                "queue_size": self.queue.qsize(),
                "active_tasks": len(self.active_tasks)
            }
        )
        
        # 如果处理器未运行，启动它
        if not self.processing:
            await self.start_processing()
    
    async def start_processing(self) -> None:
        """启动任务处理器"""
        if self.processing:
            logger.debug("任务处理器已在运行")
            return
        
        self.processing = True
        logger.info(f"🚀 启动向量化任务处理器，并发数: {self.max_concurrent_tasks}")
        
        # 创建多个 worker
        self._worker_tasks = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_concurrent_tasks)
        ]
    
    async def _worker(self, worker_id: int) -> None:
        """
        任务处理 worker
        
        Args:
            worker_id: Worker ID
        """
        logger.info(f"Worker {worker_id} 启动")
        
        while self.processing:
            try:
                # 从队列获取任务（超时机制）
                task_info = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=5.0
                )
                
                document_id = task_info["document_id"]
                db = task_info["db"]
                
                # 更新任务状态
                self.active_tasks[document_id] = {
                    **task_info,
                    "status": "processing",
                    "worker_id": worker_id,
                    "started_at": datetime.now()
                }
                
                logger.info(f"⚙️ Worker {worker_id} 开始处理文档 {document_id}")
                
                # 执行向量化
                from app.services.document.semantic_summary_service import semantic_summary_service
                
                result = await semantic_summary_service.batch_process_documents(
                    db=db,
                    document_ids=[document_id]
                )
                
                # 记录完成
                completed_info = {
                    **self.active_tasks[document_id],
                    "status": "completed",
                    "completed_at": datetime.now(),
                    "result": result
                }
                
                self.completed_tasks.append(completed_info)
                del self.active_tasks[document_id]
                
                logger.info(f"✅ Worker {worker_id} 完成文档 {document_id} 的向量化")
                
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"文档 {document_id} 向量化完成",
                    source="vectorization_queue.worker",
                    details={
                        "document_id": document_id,
                        "worker_id": worker_id,
                        "result": result
                    }
                )
                
                # 标记任务完成
                self.queue.task_done()
                
            except asyncio.TimeoutError:
                # 队列为空，继续等待
                continue
            except Exception as e:
                logger.error(f"❌ Worker {worker_id} 处理失败: {e}", exc_info=True)
                
                if document_id in self.active_tasks:
                    failed_info = {
                        **self.active_tasks[document_id],
                        "status": "failed",
                        "error": str(e),
                        "failed_at": datetime.now()
                    }
                    self.completed_tasks.append(failed_info)
                    del self.active_tasks[document_id]
                
                self.queue.task_done()
    
    async def stop_processing(self) -> None:
        """停止任务处理器"""
        if not self.processing:
            return
        
        logger.info("停止向量化任务处理器")
        self.processing = False
        
        # 等待所有 worker 完成
        for task in self._worker_tasks:
            task.cancel()
        
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks = []
    
    def get_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "processing": self.processing,
            "queue_size": self.queue.qsize(),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "max_concurrent": self.max_concurrent_tasks,
            "active_task_ids": list(self.active_tasks.keys())
        }


# 全局向量化队列实例
vectorization_queue = VectorizationQueue(max_concurrent_tasks=2)

