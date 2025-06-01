from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi import Request # Added Request
from pydantic import BaseModel

from app.core.security import get_current_active_user
from app.models.user_models import User
from app.services.embedding_service import embedding_service
from app.core.device_config import device_config_manager, DeviceType
from app.core.logging_utils import AppLogger, log_event # Added log_event
from app.models.log_models import LogLevel # Added LogLevel
import logging

logger = AppLogger(__name__, level=logging.DEBUG).get_logger() # Existing app logger can remain for very low-level/internal logs if desired

router = APIRouter()

class DeviceConfigRequest(BaseModel):
    device_preference: str  # 'auto', 'cpu', 'cuda'
    force_reload: bool = False

@router.get("/config")
async def get_embedding_model_config(
    request: Request, # Added Request
    db: AsyncIOMotorDatabase = Depends(get_db), # Added db for log_event
    current_user: User = Depends(get_current_active_user)
):
    """獲取 Embedding 模型配置選項 - 需要用戶認證"""
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    try:
        # logger.info(f"用戶 {current_user.username} 請求embedding模型配置") # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.DEBUG,
            message=f"User {current_user.username} requested embedding model configuration.",
            source="api.embedding.get_config", user_id=str(current_user.id), request_id=request_id_val
        )
        
        import torch # Keep torch import local to where it's used
        
        config = {
            "current_model": embedding_service.model_name,
            "available_devices": [],
            "recommended_device": "cuda" if torch.cuda.is_available() else "cpu",
            "gpu_info": None,
            "model_loaded": embedding_service._model_loaded,
            "current_device": embedding_service.get_model_info()["device"],
            "performance_info": None,
            "model_info": None
        }
        
        config["available_devices"].append("cpu")
        if torch.cuda.is_available():
            config["available_devices"].append("cuda")
            config["gpu_info"] = {
                "device_name": torch.cuda.get_device_name(),
                "memory_total": f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB",
                "pytorch_version": torch.__version__,
                "cuda_version": torch.version.cuda if torch.version.cuda else "N/A"
            }
        
        device_config = device_config_manager.get_device_config()
        # performance_recommendation = device_config_manager.get_performance_recommendation() # Not used
        
        if device_config:
            config["performance_info"] = {
                "gpu_performance": "GPU 模式：3-6秒加載，50-150ms搜索，3-8分鐘/1000文檔",
                "cpu_performance": "CPU 模式：8-12秒加載，200-500ms搜索，15-25分鐘/1000文檔",
                "recommendation": "建議使用GPU以獲得更好性能" if device_config.get("gpu_available") else "使用CPU模式以確保兼容性"
            }
        
        if embedding_service._model_loaded:
            config["model_info"] = {
                "model_name": embedding_service.model_name,
                "vector_dimension": embedding_service.vector_dimension,
                "model_size": "約 420MB"
            }
        
        await log_event(
            db=db, level=LogLevel.DEBUG,
            message=f"Successfully retrieved embedding model configuration for user {current_user.username}.",
            source="api.embedding.get_config", user_id=str(current_user.id), request_id=request_id_val,
            details={"config_summary": {"model_loaded": config["model_loaded"], "current_device": config["current_device"]}}
        )
        return config
        
    except Exception as e:
        # logger.error(f"獲取模型配置失敗: {e}", exc_info=True) # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Failed to get embedding model configuration for user {current_user.username}: {str(e)}",
            source="api.embedding.get_config", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve model configuration." # User-friendly
        )

