from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.security import get_current_active_user
from app.models.user_models import User
from app.services.embedding_service import embedding_service
from app.core.device_config import device_config_manager, DeviceType
from app.core.logging_utils import AppLogger
import logging

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

router = APIRouter()

class DeviceConfigRequest(BaseModel):
    device_preference: str  # 'auto', 'cpu', 'cuda'
    force_reload: bool = False

@router.get("/config")
async def get_embedding_model_config(
    current_user: User = Depends(get_current_active_user)
):
    """獲取 Embedding 模型配置選項 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 請求embedding模型配置")
        
        import torch
        
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
        
        # 檢查可用設備
        config["available_devices"].append("cpu")
        if torch.cuda.is_available():
            config["available_devices"].append("cuda")
            config["gpu_info"] = {
                "device_name": torch.cuda.get_device_name(),
                "memory_total": f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB",
                "pytorch_version": torch.__version__,
                "cuda_version": torch.version.cuda if torch.version.cuda else "N/A"
            }
        
        # 添加性能信息
        device_config = device_config_manager.get_device_config()
        performance_recommendation = device_config_manager.get_performance_recommendation()
        
        if device_config:
            config["performance_info"] = {
                "gpu_performance": "GPU 模式：3-6秒加載，50-150ms搜索，3-8分鐘/1000文檔",
                "cpu_performance": "CPU 模式：8-12秒加載，200-500ms搜索，15-25分鐘/1000文檔",
                "recommendation": "建議使用GPU以獲得更好性能" if device_config.get("gpu_available") else "使用CPU模式以確保兼容性"
            }
        
        # 添加模型信息
        if embedding_service._model_loaded:
            config["model_info"] = {
                "model_name": embedding_service.model_name,
                "vector_dimension": embedding_service.vector_dimension,
                "model_size": "約 420MB"
            }
        
        return config
        
    except Exception as e:
        logger.error(f"獲取模型配置失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取模型配置失敗: {str(e)}"
        )

@router.post("/load")
async def load_embedding_model(
    current_user: User = Depends(get_current_active_user)
):
    """手動加載 Embedding 模型 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 請求加載embedding模型")
        
        if embedding_service._model_loaded:
            return JSONResponse(
                content={
                    "message": "Embedding模型已經加載",
                    "status": "already_loaded",
                    "model_info": embedding_service.get_model_info()
                }
            )
        
        logger.info(f"用戶 {current_user.username} 開始手動加載Embedding模型...")
        
        # 執行模型加載
        embedding_service._load_model()
        
        model_info = embedding_service.get_model_info()
        
        logger.info(f"用戶 {current_user.username} Embedding模型加載成功")
        
        return JSONResponse(
            content={
                "message": "Embedding模型加載成功",
                "status": "loaded",
                "model_info": model_info,
                "load_time_info": "模型已從緩存加載"
            }
        )
        
    except Exception as e:
        logger.error(f"加載Embedding模型失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"加載Embedding模型失敗: {str(e)}"
        )

@router.post("/configure-device")
async def configure_embedding_device(
    request: DeviceConfigRequest,
    current_user: User = Depends(get_current_active_user)
):
    """配置 Embedding 模型設備偏好 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 請求配置設備: {request.device_preference}")
        
        import torch
        
        if request.device_preference not in ["cpu", "cuda", "auto"]:
            raise HTTPException(
                status_code=400,
                detail="設備偏好必須是 'cpu', 'cuda' 或 'auto'"
            )
        
        if request.device_preference == "cuda" and not torch.cuda.is_available():
            raise HTTPException(
                status_code=400,
                detail="CUDA 不可用，無法設置為 GPU 模式"
            )
        
        # 使用設備配置管理器設置偏好
        try:
            device_type = DeviceType(request.device_preference)
            success = device_config_manager.set_device_preference(device_type)
            if success:
                result = {"note": f"設備偏好已設置為 {request.device_preference}"}
            else:
                result = {"note": "設備偏好設置失敗，可能是硬體限制"}
        except ValueError as e:
            logger.warning(f"無效的設備偏好: {request.device_preference}")
            result = {"note": "無效的設備偏好值"}
        except Exception as e:
            logger.warning(f"設置設備偏好失敗: {e}")
            result = {"note": "設備偏好設置遇到問題，但已記錄請求"}
        
        # 如果需要強制重新加載模型
        requires_restart = False
        if request.force_reload and embedding_service._model_loaded:
            logger.info(f"用戶 {current_user.username} 強制重新加載模型")
            try:
                # 卸載當前模型
                embedding_service._model = None
                embedding_service._model_loaded = False
                # 重新加載模型
                embedding_service._load_model()
                requires_restart = False
            except Exception as e:
                logger.warning(f"重新加載模型失敗: {e}")
                requires_restart = True
        
        logger.info(f"用戶 {current_user.username} 設備配置完成: {request.device_preference}")
        
        return JSONResponse(
            content={
                "message": f"設備偏好已設置為: {request.device_preference}",
                "device_preference": request.device_preference,
                "note": result.get("note", "設備偏好設置成功"),
                "current_device": embedding_service.get_model_info()["device"],
                "requires_restart": requires_restart,
                "performance_impact": result.get("performance_impact", "性能將根據新設備設置調整")
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"配置模型設備失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"配置模型設備失敗: {str(e)}"
        )

@router.get("/status")
async def get_embedding_model_status(
    current_user: User = Depends(get_current_active_user)
):
    """獲取 Embedding 模型當前狀態 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 請求embedding模型狀態")
        
        model_info = embedding_service.get_model_info()
        device_config = device_config_manager.get_device_config()
        
        status = {
            "model_info": model_info,
            "device_config": device_config,
            "is_ready": embedding_service._model_loaded,
            "cache_available": hasattr(embedding_service, '_model') and embedding_service._model is not None,
            "last_used": None,  # TODO: 可以添加最後使用時間追蹤
            "performance_metrics": {
                "average_encoding_time": None,  # TODO: 可以添加性能指標追蹤
                "total_encodings": None
            }
        }
        
        return status
        
    except Exception as e:
        logger.error(f"獲取模型狀態失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取模型狀態失敗: {str(e)}"
        )

@router.post("/unload")
async def unload_embedding_model(
    current_user: User = Depends(get_current_active_user)
):
    """卸載 Embedding 模型 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 請求卸載embedding模型")
        
        if not embedding_service._model_loaded:
            return JSONResponse(
                content={
                    "message": "Embedding模型未加載",
                    "status": "not_loaded"
                }
            )
        
        # 卸載模型
        embedding_service._model = None
        embedding_service._model_loaded = False
        
        logger.info(f"用戶 {current_user.username} Embedding模型卸載成功")
        
        return JSONResponse(
            content={
                "message": "Embedding模型已卸載",
                "status": "unloaded",
                "memory_freed": "模型記憶體已釋放"
            }
        )
        
    except Exception as e:
        logger.error(f"卸載Embedding模型失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"卸載Embedding模型失敗: {str(e)}"
        ) 