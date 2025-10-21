from motor.motor_asyncio import AsyncIOMotorDatabase
from .db.mongodb_utils import db_manager, get_db
from .services.document.document_processing_service import DocumentProcessingService
from .core.config import settings, Settings
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.enhanced_ai_qa_service import enhanced_ai_qa_service
from app.services.vector.vector_db_service import vector_db_service, VectorDatabaseService
from app.services.document.document_tasks_service import DocumentTasksService




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

def get_document_tasks_service() -> DocumentTasksService:
    """獲取 DocumentTasksService 的實例。"""
    return DocumentTasksService()

def get_vector_db_service() -> VectorDatabaseService:
    """獲取 VectorDBService 的實例。"""
    return vector_db_service

async def get_settings() -> Settings:
    """獲取應用程式設定的實例。"""
    return settings 