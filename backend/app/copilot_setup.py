import logging
from typing import Dict, Any, Optional
from copilotkit import CopilotKitRemoteEndpoint, Action as CopilotAction

from motor.motor_asyncio import AsyncIOMotorDatabase # For type hinting db
from app.db.mongodb_utils import db_manager
from app.models.vector_models import AIQARequest, AIQAResponse
from app.models.ai_models_simplified import AITextAnalysisOutput, FlexibleKeyInformation # Added FlexibleKeyInformation
from app.services.enhanced_ai_qa_service import EnhancedAIQAService # Changed import
from app.services.unified_ai_service_simplified import UnifiedAIServiceSimplified # Changed import


# 假設 FastAPI app 實例和版本資訊可以從 main 或 config 獲取（如果需要的話）
# from .main import app # 避免循環導入，如果需要 app 的屬性，考慮其他方式傳遞或從 config 讀取

# 獲取一個日誌記錄器實例
# 您可以選擇傳入 main.py 中的 std_logger，或者在這裡重新獲取
# 為了簡單起見，我們先在這裡獲取一個。如果需要與 main.py 一致的日誌行為，則需要調整。
copilot_logger = logging.getLogger(__name__)
if not copilot_logger.hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

# --- New Action: Ask about project documents ---
async def ask_about_project_documents(question: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Answers questions based on the content of documents within the project.
    """
    copilot_logger.info(f"CopilotKit Action 'ask_about_project_documents' called with question: {question[:50]}..., User ID: {user_id}")
    db = db_manager.get_database()
    if db is None:
        copilot_logger.error("Database not available for askAboutProjectDocuments action.")
        return {"answer": "Error: Database not available. Cannot process the document question.", "error": "Database connection error."}

    try:
        qa_service = EnhancedAIQAService() # Instantiate the service
        ai_response: AIQAResponse = await qa_service.process_qa_request( # Call via instance
            db=db,
            request=AIQARequest(question=question),
            user_id=user_id,
            request_id=None # Added request_id as None
        )

        if ai_response.answer and ai_response.confidence_score > 0:
            return {
                "answer": ai_response.answer,
                "sources": [str(doc_id) for doc_id in ai_response.source_documents or []],
                "confidence": ai_response.confidence_score
            }
        else:
            error_msg = ai_response.answer or "No answer found."
            copilot_logger.warning(f"No answer or low confidence from AI QA service: {error_msg}")
            return {"answer": "Could not retrieve an answer. Please try rephrasing or check logs.", "error": error_msg}
    except Exception as e:
        copilot_logger.error(f"Error in ask_about_project_documents: {e}", exc_info=True)
        return {"answer": "An unexpected error occurred while processing your question.", "error": str(e)}

ask_project_documents_action = CopilotAction(
    name="askAboutProjectDocuments",
    description="Answers questions based on the content of documents within the project. Requires a user question.",
    parameters=[
        {"name": "question", "type": "string", "description": "The question to ask about the project documents.", "required": True},
        {"name": "user_id", "type": "string", "description": "Optional user ID for permissioned document access.", "required": False}
    ],
    handler=ask_about_project_documents
)


# --- Configure CopilotKit Remote Endpoint ---
python_backend_sdk = CopilotKitRemoteEndpoint(
    actions=[
        ask_project_documents_action,
    ]
)

copilot_logger.info("CopilotKit SDK (python_backend_sdk) initialized in copilot_setup.py with updated actions.")
