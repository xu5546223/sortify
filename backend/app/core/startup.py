"""
應用啟動時的智能預熱機制
實現背景預熱，避免用戶首次使用延遲
"""
import asyncio
import logging
from typing import Optional
from fastapi import BackgroundTasks

from app.services.vector.embedding_service import embedding_service
from app.services.vector.vector_db_service import vector_db_service
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
            
            stats = await vector_db_service.get_collection_stats()
            error_message = stats.get('error')

            # 更寬鬆的判斷條件，檢查是否包含關鍵字
            needs_initialization = False
            if error_message:
                if "未初始化" in error_message or "not initialized" in error_message.lower() or "不可用" in error_message:
                    needs_initialization = True
            
            if needs_initialization:
                logger.info(f"檢測到向量數據庫集合 '{vector_db_service.collection_name}' 需要初始化 (原始錯誤: '{error_message}')，準備創建...")
                if not embedding_service._model_loaded:
                    logger.info("Embedding 模型未加載，嘗試在向量庫初始化前加載...")
                    await self._preload_embedding_model()
                
                vector_dimension = embedding_service.vector_dimension
                if vector_dimension:
                    logger.info(f"獲取到向量維度: {vector_dimension}，開始創建集合 '{vector_db_service.collection_name}'...")
                    vector_db_service.create_collection(vector_dimension)
                    logger.info(f"向量數據庫集合 '{vector_db_service.collection_name}' 初始化成功。")
                else:
                    logger.warning("無法獲取向量維度，跳過向量數據庫集合創建。")
            elif error_message: # 如果有其他錯誤，但不是明確的未初始化錯誤
                logger.error(f"獲取向量數據庫統計信息時返回了未預期的錯誤。完整統計信息: {stats}")
            else: # 沒有錯誤，表示已就緒
                logger.info(f"向量數據庫集合 '{vector_db_service.collection_name}' 已經就緒。統計信息: {stats}")
        except Exception as e:
            logger.error(f"向量數據庫初始化過程中發生未預期錯誤: {e}", exc_info=True)

# 創建全局預熱器實例
app_preloader = ApplicationPreloader()

async def preload_on_startup() -> None:
    """FastAPI 啟動事件處理器"""
    await app_preloader.startup_preload() 