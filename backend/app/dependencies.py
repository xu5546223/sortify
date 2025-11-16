"""
依賴注入配置

統一管理應用程式的依賴注入，提供一致的服務獲取方式。

設計原則：
- 有狀態服務（如資料庫連接）使用單例模式
- 無狀態服務每次創建新實例
- 配置對象使用全局單例
"""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from .db.mongodb_utils import db_manager, get_db
from .services.document.document_processing_service import DocumentProcessingService
from .core.config import settings, Settings
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.vector.vector_db_service import vector_db_service, VectorDatabaseService
from app.services.document.document_tasks_service import DocumentTasksService


# ==================== 服務註冊表 ====================
# 用於管理單例服務實例

class ServiceRegistry:
    """
    服務註冊表 - 管理全局單例服務
    
    用於需要保持狀態或昂貴初始化的服務。
    """
    _instances = {
        "unified_ai_service": unified_ai_service_simplified,
        "vector_db_service": vector_db_service,
    }
    
    @classmethod
    def get_service(cls, service_name: str):
        """獲取已註冊的服務實例"""
        return cls._instances.get(service_name)
    
    @classmethod
    def register_service(cls, service_name: str, instance):
        """註冊新的服務實例"""
        cls._instances[service_name] = instance


# ==================== 數據庫依賴 ====================

async def get_database() -> AsyncIOMotorDatabase:
    """
    獲取數據庫連接
    
    用於 FastAPI 路由的依賴注入。
    """
    return await get_db()


# ==================== AI 服務依賴 ====================

def get_unified_ai_service():
    """
    獲取統一 AI 服務實例（單例）
    
    Returns:
        統一的 AI 服務實例
    """
    return ServiceRegistry.get_service("unified_ai_service")


# ==================== 文檔服務依賴 ====================

def get_document_processing_service() -> DocumentProcessingService:
    """
    獲取文檔處理服務實例（每次創建新實例）
    
    DocumentProcessingService 是無狀態的，每次創建新實例。
    
    Returns:
        文檔處理服務實例
    """
    return DocumentProcessingService()


def get_document_tasks_service() -> DocumentTasksService:
    """
    獲取文檔任務服務實例（每次創建新實例）
    
    DocumentTasksService 用於後台任務處理。
    
    Returns:
        文檔任務服務實例
    """
    return DocumentTasksService()


# ==================== 向量資料庫服務依賴 ====================

def get_vector_db_service() -> VectorDatabaseService:
    """
    獲取向量資料庫服務實例（單例）
    
    向量資料庫服務維護連接狀態，使用單例模式。
    
    Returns:
        向量資料庫服務實例
    """
    return ServiceRegistry.get_service("vector_db_service")


# ==================== 配置依賴 ====================

async def get_settings() -> Settings:
    """
    獲取應用程式配置實例（全局單例）
    
    Returns:
        應用程式配置
    """
    return settings


# ==================== 工具函數 ====================

def get_service_health() -> dict:
    """
    獲取所有已註冊服務的健康狀態
    
    用於系統監控和診斷。
    
    Returns:
        服務健康狀態字典
    """
    health_status = {}
    
    for service_name, instance in ServiceRegistry._instances.items():
        # 檢查服務是否有健康檢查方法
        if hasattr(instance, 'health_check'):
            try:
                health_status[service_name] = instance.health_check()
            except Exception as e:
                health_status[service_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        else:
            health_status[service_name] = {
                "status": "running",
                "note": "No health check available"
            }
    
    return health_status