@router.post("/load")
async def load_embedding_model(
    request: Request, # Added
    db: AsyncIOMotorDatabase = Depends(get_db), # Added
    current_user: User = Depends(get_current_active_user)
):
    """手動加載 Embedding 模型 - 需要用戶認證"""
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"User {current_user.username} requested to load embedding model.",
        source="api.embedding.load_model", user_id=str(current_user.id), request_id=request_id_val
    )

    try:
        if embedding_service._model_loaded:
            await log_event(
                db=db, level=LogLevel.INFO,
                message=f"Embedding model load request by {current_user.username}: Model already loaded.",
                source="api.embedding.load_model", user_id=str(current_user.id), request_id=request_id_val,
                details={"model_info": embedding_service.get_model_info()}
            )
            return JSONResponse(
                content={
                    "message": "Embedding model already loaded.", # User-friendly
                    "status": "already_loaded",
                    "model_info": embedding_service.get_model_info()
                }
            )
        
        logger.info(f"User {current_user.username} initiating manual load of Embedding model...") # Keep this specific internal logger if desired
        
        embedding_service._load_model() # This might take time
        
        model_info = embedding_service.get_model_info()
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Embedding model loaded successfully by user {current_user.username}.",
            source="api.embedding.load_model", user_id=str(current_user.id), request_id=request_id_val,
            details={"model_info": model_info}
        )
        
        return JSONResponse(
            content={
                "message": "Embedding model loaded successfully.", # User-friendly
                "status": "loaded",
                "model_info": model_info,
                "load_time_info": "Model has been loaded." # Simplified
            }
        )
        
    except Exception as e:
        # logger.error(f"加載Embedding模型失敗: {e}", exc_info=True) # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Failed to load embedding model for user {current_user.username}: {str(e)}",
            source="api.embedding.load_model", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to load embedding model." # User-friendly
        )

@router.post("/configure-device")
async def configure_embedding_device(
    config_request: DeviceConfigRequest, # Renamed to avoid conflict with fastapi.Request
    fastapi_request: Request, # Added Request
    db: AsyncIOMotorDatabase = Depends(get_db), # Added db
    current_user: User = Depends(get_current_active_user)
):
    """配置 Embedding 模型設備偏好 - 需要用戶認證"""
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"User {current_user.username} requested to configure embedding device.",
        source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val,
        details={"device_preference": config_request.device_preference, "force_reload": config_request.force_reload}
    )

    try:
        import torch # Keep torch import local
        
        if config_request.device_preference not in ["cpu", "cuda", "auto"]:
            await log_event(db=db, level=LogLevel.WARNING, message=f"Invalid device preference '{config_request.device_preference}' by user {current_user.username}.",
                            source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val)
            raise HTTPException(status_code=400, detail="Device preference must be 'cpu', 'cuda', or 'auto'.")
        
        if config_request.device_preference == "cuda" and not torch.cuda.is_available():
            await log_event(db=db, level=LogLevel.WARNING, message=f"CUDA requested by user {current_user.username} but not available.",
                            source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val)
            raise HTTPException(status_code=400, detail="CUDA not available, cannot set to GPU mode.")
        
        set_pref_note = ""
        try:
            device_type = DeviceType(config_request.device_preference)
            success = device_config_manager.set_device_preference(device_type)
            if success:
                set_pref_note = f"Device preference set to {config_request.device_preference}."
                await log_event(db=db, level=LogLevel.INFO, message=set_pref_note, source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val)
            else:
                set_pref_note = "Failed to set device preference, possibly due to hardware limitations."
                await log_event(db=db, level=LogLevel.WARNING, message=set_pref_note, source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val)
        except ValueError as e_val:
            set_pref_note = f"Invalid device preference value: {config_request.device_preference}."
            logger.warning(set_pref_note) # Keep existing logger for this specific internal detail
            await log_event(db=db, level=LogLevel.WARNING, message=set_pref_note, source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val, details={"error": str(e_val)})
        except Exception as e_set: # Catch other potential errors from set_device_preference
            set_pref_note = f"Problem setting device preference: {str(e_set)}."
            logger.warning(set_pref_note, exc_info=True) # Keep existing logger
            await log_event(db=db, level=LogLevel.ERROR, message=set_pref_note, source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val, details={"error": str(e_set)})

        requires_restart_msg = "" # Will be part of the note if restart happens
        if config_request.force_reload and embedding_service._model_loaded:
            await log_event(db=db, level=LogLevel.INFO, message=f"User {current_user.username} requested force model reload.", source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val)
            try:
                embedding_service._model = None
                embedding_service._model_loaded = False
                embedding_service._load_model() # This might take time
                requires_restart_msg = " Model reloaded successfully."
                await log_event(db=db, level=LogLevel.INFO, message=f"Embedding model reloaded successfully by user {current_user.username}.", source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val)
            except Exception as e_reload:
                requires_restart_msg = f" Failed to reload model: {str(e_reload)}."
                logger.warning(f"重新加載模型失敗: {e_reload}", exc_info=True) # Keep existing logger for this detail
                await log_event(db=db, level=LogLevel.ERROR, message=f"Model reload failed for user {current_user.username}: {str(e_reload)}", source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val, details={"error": str(e_reload)})

        final_note = set_pref_note + requires_restart_msg

        await log_event(db=db, level=LogLevel.INFO,
                        message=f"Device configuration completed for user {current_user.username}. Preference: {config_request.device_preference}, Forced Reload: {config_request.force_reload}.",
                        source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val,
                        details={"final_note": final_note, "current_model_device": embedding_service.get_model_info()["device"]})

        return JSONResponse(
            content={
                "message": f"Device preference set to: {config_request.device_preference}.", # User-friendly
                "device_preference": config_request.device_preference,
                "note": final_note,
                "current_device": embedding_service.get_model_info()["device"],
                "requires_restart": "Failed to reload model" in requires_restart_msg, # True if reload failed
                "performance_impact": "Performance will adjust based on the new device setting." # Generic
            }
        )
        
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        # logger.error(f"配置模型設備失敗: {e}", exc_info=True) # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Failed to configure embedding device for user {current_user.username}: {str(e)}",
            source="api.embedding.configure_device", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to configure model device." # User-friendly
        )

