import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_db
from app.models.user_models import User
from app.core.security import get_current_active_user
from app.core.logging_utils import AppLogger
# 切換到簡化版本的模型和服務
from app.models.ai_models_simplified import AIPromptRequest, TokenUsage
from app.services.unified_ai_service_simplified import unified_ai_service_simplified, AIRequest, TaskType
from app.services.prompt_manager_simplified import PromptType
from app.services.enhanced_ai_qa_service import enhanced_ai_qa_service
from app.models.vector_models import AIQARequest, AIQAResponse
from fastapi import Request # Added
from app.core.logging_utils import log_event, LogLevel # Added


router = APIRouter()
logger = AppLogger(__name__, level=logging.DEBUG).get_logger() # Existing AppLogger can remain for very detailed internal/service logs

# === 新的響應模型（保持API兼容性）===
from pydantic import BaseModel

class AIResponse(BaseModel):
    """統一的AI響應格式 - 保持向後兼容"""
    answer: str  # JSON字符串格式，保持舊格式兼容性
    token_usage: TokenUsage
    model_used: str
    processing_time: Optional[float] = None

class QueryRewriteRequest(BaseModel):
    """查詢重寫請求模型"""
    query: str
    model: Optional[str] = None

# === 文本分析端點（已切換到簡化版） ===
@router.post("/analyze-text", response_model=AIResponse)
async def analyze_text(
    fastapi_request: Request, # Added
    request_data: AIPromptRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    統一文本分析端點 - 現在使用簡化版本
    
    - **user_prompt**: 要分析的文本內容
    - **system_prompt** (可選): 額外的系統指令
    - **model** (可選): 指定使用的AI模型
    """
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"Unified AI request: Text Analysis for user {current_user.username}.",
        source="api.unified_ai.analyze_text", user_id=str(current_user.id), request_id=request_id_val,
        details={
            "model_preference": request_data.model,
            "prompt_length": len(request_data.user_prompt) if request_data.user_prompt else 0,
            "system_prompt_provided": bool(request_data.system_prompt)
        }
    )
    
    try:
        ai_response = await unified_ai_service_simplified.analyze_text(
            text=request_data.user_prompt,
            db=db,
            model_preference=request_data.model
        )
        
        if not ai_response.success:
            # logger.error(f"簡化版文本分析失敗: {ai_response.error_message}") # Replaced by log_event
            await log_event(
                db=db, level=LogLevel.ERROR,
                message=f"Unified AI request failed: Text Analysis for user {current_user.username}. Error: {ai_response.error_message}",
                source="api.unified_ai.analyze_text", user_id=str(current_user.id), request_id=request_id_val,
                details={
                    "model_preference": request_data.model, "error": ai_response.error_message,
                    "prompt_length": len(request_data.user_prompt) if request_data.user_prompt else 0
                }
            )
            raise HTTPException(status_code=500, detail=ai_response.error_message or "Text analysis failed.") # Keep detail somewhat generic
        
        content_json = ai_response.output_data.model_dump_json() if hasattr(ai_response.output_data, 'model_dump_json') else str(ai_response.output_data)
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Unified AI request successful: Text Analysis for user {current_user.username}.",
            source="api.unified_ai.analyze_text", user_id=str(current_user.id), request_id=request_id_val,
            details={
                "model_used": ai_response.model_used,
                "token_usage": ai_response.token_usage.model_dump() if ai_response.token_usage else None,
                "processing_time_ms": int(ai_response.processing_time_seconds * 1000) if ai_response.processing_time_seconds else None
            }
        )
        return AIResponse(
            answer=content_json, # This is a JSON string representation of complex Pydantic model
            token_usage=ai_response.token_usage,
            model_used=ai_response.model_used,
            processing_time=ai_response.processing_time_seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # logger.error(f"簡化版文本分析處理失敗: {e}", exc_info=True) # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Unified AI request failed unexpectedly: Text Analysis for user {current_user.username}. Error: {str(e)}",
            source="api.unified_ai.analyze_text", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__, "model_preference": request_data.model}
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred during text analysis.") # User-friendly

# === 圖片分析端點（已切換到簡化版） ===
@router.post("/analyze-image", response_model=AIResponse)
async def analyze_image(
    fastapi_request: Request, # Added
    image: UploadFile = File(...),
    model: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    統一圖片分析端點 - 現在使用簡化版本
    
    - **image**: 要分析的圖片文件
    - **model** (可選): 指定使用的AI模型
    """
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"Unified AI request: Image Analysis for user {current_user.username}.",
        source="api.unified_ai.analyze_image", user_id=str(current_user.id), request_id=request_id_val,
        details={
            "filename": image.filename,
            "content_type": image.content_type,
            "model_preference": model
        }
    )
    
    try:
        image_data = await image.read()
        image_mime_type = image.content_type or "image/jpeg" # Default to jpeg if not provided
        
        # Convert bytes to PIL Image
        from PIL import Image as PILImage
        import io
        pil_image = PILImage.open(io.BytesIO(image_data))
        
        ai_response = await unified_ai_service_simplified.analyze_image(
            image=pil_image,
            image_mime_type=image_mime_type,
            db=db,
            model_preference=model
        )
        
        if not ai_response.success:
            # logger.error(f"簡化版圖片分析失敗: {ai_response.error_message}") # Replaced
            await log_event(
                db=db, level=LogLevel.ERROR,
                message=f"Unified AI request failed: Image Analysis for user {current_user.username}. Error: {ai_response.error_message}",
                source="api.unified_ai.analyze_image", user_id=str(current_user.id), request_id=request_id_val,
                details={
                    "filename": image.filename, "model_preference": model, "error": ai_response.error_message
                }
            )
            raise HTTPException(status_code=500, detail=ai_response.error_message or "Image analysis failed.")
        
        content_json = ai_response.output_data.model_dump_json() if hasattr(ai_response.output_data, 'model_dump_json') else str(ai_response.output_data)
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Unified AI request successful: Image Analysis for user {current_user.username}.",
            source="api.unified_ai.analyze_image", user_id=str(current_user.id), request_id=request_id_val,
            details={
                "filename": image.filename, "model_used": ai_response.model_used,
                "token_usage": ai_response.token_usage.model_dump() if ai_response.token_usage else None,
                "processing_time_ms": int(ai_response.processing_time_seconds * 1000) if ai_response.processing_time_seconds else None
            }
        )
        return AIResponse(
            answer=content_json,
            token_usage=ai_response.token_usage,
            model_used=ai_response.model_used,
            processing_time=ai_response.processing_time_seconds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # logger.error(f"簡化版圖片分析處理失敗: {e}", exc_info=True) # Replaced
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Unified AI request failed unexpectedly: Image Analysis for user {current_user.username}. Error: {str(e)}",
            source="api.unified_ai.analyze_image", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__, "filename": image.filename, "model_preference": model}
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred during image analysis.") # User-friendly

