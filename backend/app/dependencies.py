from motor.motor_asyncio import AsyncIOMotorDatabase
from .db.mongodb_utils import db_manager
from .services.document_processing_service import DocumentProcessingService
from .core.config import settings, Settings
from app.services.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.enhanced_ai_qa_service import enhanced_ai_qa_service
from app.services.vector_db_service import vector_db_service, VectorDatabaseService


async def get_db() -> AsyncIOMotorDatabase:
    if db_manager.db is None:
        # 這確保了即使在 lifespan 之外被調用（例如，在測試或腳本中），
        # 也能嘗試連接，儘管在正常的應用程式流程中 lifespan 應該已經處理了連接。
        await db_manager.connect_to_mongo()
        if db_manager.db is None:
            # 可以引發一個更具體的 HTTPException，如果這是在請求處理流程中
            raise ConnectionError("資料庫未連接且無法建立新連接。")
    return db_manager.db

def get_unified_ai_service():
    """
    獲取統一AI服務實例
    """
    return unified_ai_service_simplified

def get_enhanced_ai_qa_service():
    """
    獲取增強AI問答服務實例
    """
    return enhanced_ai_qa_service

def get_document_processing_service() -> DocumentProcessingService:
    """獲取 DocumentProcessingService 的實例。"""
    return DocumentProcessingService()

def get_vector_db_service() -> VectorDatabaseService:
    """獲取 VectorDBService 的實例。"""
    return vector_db_service

async def get_settings() -> Settings:
    """獲取應用程式設定的實例。"""
    return settings 