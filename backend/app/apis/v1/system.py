from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List

from ...dependencies import get_db
from ...models.user_models import User # Import User
from ...core.security import get_current_active_user # Import auth dependency
from ...models.system_models import (
    SettingsDataResponse,
    UpdatableSettingsData,
    ConnectionInfo,
    TunnelStatus,
    TestDBConnectionRequest,
    TestDBConnectionResponse,
)
from ...crud import crud_settings
from ...services.ai.unified_ai_config import verify_google_api_key, get_google_ai_models
from ...core.logging_utils import log_event
from ...models.log_models import LogLevel
from ...core.logging_decorators import log_api_operation

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
@log_api_operation(operation_name="獲取系統設置", log_success=True, success_level=LogLevel.DEBUG)
async def read_settings(
    request: Request, 
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    檢索目前系統的可配置設定。
    API Key 不會在此處返回，但會指示是否已配置。
    """
    return await crud_settings.get_system_settings(db)

@router.put("/settings", response_model=SettingsDataResponse, summary="更新系統設定")
@log_api_operation(operation_name="更新系統設置", log_success=True)
async def update_settings_route(
    request: Request,
    settings_update: UpdatableSettingsData, 
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    更新系統的可配置設定。
    - **ai_service.model**: 您要使用的 AI 模型 (例如 "gemini-1.5-flash")。
    - **ai_service.apiKey**: 您的 AI 服務 API 金鑰 (將存儲在 .env 文件中)。
    - **ai_service.temperature**: AI 模型溫度。
    TODO: This should ideally be an admin-only endpoint.
    """
    updated_settings_response = await crud_settings.update_system_settings(db=db, settings_to_update=settings_update)
    if not updated_settings_response:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update settings.")
    
    return updated_settings_response

@router.post("/test-ai-api-key", response_model=TestApiKeyResponse, summary="測試 Google AI API 金鑰的有效性")
@log_api_operation(operation_name="測試 API 金鑰", log_success=True)
async def test_ai_api_key(
    request: Request,
    payload: TestApiKeyRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    接收一個 API 金鑰並嘗試使用它執行一個輕量級的 Google AI API 調用以驗證其有效性。
    """
    is_valid, message = verify_google_api_key(payload.api_key)

    if is_valid:
        return TestApiKeyResponse(status="success", message=message, is_valid=True)
    else:
        return TestApiKeyResponse(status="error", message=message, is_valid=False)

@router.get("/ai-models/google", response_model=List[str], summary="獲取支援的 Google AI 模型列表")
@log_api_operation(operation_name="獲取 AI 模型列表", log_success=True, success_level=LogLevel.DEBUG)
async def get_google_models_list(
    request: Request, 
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    返回一個可用於設定的 Google AI 模型名稱列表。
    """
    return get_google_ai_models()

@router.get("/connection-info", response_model=ConnectionInfo, summary="獲取手機配對連線資訊")
@log_api_operation(operation_name="獲取連線信息", log_success=True, success_level=LogLevel.DEBUG)
async def get_connection_info_route(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    獲取用於手機應用程式配對的連線資訊，包括 QR Code 圖像數據/URL 和配對碼。
    (目前為模擬數據)
    """
    return await crud_settings.get_connection_info(db)

@router.post("/connection-info/refresh", response_model=ConnectionInfo, summary="刷新手機配對連線資訊")
@log_api_operation(operation_name="刷新連線信息", log_success=True)
async def refresh_connection_info_route(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    請求新的手機應用程式配對連線資訊，使舊的資訊可能失效。
    (目前為模擬數據)
    """
    return await crud_settings.refresh_connection_info(db)

@router.post("/test-db-connection", response_model=TestDBConnectionResponse, summary="測試資料庫連線")
async def test_db_connection_endpoint(
    request: Request, # Added Request for request_id
    request_data: TestDBConnectionRequest,
    db: AsyncIOMotorDatabase = Depends(get_db), # Added db for logging
    current_user: User = Depends(get_current_active_user)
):
    """
    測試與提供的 MongoDB URI 和資料庫名稱的連線。
    """
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db,
        level=LogLevel.INFO,
        message=f"User {current_user.username} initiated DB connection test.",
        source="api.system.test_db_connection",
        user_id=str(current_user.id),
        request_id=request_id_val,
        # Do not log request_data.uri directly as it's sensitive. Log that a test was made.
        details={"test_uri_provided": bool(request_data.uri), "test_dbname_provided": bool(request_data.db_name)}
    )

    try:
        # crud_settings.perform_db_connection_test already has internal logging for success/failure of the test itself
        result = await crud_settings.perform_db_connection_test(
            uri=request_data.uri, 
            db_name=request_data.db_name
        )
        # Log the outcome of the test from the API perspective
        await log_event(
            db=db,
            level=LogLevel.INFO if result.success else LogLevel.WARNING,
            message=f"DB connection test completed for user {current_user.username}. Result: {result.message}",
            source="api.system.test_db_connection",
            user_id=str(current_user.id),
            request_id=request_id_val,
            details={"success": result.success, "message": result.message, "error_details_if_any": result.error_details}
        )
        return result
    except Exception as e:
        # This catches exceptions in the endpoint logic itself, not from perform_db_connection_test if it handles its own errors.
        logger.error(f"Unexpected error in test_db_connection_endpoint by user {current_user.username}: {e}", exc_info=True)
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message="DB connection test endpoint encountered an unexpected server error.",
            source="api.system.test_db_connection",
            user_id=str(current_user.id),
            request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during the database connection test." # User-friendly
        )

@router.get("/tunnel-status", response_model=TunnelStatus, summary="獲取 Cloudflare Tunnel 狀態")
async def get_tunnel_status_route(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db), # db might be used for logging if needed
    current_user: User = Depends(get_current_active_user) # Add auth dependency
):
    """
    檢查並返回 Cloudflare Tunnel 的當前狀態，包括是否啟用以及公開 URL。
    (目前為模擬數據)
    """
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db,
        level=LogLevel.DEBUG,
        message=f"User {current_user.username} requested tunnel status.",
        source="api.system.get_tunnel_status",
        user_id=str(current_user.id),
        request_id=request_id_val
    )
    return await crud_settings.get_tunnel_status(db) 