"""
應用啟動時的智能預熱機制
實現背景預熱，避免用戶首次使用延遲
"""
import asyncio
import logging
from typing import Optional
from fastapi import BackgroundTasks

from app.services.embedding_service import embedding_service
from app.services.vector_db_service import vector_db_service
from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.INFO).get_logger()

class ApplicationPreloader:
    """應用程序預熱器"""
    
    def __init__(self):
        self.preload_enabled = True  # 可通過環境變數控制
        self.max_preload_time = 30   # 最大預熱時間（秒）
    
    async def startup_preload(self) -> None:
        """啟動時預熱關鍵組件"""
        if not self.preload_enabled:
            logger.info("預熱功能已禁用")
            return
        
        logger.info("開始應用程序預熱...")
        
        try:
            # 並行執行預熱任務
            await asyncio.wait_for(
                asyncio.gather(
                    self._preload_embedding_model(),
                    self._initialize_vector_db(),
                    return_exceptions=True
                ),
                timeout=self.max_preload_time
            )
            logger.info("應用程序預熱完成")
        except asyncio.TimeoutError:
            logger.warning(f"預熱超時 ({self.max_preload_time}s)，將在運行時按需加載")
        except Exception as e:
            logger.error(f"預熱過程中發生錯誤: {e}")
    
    async def _preload_embedding_model(self) -> None:
        """預熱 Embedding 模型"""
        try:
            logger.info("開始預熱 Embedding 模型...")
            if not embedding_service._model_loaded:
                embedding_service._load_model()
                logger.info("Embedding 模型預熱成功")
            else:
                logger.info("Embedding 模型已經加載")
        except Exception as e:
            logger.error(f"Embedding 模型預熱失敗: {e}")
    
    async def _initialize_vector_db(self) -> None:
        """初始化向量數據庫"""
        try:
            logger.info("開始初始化向量數據庫...")
            
            # 檢查集合是否存在
            stats = await vector_db_service.get_collection_stats()
            if 'error' in stats and '集合未初始化' in stats.get('error', ''):
                # 確保模型已加載以獲取向量維度
                if not embedding_service._model_loaded:
                    await self._preload_embedding_model()
                
                vector_dimension = embedding_service.vector_dimension
                if vector_dimension:
                    vector_db_service.create_collection(vector_dimension)
                    logger.info("向量數據庫初始化成功")
                else:
                    logger.warning("無法獲取向量維度，跳過向量數據庫初始化")
            else:
                logger.info("向量數據庫已經就緒")
        except Exception as e:
            logger.error(f"向量數據庫初始化失敗: {e}")

# 創建全局預熱器實例
app_preloader = ApplicationPreloader()

async def preload_on_startup() -> None:
    """FastAPI 啟動事件處理器"""
    await app_preloader.startup_preload() 