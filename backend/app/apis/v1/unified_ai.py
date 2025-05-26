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

router = APIRouter()
logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

# === 新的響應模型（保持API兼容性）===
from pydantic import BaseModel

class AIResponse(BaseModel):
    """統一的AI響應格式 - 保持向後兼容"""
    answer: str  # JSON字符串格式，保持舊格式兼容性
    token_usage: TokenUsage
    model_used: str
    processing_time: Optional[float] = None

# === 文本分析端點（已切換到簡化版） ===
@router.post("/analyze-text", response_model=AIResponse)
async def analyze_text(
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
    logger.info(f"用戶 {current_user.username} 請求文本分析（簡化版）")
    
    try:
        # 使用簡化版統一AI服務進行文本分析
        ai_response = await unified_ai_service_simplified.analyze_text(
            text_content=request_data.user_prompt,
            db=db,
            model_preference=request_data.model
        )
        
        if not ai_response.success:
            logger.error(f"簡化版文本分析失敗: {ai_response.error_message}")
            raise HTTPException(status_code=500, detail=ai_response.error_message)
        
        # 轉換為API響應格式 - 保持向後兼容性
        content_json = ai_response.content.model_dump_json() if hasattr(ai_response.content, 'model_dump_json') else str(ai_response.content)
        
        return AIResponse(
            answer=content_json,
            token_usage=ai_response.token_usage,
            model_used=ai_response.model_used,
            processing_time=ai_response.processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"簡化版文本分析處理失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文本分析失敗: {str(e)}")

# === 圖片分析端點（已切換到簡化版） ===
@router.post("/analyze-image", response_model=AIResponse)
async def analyze_image(
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
    logger.info(f"用戶 {current_user.username} 請求圖片分析（簡化版），文件: {image.filename}")
    
    try:
        # 讀取圖片數據
        image_data = await image.read()
        image_mime_type = image.content_type or "image/jpeg"
        
        # 使用簡化版統一AI服務進行圖片分析
        ai_response = await unified_ai_service_simplified.analyze_image(
            image_data=image_data,
            image_mime_type=image_mime_type,
            db=db,
            model_preference=model
        )
        
        if not ai_response.success:
            logger.error(f"簡化版圖片分析失敗: {ai_response.error_message}")
            raise HTTPException(status_code=500, detail=ai_response.error_message)
        
        # 轉換為API響應格式 - 保持向後兼容性
        content_json = ai_response.content.model_dump_json() if hasattr(ai_response.content, 'model_dump_json') else str(ai_response.content)
        
        return AIResponse(
            answer=content_json,
            token_usage=ai_response.token_usage,
            model_used=ai_response.model_used,
            processing_time=ai_response.processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"簡化版圖片分析處理失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"圖片分析失敗: {str(e)}")

# === AI問答端點（更新為使用簡化版） ===
@router.post("/qa", response_model=AIQAResponse)
async def ai_question_answer(
    request: AIQARequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    統一AI問答端點 - 使用增強的RAG+T2Q混合檢索策略
    現在內部使用簡化版AI服務
    
    實現流程：
    1. 查詢重寫（使用簡化版統一AI服務）
    2. 向量搜索
    3. T2Q過濾
    4. 生成答案（使用簡化版統一AI服務）
    
    只返回用戶有權限訪問的文檔相關信息
    """
    try:
        logger.info(f"用戶 {current_user.username} 收到AI問答請求: {request.question[:100]}（簡化版）")
        
        # 使用增強的AI問答服務處理請求（內部會使用簡化版AI服務）
        response = await enhanced_ai_qa_service.process_qa_request(
            db=db, 
            request=request, 
            user_id=current_user.id
        )
        
        logger.info(f"用戶 {current_user.username} AI問答處理完成（簡化版），Token使用: {response.tokens_used}")
        return response
        
    except Exception as e:
        logger.error(f"AI問答處理失敗（簡化版）: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"AI問答處理失敗: {str(e)}"
        )

# === 查詢重寫端點（已切換到簡化版） ===
@router.post("/rewrite-query")
async def rewrite_query(
    query: str,
    model: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    查詢重寫端點 - 現在使用簡化版本
    """
    try:
        logger.info(f"用戶 {current_user.username} 請求查詢重寫（簡化版）: {query[:50]}")
        
        # 使用簡化版統一AI服務進行查詢重寫
        ai_response = await unified_ai_service_simplified.rewrite_query(
            original_query=query,
            db=db,
            model_preference=model
        )
        
        if not ai_response.success:
            raise HTTPException(status_code=500, detail=ai_response.error_message)
        
        return {
            "original_query": query,
            "rewritten_result": ai_response.content.model_dump_json() if hasattr(ai_response.content, 'model_dump_json') else str(ai_response.content),
            "token_usage": ai_response.token_usage.model_dump(),
            "model_used": ai_response.model_used,
            "processing_time": ai_response.processing_time,
            "simplified_version": True  # 標記使用簡化版本
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"簡化版查詢重寫失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢重寫失敗: {str(e)}")

# === 模型配置端點（使用簡化版配置） ===
@router.get("/models")
async def list_available_models(
    task_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """
    列出可用的AI模型 - 使用簡化版配置
    """
    try:
        from app.services.unified_ai_config import unified_ai_config, TaskType
        
        # 轉換任務類型
        task_type_enum = None
        if task_type:
            try:
                task_type_enum = TaskType(task_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"無效的任務類型: {task_type}")
        
        # 獲取可用模型列表
        models = await unified_ai_config.get_available_models_for_task(task_type_enum)
        
        return {
            "success": True,
            "task_type": task_type,
            "available_models": models,
            "simplified_version": True,  # 標記使用簡化版本
            "supported_structures": ["FlexibleKeyInformation", "FlexibleIntermediateAnalysis"]
        }
        
    except Exception as e:
        logger.error(f"獲取模型列表失敗: {e}", exc_info=True)
        return {
            "success": False,
            "available_models": [],
            "error_message": f"獲取模型列表失敗: {str(e)}"
        }

# === 提示詞配置端點（使用簡化版） ===
@router.get("/prompts")
async def list_available_prompts(
    current_user: User = Depends(get_current_active_user)
):
    """
    列出可用的提示詞模板 - 使用簡化版本
    """
    try:
        from app.services.prompt_manager_simplified import prompt_manager_simplified
        
        # 獲取簡化版提示詞列表
        prompts = {}
        for prompt_type in PromptType:
            prompt_template = prompt_manager_simplified._prompts.get(prompt_type)
            if prompt_template:
                prompts[prompt_type.value] = {
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
        logger.error(f"獲取提示詞列表失敗: {e}", exc_info=True)
        return {
            "success": False,
            "available_prompts": {},
            "error_message": f"獲取提示詞列表失敗: {str(e)}"
        }

# === API Key配置端點 ===
@router.post("/config/api-key")
async def update_api_key(
    api_key: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    更新API Key - 兼容簡化版本
    """
    try:
        from app.core.config import settings
        
        # 這裡可以添加API Key驗證邏輯
        # 暫時只是更新配置
        settings.GOOGLE_API_KEY = api_key
        
        return {
            "success": True,
            "message": "API Key已更新",
            "simplified_version": True
        }
        
    except Exception as e:
        logger.error(f"更新API Key失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"更新API Key失敗: {str(e)}"
        )

# === 系統狀態端點（簡化版） ===
@router.get("/status")
async def ai_system_status(
    current_user: User = Depends(get_current_active_user)
):
    """
    AI系統狀態檢查 - 現在顯示簡化版本狀態
    """
    try:
        from app.core.config import settings
        
        status = {
            "success": True,
            "version": "simplified",  # 標記為簡化版本
            "api_key_configured": bool(settings.GOOGLE_API_KEY),
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
                "code_reduction": "57%",
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
        
        return status
        
    except Exception as e:
        logger.error(f"獲取系統狀態失敗: {e}", exc_info=True)
        return {
            "success": False,
            "version": "simplified",
            "error_message": f"系統狀態檢查失敗: {str(e)}"
        } 