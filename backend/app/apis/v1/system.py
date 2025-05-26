from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List

from ...dependencies import get_db
from ...models.system_models import (
    SettingsDataResponse,
    UpdatableSettingsData,
    ConnectionInfo,
    TunnelStatus,
    TestDBConnectionRequest,
    TestDBConnectionResponse,
)
from ...crud import crud_settings
from ...services.unified_ai_config import verify_google_api_key, get_google_ai_models
from ...core.logging_utils import log_event
from ...models.log_models import LogLevel

router = APIRouter()

# Pydantic model for the request body of the test API key endpoint
class TestApiKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1, description="要測試的 Google AI API 金鑰")

# Pydantic model for the response body of the test API key endpoint
class TestApiKeyResponse(BaseModel):
    status: str # "success" or "error"
    message: str
    is_valid: bool # True if key is valid, False otherwise

@router.get("/settings", response_model=SettingsDataResponse, summary="獲取系統設定")
async def read_settings(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    檢索目前系統的可配置設定。
    API Key 不會在此處返回，但會指示是否已配置。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(db, LogLevel.DEBUG, "嘗試獲取系統設定", "system_api", request_id=request_id_for_log)

    settings_response = await crud_settings.get_system_settings(db)
    
    await log_event(db, LogLevel.DEBUG, "成功獲取系統設定", "system_api", request_id=request_id_for_log, details={"settings_retrieved": True})
    return settings_response

@router.put("/settings", response_model=SettingsDataResponse, summary="更新系統設定")
async def update_settings_route(
    request: Request,
    settings_update: UpdatableSettingsData, 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    更新系統的可配置設定。
    - **ai_service.model**: 您要使用的 AI 模型 (例如 "gemini-1.5-flash")。
    - **ai_service.apiKey**: 您的 AI 服務 API 金鑰 (將存儲在 .env 文件中)。
    - **ai_service.temperature**: AI 模型溫度。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    log_payload = settings_update.model_dump(exclude_unset=True)
    if log_payload.get("aiService") and isinstance(log_payload["aiService"], dict) and log_payload["aiService"].get("apiKey"):
        log_payload["aiService"]["apiKey"] = "********"
    
    await log_event(db, LogLevel.INFO, "嘗試更新系統設定", "system_api", request_id=request_id_for_log, details={"update_payload": log_payload})

    try:
        updated_settings_response = await crud_settings.update_system_settings(db=db, settings_to_update=settings_update)
        if not updated_settings_response:
            await log_event(db, LogLevel.ERROR, "更新系統設定失敗 (CRUD 操作返回 None)", "system_api", request_id=request_id_for_log, details={"update_payload": log_payload})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新設定失敗")
        
        await log_event(db, LogLevel.INFO, "系統設定已成功更新", "system_api", request_id=request_id_for_log, details={"updated_successfully": True})
        return updated_settings_response
    except Exception as e:
        await log_event(db, LogLevel.ERROR, f"更新系統設定時發生錯誤: {str(e)}", "system_api", request_id=request_id_for_log, details={"error": str(e), "update_payload": log_payload})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新設定時發生內部錯誤: {str(e)}")

@router.post("/test-ai-api-key", response_model=TestApiKeyResponse, summary="測試 Google AI API 金鑰的有效性")
async def test_ai_api_key(
    request: Request,
    payload: TestApiKeyRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    接收一個 API 金鑰並嘗試使用它執行一個輕量級的 Google AI API 調用以驗證其有效性。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db, 
        LogLevel.INFO, 
        f"嘗試測試 Google AI API 金鑰 (結尾為 ...{payload.api_key[-4:] if len(payload.api_key) > 4 else '****'})", 
        "system_api_key_test", 
        request_id=request_id_for_log
    )

    is_valid, message = verify_google_api_key(payload.api_key)

    log_level = LogLevel.INFO if is_valid else LogLevel.WARNING
    await log_event(
        db, 
        log_level, 
        f"Google AI API 金鑰測試結果: {message}", 
        "system_api_key_test", 
        request_id=request_id_for_log, 
        details={"is_valid": is_valid, "message": message}
    )

    if is_valid:
        return TestApiKeyResponse(status="success", message=message, is_valid=True)
    else:
        # We don't raise HTTPException here as it's not an internal server error,
        # but a validation result. The client should check the 'is_valid' field.
        return TestApiKeyResponse(status="error", message=message, is_valid=False)

@router.get("/ai-models/google", response_model=List[str], summary="獲取支援的 Google AI 模型列表")
async def get_google_models_list(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    返回一個可用於設定的 Google AI 模型名稱列表。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(db, LogLevel.DEBUG, "請求 Google AI 模型列表", "system_api", request_id=request_id_for_log)
    models = get_google_ai_models()
    return models

@router.get("/connection-info", response_model=ConnectionInfo, summary="獲取手機配對連線資訊")
async def get_connection_info_route(db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    獲取用於手機應用程式配對的連線資訊，包括 QR Code 圖像數據/URL 和配對碼。
    (目前為模擬數據)
    """
    return await crud_settings.get_connection_info(db)

@router.post("/connection-info/refresh", response_model=ConnectionInfo, summary="刷新手機配對連線資訊")
async def refresh_connection_info_route(db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    請求新的手機應用程式配對連線資訊，使舊的資訊可能失效。
    (目前為模擬數據)
    """
    return await crud_settings.refresh_connection_info(db)

@router.post("/test-db-connection", response_model=TestDBConnectionResponse, summary="測試資料庫連線")
async def test_db_connection_endpoint(
    request_data: TestDBConnectionRequest,
):
    """
    測試與提供的 MongoDB URI 和資料庫名稱的連線。
    """
    try:
        result = await crud_settings.perform_db_connection_test(
            uri=request_data.uri, 
            db_name=request_data.db_name
        )
        return result
    except Exception as e:
        return TestDBConnectionResponse(
            success=False,
            message="測試資料庫連線時發生未預期的伺服器內部錯誤。",
            error_details=str(e)
        )

@router.get("/tunnel-status", response_model=TunnelStatus, summary="獲取 Cloudflare Tunnel 狀態")
async def get_tunnel_status_route(db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    檢查並返回 Cloudflare Tunnel 的當前狀態，包括是否啟用以及公開 URL。
    (目前為模擬數據)
    """
    return await crud_settings.get_tunnel_status(db) 