@router.get("/status")
async def get_embedding_model_status(
    request: Request, # Added
    db: AsyncIOMotorDatabase = Depends(get_db), # Added
    current_user: User = Depends(get_current_active_user)
):
    """獲取 Embedding 模型當前狀態 - 需要用戶認證"""
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.DEBUG,
        message=f"User {current_user.username} requested embedding model status.",
        source="api.embedding.get_status", user_id=str(current_user.id), request_id=request_id_val
    )

    try:
        model_info = embedding_service.get_model_info()
        device_config = device_config_manager.get_device_config()
        
        status_response = {
            "model_info": model_info,
            "device_config": device_config,
            "is_ready": embedding_service._model_loaded,
            "cache_available": hasattr(embedding_service, '_model') and embedding_service._model is not None,
            "last_used": None,
            "performance_metrics": {
                "average_encoding_time": None,
                "total_encodings": None
            }
        }
        
        await log_event(
            db=db, level=LogLevel.DEBUG,
            message=f"Successfully retrieved embedding model status for user {current_user.username}.",
            source="api.embedding.get_status", user_id=str(current_user.id), request_id=request_id_val,
            details={"is_ready": status_response["is_ready"], "current_device": model_info.get("device")}
        )
        return status_response
        
    except Exception as e:
        # logger.error(f"獲取模型狀態失敗: {e}", exc_info=True) # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Failed to get embedding model status for user {current_user.username}: {str(e)}",
            source="api.embedding.get_status", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve model status." # User-friendly
        )

@router.post("/unload")
async def unload_embedding_model(
    request: Request, # Added
    db: AsyncIOMotorDatabase = Depends(get_db), # Added
    current_user: User = Depends(get_current_active_user)
):
    """卸載 Embedding 模型 - 需要用戶認證"""
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"User {current_user.username} requested to unload embedding model.",
        source="api.embedding.unload_model", user_id=str(current_user.id), request_id=request_id_val
    )

    try:
        if not embedding_service._model_loaded:
            await log_event(
                db=db, level=LogLevel.INFO,
                message=f"Embedding model unload request by {current_user.username}: Model already not loaded.",
                source="api.embedding.unload_model", user_id=str(current_user.id), request_id=request_id_val
            )
            return JSONResponse(
                content={
                    "message": "Embedding model not loaded.", # User-friendly
                    "status": "not_loaded"
                }
            )
        
        embedding_service._model = None
        embedding_service._model_loaded = False
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Embedding model unloaded successfully by user {current_user.username}.",
            source="api.embedding.unload_model", user_id=str(current_user.id), request_id=request_id_val
        )
        
        return JSONResponse(
            content={
                "message": "Embedding model unloaded successfully.", # User-friendly
                "status": "unloaded",
                "memory_freed": "Model memory has been released." # User-friendly
            }
        )
        
    except Exception as e:
        # logger.error(f"卸載Embedding模型失敗: {e}", exc_info=True) # Replaced by log_event
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Failed to unload embedding model for user {current_user.username}: {str(e)}",
            source="api.embedding.unload_model", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to unload embedding model." # User-friendly
        ) 