# === AI問答端點（更新為使用簡化版） ===
@router.post("/qa", response_model=AIQAResponse)
async def ai_question_answer(
    fastapi_request: Request, # Added
    request_data: AIQARequest, # Renamed to avoid conflict
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    統一AI問答端點 - 使用增強的RAG+T2Q混合檢索策略
    現在內部使用簡化版AI服務
    """
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    
    # Correct way to count documents
    # Ensure the field name for user association in the documents collection is correct (e.g., owner_id or user_id)
    user_documents_count = await db.documents.count_documents({"owner_id": current_user.id}) 

    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"Unified AI QA request received from user {current_user.username}.",
        source="api.unified_ai.qa", user_id=str(current_user.id), request_id=request_id_val,
        details={
            "question_length": len(request_data.question) if request_data.question else 0,
            "user_total_documents_in_db": user_documents_count, 
            "document_ids_in_request_count": len(request_data.document_ids) if request_data.document_ids else 0,
            "model_preference": request_data.model_preference
        }
    )

    try:
        # logger.info(f"用戶 {current_user.username} 收到AI問答請求: {request.question[:100]}（簡化版）") # Replaced
        
        response = await enhanced_ai_qa_service.process_qa_request(
            db=db, 
            request=request_data,
            user_id=current_user.id
        )
        
        # logger.info(f"用戶 {current_user.username} AI問答處理完成（簡化版），Token使用: {response.tokens_used}") # Replaced
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Unified AI QA request successfully processed for user {current_user.username}.",
            source="api.unified_ai.qa", user_id=str(current_user.id), request_id=request_id_val,
            details={
                "response_answer_length": len(response.answer) if response.answer else 0,
                "source_documents_count": len(response.source_documents) if response.source_documents else 0,
                "tokens_used": response.tokens_used
            }
        )
        return response
        
    except Exception as e:
        # logger.error(f"AI問答處理失敗（簡化版）: {e}", exc_info=True) # Replaced
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Unified AI QA request failed for user {current_user.username}: {str(e)}",
            source="api.unified_ai.qa", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__, "question_length": len(request_data.question) if request_data.question else 0}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to process AI question and answer request." # User-friendly
        )

# === 查詢重寫端點（已切換到簡化版） ===
@router.post("/rewrite-query")
async def rewrite_query(
    fastapi_request: Request, # Added
    request_data: QueryRewriteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    查詢重寫端點 - 現在使用簡化版本，使用正確的 Pydantic 模型
    """
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"Unified AI Query Rewrite request from user {current_user.username}.",
        source="api.unified_ai.rewrite_query", user_id=str(current_user.id), request_id=request_id_val,
        details={"query_length": len(request_data.query) if request_data.query else 0, "model_preference": request_data.model}
    )

    try:
        ai_response = await unified_ai_service_simplified.rewrite_query(
            original_query=request_data.query,
            db=db,
            model_preference=request_data.model
        )
        
        if not ai_response.success:
            await log_event(
                db=db, level=LogLevel.ERROR,
                message=f"Unified AI Query Rewrite failed for user {current_user.username}. Error: {ai_response.error_message}",
                source="api.unified_ai.rewrite_query", user_id=str(current_user.id), request_id=request_id_val,
                details={"query_length": len(request_data.query) if request_data.query else 0, "model_preference": request_data.model, "error": ai_response.error_message}
            )
            raise HTTPException(status_code=500, detail=ai_response.error_message or "Query rewrite failed.")
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Unified AI Query Rewrite successful for user {current_user.username}.",
            source="api.unified_ai.rewrite_query", user_id=str(current_user.id), request_id=request_id_val,
            details={
                "original_query_length": len(request_data.query) if request_data.query else 0,
                "model_used": ai_response.model_used,
                "token_usage": ai_response.token_usage.model_dump() if ai_response.token_usage else None,
                "processing_time_ms": int(ai_response.processing_time_seconds * 1000) if ai_response.processing_time_seconds else None
            }
        )
        return {
            "original_query": request_data.query,
            "rewritten_result": ai_response.output_data.model_dump_json() if hasattr(ai_response.output_data, 'model_dump_json') else str(ai_response.output_data),
            "token_usage": ai_response.token_usage.model_dump() if ai_response.token_usage else None,
            "model_used": ai_response.model_used,
            "processing_time": ai_response.processing_time_seconds,
            "simplified_version": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Unified AI Query Rewrite failed unexpectedly for user {current_user.username}. Error: {str(e)}",
            source="api.unified_ai.rewrite_query", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__, "query_length": len(request_data.query) if request_data.query else 0, "model_preference": request_data.model}
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred during query rewrite.") # User-friendly

