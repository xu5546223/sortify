import logging
from typing import Dict, Any, Optional
from copilotkit import CopilotKitRemoteEndpoint, Action as CopilotAction

from motor.motor_asyncio import AsyncIOMotorDatabase # For type hinting db
from app.db.mongodb_utils import db_manager
from app.models.vector_models import AIQARequest, AIQAResponse
from app.models.ai_models_simplified import AITextAnalysisOutput, FlexibleKeyInformation # Added FlexibleKeyInformation
from app.services import enhanced_ai_qa_service, unified_ai_service_simplified


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

# --- Renamed Action: 從後端獲取專案資訊 ---
async def get_project_info(category: str) -> Dict[str, Any]:
    """
    Retrieves general project information based on a category.
    In a real application, this would involve your business logic, e.g., querying a database.
    """
    copilot_logger.info(f"CopilotKit Action 'get_project_info' called with category: {category}")
    # Note: If the Action needs to access app.version or other properties of the app instance,
    # you need to find a way to access them safely, e.g., through configuration or dependency injection,
    # instead of directly importing app.
    # For demonstration, we temporarily remove direct dependency on app.version or assume it's fetched elsewhere.
    # app_version = "0.1.0" # Example version
    # app_description = "Sortify AI Assistant Backend" # Example description

    if category.lower() == "status":
        return {"projectName": "Sortify", "status": "Ongoing", "progress": "75%", "nextMilestone": "User authentication module completion"}
    elif category.lower() == "team":
        return {"projectName": "Sortify", "teamSize": 5, "lead": "AI Assistant", "members": ["Developer A", "Developer B"]}
    elif category.lower() == "version":
        # If app.version is needed, ensure it's accessed safely. Returning fixed value or from config.
        try:
            from .core.config import settings # Assuming settings can provide version info
            app_version = getattr(settings, 'APP_VERSION', 'N/A')
            app_description = getattr(settings, 'APP_DESCRIPTION', 'N/A')
        except ImportError:
            copilot_logger.warning("Could not import settings from .core.config. Using fallback values for version/description.")
            app_version = 'N/A'
            app_description = 'N/A'
        return {"projectName": "Sortify", "version": app_version, "description": app_description}
    else:
        return {"error": f"Unknown query category: {category}. Available categories: status, team, version."}

# Wrap the function into a CopilotKit Action
project_info_action = CopilotAction(
    name="getProjectInfo",
    description="Retrieves general project information based on a category (e.g., 'status', 'team', 'version').",
    parameters=[
        {
            "name": "category",
            "type": "string",
            "description": "The information category to query (e.g., 'status', 'team', 'version')",
            "required": True,
        }
    ],
    handler=get_project_info
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
        ai_response: AIQAResponse = await enhanced_ai_qa_service.process_qa_request(
            db=db,
            request=AIQARequest(question=question),
            user_id=user_id
        )

        if ai_response.answer and not ai_response.error_message:
            return {
                "answer": ai_response.answer,
                "sources": [str(doc_id) for doc_id in ai_response.source_documents_ids or []], # Use .source_documents_ids
                "confidence": ai_response.confidence_score
            }
        else:
            error_msg = ai_response.error_message or "No answer found."
            copilot_logger.warning(f"No answer or error from AI QA service: {error_msg}")
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

# --- New Action: Summarize text ---
async def summarize_text(text_content: str, document_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Summarizes the provided text content.
    """
    copilot_logger.info(f"CopilotKit Action 'summarize_text' called. Doc ID: {document_id}, Text length: {len(text_content)}")
    db = db_manager.get_database()
    if db is None:
        copilot_logger.error("Database not available for summarizeText action.")
        return {"summary": "Error: Database not available. Cannot process the text summarization.", "error": "Database connection error."}

    try:
        ai_response = await unified_ai_service_simplified.analyze_text(text=text_content, db=db)

        if ai_response.success and ai_response.output_data:
            if isinstance(ai_response.output_data, AITextAnalysisOutput):
                summary = ai_response.output_data.initial_summary
                if not summary and isinstance(ai_response.output_data.key_information, FlexibleKeyInformation):
                    summary = ai_response.output_data.key_information.content_summary

                if summary:
                    return {"summary": summary}
                else:
                    copilot_logger.warning("AITextAnalysisOutput was received but no summary could be extracted.")
                    return {"summary": "Could not extract a summary from the AI response.", "error": "Summary field missing in AI output."}
            elif isinstance(ai_response.output_data, str):
                # Fallback if the output is just a string (less ideal)
                return {"summary": ai_response.output_data}
            else:
                copilot_logger.error(f"Unexpected output_data type: {type(ai_response.output_data)}")
                return {"summary": "Error: Unexpected AI response format.", "error": "AI output type mismatch."}
        else:
            error_msg = ai_response.error_message or "Failed to analyze text."
            copilot_logger.warning(f"Summarization failed or no output data: {error_msg}")
            return {"summary": "Could not summarize the text.", "error": error_msg}
    except Exception as e:
        copilot_logger.error(f"Error in summarize_text: {e}", exc_info=True)
        return {"summary": "An unexpected error occurred while summarizing the text.", "error": str(e)}

summarize_text_action = CopilotAction(
    name="summarizeText",
    description="Summarizes the provided text content.",
    parameters=[
        {"name": "text_content", "type": "string", "description": "The text to be summarized.", "required": True},
        {"name": "document_id", "type": "string", "description": "Optional document ID for context/logging.", "required": False}
    ],
    handler=summarize_text
)

# --- Configure CopilotKit Remote Endpoint ---
python_backend_sdk = CopilotKitRemoteEndpoint(
    actions=[
        project_info_action,
        ask_project_documents_action,
        summarize_text_action
    ]
)

copilot_logger.info("CopilotKit SDK (python_backend_sdk) initialized in copilot_setup.py with updated actions.")