# === 模型配置端點（使用簡化版配置） ===
@router.get("/models")
async def list_available_models(
    fastapi_request: Request, # Added
    db: AsyncIOMotorDatabase = Depends(get_db), # Added
    task_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """
    列出可用的AI模型 - 使用簡化版配置
    """
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.DEBUG,
        message=f"User {current_user.username} requested list of available AI models.",
        source="api.unified_ai.list_models", user_id=str(current_user.id), request_id=request_id_val,
        details={"task_type_filter": task_type}
    )
    try:
        from app.services.unified_ai_config import unified_ai_config, TaskType as UnifiedTaskType # Alias to avoid conflict
        
        task_type_enum_val: Optional[UnifiedTaskType] = None # Use aliased TaskType
        if task_type:
            try:
                task_type_enum_val = UnifiedTaskType(task_type)
            except ValueError:
                await log_event(db=db, level=LogLevel.WARNING, message=f"Invalid task_type '{task_type}' provided by user {current_user.username}.",
                                source="api.unified_ai.list_models", user_id=str(current_user.id), request_id=request_id_val)
                raise HTTPException(status_code=400, detail=f"Invalid task type: {task_type}")
        
        models = await unified_ai_config.get_available_models_for_task(task_type_enum_val)
        
        return {
            "success": True,
            "task_type": task_type,
            "available_models": models,
            "simplified_version": True,
            "supported_structures": ["FlexibleKeyInformation", "FlexibleIntermediateAnalysis"]
        }
        
    except Exception as e:
        # logger.error(f"獲取模型列表失敗: {e}", exc_info=True) # Replaced
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Failed to list available AI models for user {current_user.username}. Error: {str(e)}",
            source="api.unified_ai.list_models", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__, "task_type_filter": task_type}
        )
        if isinstance(e, HTTPException): # If it was already an HTTPException (like the 400 above)
            raise
        return {
            "success": False,
            "available_models": [],
            "error_message": f"Failed to retrieve model list: {str(e)}" # User-friendly part
        }

# === 提示詞配置端點（使用簡化版） ===
@router.get("/prompts")
async def list_available_prompts(
    current_user: User = Depends(get_current_active_user)
):
    """
    列出可用的提示詞模板 - 使用簡化版本
    """
    await log_event(
        db=None, level=LogLevel.DEBUG, # db is None as it's not a dependency here
        message=f"User {current_user.username} requested list of available prompts.",
        source="api.unified_ai.list_prompts", user_id=str(current_user.id)
    )
    try:
        from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType as SimplifiedPromptType # Alias
        
        prompts = {}
        for prompt_type_enum_val in SimplifiedPromptType: # Use aliased PromptType
            prompt_template = prompt_manager_simplified._prompts.get(prompt_type_enum_val)
            if prompt_template:
                prompts[prompt_type_enum_val.value] = {
                    "description": prompt_template.description,
                    "variables": prompt_template.variables,
                    "simplified_version": True
                }
        
        return {
            "success": True,
            "available_prompts": prompts,
            "simplified_version": True,
            "message": "使用簡化版提示詞管理器"
        }
        
    except Exception as e:
        # logger.error(f"獲取提示詞列表失敗: {e}", exc_info=True) # Replaced
        await log_event(
            db=None, level=LogLevel.ERROR, # db is None
            message=f"Failed to list available prompts for user {current_user.username}. Error: {str(e)}",
            source="api.unified_ai.list_prompts", user_id=str(current_user.id),
            details={"error": str(e), "error_type": type(e).__name__}
        )
        return { # Original behavior returns JSON error
            "success": False,
            "available_prompts": {},
            "error_message": f"Failed to retrieve prompt list: {str(e)}"
        }

# === 系統狀態端點（簡化版） ===
@router.get("/status")
async def ai_system_status(
    current_user: User = Depends(get_current_active_user)
):
    """
    AI系統狀態檢查 - 現在顯示簡化版本狀態
    """

    await log_event(
        db=None, level=LogLevel.DEBUG, # db is None
        message=f"User {current_user.username} requested AI system status.",
        source="api.unified_ai.get_status", user_id=str(current_user.id)
    )
    try:
        from app.core.config import settings as app_settings # Alias to avoid conflict
        
        status_response = {
            "success": True,
            "version": "simplified",
            "api_key_configured": bool(app_settings.GOOGLE_API_KEY),
            "services": {
                "unified_ai_service_simplified": "active",
                "prompt_manager_simplified": "active",
                "flexible_structures": "active",
                "migration_status": "phase_3_completed"
            },
            "features": {
                "flexible_key_information": "enabled",
                "dynamic_fields": "enabled",
                "smart_repair": "enabled",
                "batch_processing": "enabled",
                "backward_compatibility": "enabled"
            },
            "performance": {
                "code_reduction": "57%", # Example data
                "structure_complexity": "simplified",
                "json_processing": "optimized",
                "vector_search": "enhanced"
            },
            "migration_info": {
                "phase": "3 - Production Deployment",
                "status": "Active",
                "legacy_backup": "Available in /legacy/"
            }
        }
        
        return status_response
        
    except Exception as e:
        # logger.error(f"獲取系統狀態失敗: {e}", exc_info=True) # Replaced
        await log_event(
            db=None, level=LogLevel.ERROR, # db is None
            message=f"Failed to get AI system status for user {current_user.username}. Error: {str(e)}",
            source="api.unified_ai.get_status", user_id=str(current_user.id),
            details={"error": str(e), "error_type": type(e).__name__}
        )
        return { # Original behavior returns JSON error
            "success": False,
            "version": "simplified",
            "error_message": f"System status check failed: {str(e)}"
        } 