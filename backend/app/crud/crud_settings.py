from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models.system_models import (
    SettingsDataResponse, 
    UpdatableSettingsData, 
    ConnectionInfo, 
    TunnelStatus,
    DBSettingsSchema, # Schema for MongoDB storage
    AIServiceSettingsStored, # For constructing response
    StoredAISettings, # For DB storage
    DatabaseSettings, # Add DatabaseSettings here
    AIServiceSettingsInput, # 確保 AIServiceSettingsInput 被導入如果 UpdatableSettingsData 用到
    TestDBConnectionResponse
)
from ..core.config import settings as app_env_settings
from ..services.unified_ai_config import save_ai_api_key_to_env
from typing import Optional, Dict, Any
import logging
from dotenv import set_key, find_dotenv, load_dotenv
import os
from ..db.mongodb_utils import DatabaseUnavailableError, db_manager # 導入 DatabaseUnavailableError 和 db_manager
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure
import uuid

from ..core.logging_utils import log_event # Added log_event
from ..models.log_models import LogLevel # Added LogLevel
# from app.schemas.settings import AIServiceSettings, AIServiceSettingsUpdate, SystemSettings, SystemSettingsCreate, SystemSettingsUpdate, GlobalAISettingsDB # 保留此行或根據實際需要調整

logger = logging.getLogger(__name__)

CONFIG_DOCUMENT_ID = "main_system_settings"

async def get_system_settings(db: AsyncIOMotorDatabase) -> SettingsDataResponse:
    """
    獲取系統設定。MongoDB URI/DB Name 從 .env 讀取。
    其他設定嘗試從資料庫讀取，如果資料庫不可用，則使用預設值。
    """
    db_connected = db_manager.is_connected # 直接檢查 db_manager 的狀態
    
    # MongoDB URI 和 DB Name 始終從環境變數讀取
    db_settings_from_env = DatabaseSettings(
        uri=app_env_settings.MONGODB_URL,
        db_name=app_env_settings.DB_NAME
    )

    # AI 服務設定 和 autoConnect/autoSync 嘗試從資料庫讀取
    stored_ai_settings_from_db = StoredAISettings() # 預設
    auto_connect_from_db = None
    auto_sync_from_db = None

    if db_connected:
        try:
            actual_db_instance = db_manager.get_database() # 從管理器獲取 DB 實例
            if actual_db_instance is not None: # <--- 修正這裡
                config_collection = actual_db_instance.system_config
                db_doc = await config_collection.find_one({"_id": CONFIG_DOCUMENT_ID})
                if db_doc:
                    logger.debug(f"從資料庫載入設定 (AI服務、自動連接/同步): {db_doc}")
                    if "ai_service" in db_doc and isinstance(db_doc["ai_service"], dict):
                        logger.debug(f"DB ai_service content before parsing: {db_doc['ai_service']}")
                        # 假設 StoredAISettings 模型本身已不包含 force_stable_model
                        stored_ai_settings_from_db = StoredAISettings(**db_doc["ai_service"])
                        logger.debug(f"Parsed stored_ai_settings_from_db: model={stored_ai_settings_from_db.model}, "
                                     f"ensure_chinese={stored_ai_settings_from_db.ensure_chinese_output}, "
                                     f"max_tokens={stored_ai_settings_from_db.max_output_tokens}")
                    auto_connect_from_db = db_doc.get("auto_connect")
                    auto_sync_from_db = db_doc.get("auto_sync")
                else:
                    logger.info("資料庫中未找到系統設定文件，AI 及其他 DB 設定將使用預設值。")
            else:
                # 如果 db_manager.is_connected 為 True 但 get_database() 返回 None，這是一個不一致的狀態
                # 將 db_connected 更新為 False，並記錄警告
                db_connected = False 
                logger.warning("資料庫狀態不一致：is_connected 為 True 但 get_database() 返回 None。將視為未連接。")
        except Exception as e: 
            logger.error(f"讀取資料庫設定時發生錯誤: {e}", exc_info=True)
            db_connected = False # 任何從資料庫讀取設定的錯誤都應將 db_connected 視為 False
            # stored_ai_settings_from_db, auto_connect_from_db, auto_sync_from_db 保持預設值
    
    if not db_connected:
         logger.warning("資料庫未連接。AI服務設定 (model, temp) 和 autoConnect/autoSync 將使用預設值或為 None。")

    is_api_key_configured_in_env = bool(app_env_settings.GOOGLE_API_KEY)
    
    # Log before creating AIServiceSettingsStored
    logger.debug(f"Values for AIServiceSettingsStored: provider={stored_ai_settings_from_db.provider}, "
                 f"model={stored_ai_settings_from_db.model}, temp={stored_ai_settings_from_db.temperature}, "
                 f"ensure_chinese={stored_ai_settings_from_db.ensure_chinese_output}, "
                 f"max_tokens={stored_ai_settings_from_db.max_output_tokens}, "
                 f"prompt_input_max_length={stored_ai_settings_from_db.prompt_input_max_length}")

    ai_service_response = AIServiceSettingsStored(
        provider=stored_ai_settings_from_db.provider,
        model=stored_ai_settings_from_db.model,
        temperature=stored_ai_settings_from_db.temperature,
        is_api_key_configured=is_api_key_configured_in_env,
        ensure_chinese_output=stored_ai_settings_from_db.ensure_chinese_output,
        max_output_tokens=stored_ai_settings_from_db.max_output_tokens,
        prompt_input_max_length=stored_ai_settings_from_db.prompt_input_max_length
    )

    # 新增日誌：檢查 Pydantic 的序列化結果
    try:
        dumped_dict = ai_service_response.model_dump(by_alias=True, exclude_none=False, exclude_defaults=False) # exclude_none=False 確保 null 值被包含
        dumped_json = ai_service_response.model_dump_json(by_alias=True, exclude_none=False, exclude_defaults=False)
        logger.debug(f"ai_service_response.model_dump(by_alias=True, exclude_defaults=False): {dumped_dict}")
        logger.debug(f"ai_service_response.model_dump_json(by_alias=True, exclude_defaults=False): {dumped_json}")
    except Exception as e:
        logger.error(f"Error during model_dump/model_dump_json for ai_service_response: {e}")

    final_settings_response = SettingsDataResponse(
        aiService=ai_service_response,
        database=db_settings_from_env,
        autoConnect=auto_connect_from_db,
        autoSync=auto_sync_from_db,
        isDatabaseConnected=db_connected # 使用我們確定的連接狀態
    )

    # Log successful retrieval of system settings
    await log_event(
        db=db, # Passing db, though it might be None if db_manager was not connected
        level=LogLevel.INFO,
        message="System settings retrieved.",
        source="crud_settings.get_system_settings",
        details={
            "database_connected_status": db_connected,
            "env_db_uri_present": bool(app_env_settings.MONGODB_URL),
            "env_db_name_present": bool(app_env_settings.DB_NAME),
            "env_google_api_key_present": bool(app_env_settings.GOOGLE_API_KEY),
            "retrieved_auto_connect_from_db": auto_connect_from_db is not None,
            "retrieved_auto_sync_from_db": auto_sync_from_db is not None,
            "retrieved_ai_settings_from_db": stored_ai_settings_from_db.model != StoredAISettings().model # Check if model differs from default
        }
    )
    return final_settings_response

async def update_system_settings(db: AsyncIOMotorDatabase, settings_to_update: UpdatableSettingsData) -> Optional[SettingsDataResponse]:
    """
    更新系統設定。API Key, MongoDB URI 和 DB Name 將存儲到 .env。
    其他設定（如 AI model, temperature, autoConnect, autoSync）嘗試存儲到資料庫，如果資料庫不可用則跳過。
    """
    config_collection = None # 推遲初始化，直到確認資料庫可用
    update_payload_for_db: Dict[str, Any] = {}
    api_key_to_save: Optional[str] = None
    mongodb_uri_to_save: Optional[str] = None
    db_name_to_save: Optional[str] = None
    env_vars_changed = False

    # 處理來自 settings_to_update 的值，準備 .env 更新和 DB 更新的 payload
    if settings_to_update.ai_service:
        ai_service_input = settings_to_update.ai_service
        # 假設 StoredAISettings 模型已不包含 force_stable_model
        db_ai_service_data_to_store = StoredAISettings().model_dump() 

        if ai_service_input.model is not None: db_ai_service_data_to_store["model"] = ai_service_input.model
        if ai_service_input.provider is not None: db_ai_service_data_to_store["provider"] = ai_service_input.provider
        if ai_service_input.temperature is not None: db_ai_service_data_to_store["temperature"] = ai_service_input.temperature
        if ai_service_input.ensure_chinese_output is not None: db_ai_service_data_to_store["ensure_chinese_output"] = ai_service_input.ensure_chinese_output
        if ai_service_input.max_output_tokens is not None: db_ai_service_data_to_store["max_output_tokens"] = ai_service_input.max_output_tokens
        if ai_service_input.prompt_input_max_length is not None: 
            db_ai_service_data_to_store["prompt_input_max_length"] = ai_service_input.prompt_input_max_length
            logger.info(f"🔧 設置 prompt_input_max_length: {ai_service_input.prompt_input_max_length}")
        
        logger.info(f"準備保存到DB的 ai_service 數據: {db_ai_service_data_to_store}")
        update_payload_for_db["ai_service"] = db_ai_service_data_to_store

    if settings_to_update.database: # database 包含 uri 和 dbName，主要用於更新 .env
        db_settings_input = settings_to_update.database
        if db_settings_input.uri is not None:
            mongodb_uri_to_save = db_settings_input.uri
        if db_settings_input.db_name is not None:
            db_name_to_save = db_settings_input.db_name
        # 不再將 database settings 存入 update_payload_for_db，因為它們由 .env 管理
        # 如果 DatabaseSettings 模型中有其他不由 .env 管理的欄位，則需要保留它們到 DB
        # update_payload_for_db["database"] = db_settings_input.model_dump(exclude_unset=True, by_alias=False)
    
    if settings_to_update.auto_connect is not None:
        update_payload_for_db["auto_connect"] = settings_to_update.auto_connect
    if settings_to_update.auto_sync is not None:
        update_payload_for_db["auto_sync"] = settings_to_update.auto_sync

    # --- .env 更新邏輯 (獨立於資料庫連線) ---
    env_path = find_dotenv(usecwd=True, raise_error_if_not_found=False)
    if not env_path: 
        env_file_name = app_env_settings.model_config.get('env_file', '.env')
        env_path = os.path.join(os.getcwd(), env_file_name) 
        logger.warning(f".env file not found by find_dotenv(usecwd=True). Will use/create at CWD: {env_path}")
    logger.info(f"Using .env path for updates: {env_path}")

    if mongodb_uri_to_save is not None:
        try:
            set_key(env_path, "MONGODB_URL", mongodb_uri_to_save)
            app_env_settings.MONGODB_URL = mongodb_uri_to_save 
            logger.info(f"MONGODB_URL saved to .env file: {env_path}. Live settings updated.")
            env_vars_changed = True
        except Exception as e:
            logger.error(f"Error saving MONGODB_URL to .env: {e}", exc_info=True)

    if db_name_to_save is not None:
        try:
            set_key(env_path, "DB_NAME", db_name_to_save)
            app_env_settings.DB_NAME = db_name_to_save 
            logger.info(f"DB_NAME saved to .env file: {env_path}. Live settings updated.")
            env_vars_changed = True
        except Exception as e:
            logger.error(f"Error saving DB_NAME to .env: {e}", exc_info=True)
    
    if env_vars_changed:
        try:
            if load_dotenv(dotenv_path=env_path, override=True):
                 logger.info(f"Reloaded .env file from: {env_path} to reflect changes in current process's os.environ.")
            else:
                 logger.warning(f"load_dotenv did not find .env file at {env_path} or it was empty during reload attempt.")
        except Exception as e:
             logger.error(f"Error reloading .env after updates: {e}", exc_info=True)

    # --- 資料庫更新邏輯 (依賴資料庫連線) ---
    db_update_attempted = False
    db_update_successful = True # 假設成功，除非嘗試了但失敗了，或者根本沒嘗試

    if not update_payload_for_db and not env_vars_changed:
        logger.info("沒有提供需要更新到資料庫或 .env 的設定項。")
        # 即使沒有任何東西被更新，也返回當前的設定狀態 (包含最新的 db 連線狀態)
        return await get_system_settings(db) # db 參數是 FastAPI 注入的 get_db 結果

    if update_payload_for_db: # 只有在有東西要更新到 DB 時才嘗試
        db_update_attempted = True
        if db_manager.is_connected: # 使用 db_manager 的狀態
            try:
                actual_db_instance = db_manager.get_database()
                if actual_db_instance is not None: # <--- 修正這裡 (如果 update_system_settings 中也有類似邏輯)
                    # 在這裡重新讀取 current_settings_doc 以正確更新 ai_service
                    # 這確保我們只更新傳入的欄位，而不是用預設值覆蓋現有DB中的AI設定
                    current_settings_doc = await actual_db_instance.system_config.find_one({"_id": CONFIG_DOCUMENT_ID})
                    if current_settings_doc and "ai_service" in current_settings_doc and "ai_service" in update_payload_for_db:
                        # 假設 StoredAISettings 模型已不包含 force_stable_model
                        existing_ai_db = StoredAISettings(**current_settings_doc["ai_service"])
                        update_for_ai = update_payload_for_db["ai_service"]
                        
                        if "model" in update_for_ai and update_for_ai["model"] is not None: existing_ai_db.model = update_for_ai["model"]
                        if "provider" in update_for_ai and update_for_ai["provider"] is not None: existing_ai_db.provider = update_for_ai["provider"]
                        if "temperature" in update_for_ai and update_for_ai["temperature"] is not None: existing_ai_db.temperature = update_for_ai["temperature"]
                        if "ensure_chinese_output" in update_for_ai and update_for_ai["ensure_chinese_output"] is not None: existing_ai_db.ensure_chinese_output = update_for_ai["ensure_chinese_output"]
                        if "max_output_tokens" in update_for_ai and update_for_ai["max_output_tokens"] is not None: existing_ai_db.max_output_tokens = update_for_ai["max_output_tokens"]
                        if "prompt_input_max_length" in update_for_ai and update_for_ai["prompt_input_max_length"] is not None: 
                            existing_ai_db.prompt_input_max_length = update_for_ai["prompt_input_max_length"]
                            logger.info(f"✅ 更新 prompt_input_max_length 到現有DB配置: {update_for_ai['prompt_input_max_length']}")
                        
                        # 假設 StoredAISettings.model_dump() 自然不會包含 force_stable_model
                        final_ai_payload = existing_ai_db.model_dump()
                        logger.info(f"合併後的最終 ai_service payload: {final_ai_payload}")
                        update_payload_for_db["ai_service"] = final_ai_payload
                    
                    await actual_db_instance.system_config.find_one_and_update(
                        {"_id": CONFIG_DOCUMENT_ID},
                        {"$set": update_payload_for_db},
                        upsert=True
                    )
                    logger.info(f"系統設定已在資料庫中更新。Payload: {update_payload_for_db}")
                else:
                    db_update_successful = False
                    logger.error("嘗試更新資料庫設定失敗：無法獲取資料庫實例，即使 db_manager.is_connected 為 True。")
            except Exception as e: 
                db_update_successful = False
                logger.error(f"更新系統設定到資料庫時發生錯誤: {e}", exc_info=True)
        else:
            db_update_successful = False # 因為資料庫未連接，所以DB更新不成功
            logger.warning(f"資料庫未連接。設定 {list(update_payload_for_db.keys())} 將不會被更新到資料庫。")
    elif not update_payload_for_db and env_vars_changed: # 只有 .env 變更，沒有DB變更
        db_update_successful = True # 沒有嘗試DB更新，所以不算失敗

    final_settings = await get_system_settings(db) 

    # 如果AI服務設定有更新，重新載入AI任務配置
    if "ai_service" in update_payload_for_db and db_update_successful:
        try:
            from app.services.unified_ai_config import unified_ai_config
            logger.info("🔄 準備重新載入AI任務配置...")
            reload_success = await unified_ai_config.reload_task_configs(db_manager.get_database())
            if reload_success:
                logger.info("✅ AI任務配置已重新載入以應用新的模型偏好設定")
                logger.info(f"當前 _user_global_ai_preferences: {unified_ai_config._user_global_ai_preferences}")
            else:
                logger.warning("❌ AI任務配置重新載入失敗")
        except Exception as e:
            logger.error(f"重新載入AI任務配置時發生錯誤: {e}", exc_info=True)
    else:
        logger.info(f"跳過AI配置重新載入: ai_service在payload中={('ai_service' in update_payload_for_db)}, db_update_successful={db_update_successful}")

    if env_vars_changed and db_update_attempted and not db_update_successful:
        logger.warning("成功更新 .env 中的設定，但資料庫中的對應設定更新失敗或被跳過。")

    # Log the outcome of the update operation
    updated_keys_in_db = list(update_payload_for_db.keys())
    updated_keys_in_env = []
    if mongodb_uri_to_save: updated_keys_in_env.append("MONGODB_URL")
    if db_name_to_save: updated_keys_in_env.append("DB_NAME")
    # API key is handled by save_ai_api_key_to_env, not directly here for .env update list

    await log_event(
        db=db,
        level=LogLevel.INFO,
        message="System settings update process completed.",
        source="crud_settings.update_system_settings",
        details={
            "env_update_attempted": env_vars_changed,
            "db_update_attempted": db_update_attempted,
            "db_update_successful": db_update_successful,
            "updated_keys_in_db_attempt": updated_keys_in_db if db_update_attempted else [],
            "updated_keys_in_env_attempt": updated_keys_in_env # Actual saving depends on set_key success
        }
    )
    
    return final_settings

async def get_user_selected_ai_model(db: AsyncIOMotorDatabase) -> Optional[str]:
    """
    從資料庫獲取用戶選擇的預設 AI 模型名稱。
    如果未設定或資料庫無法訪問，則返回 None。
    """
    model_to_return = None # Initialize
    db_was_connected = db_manager.is_connected # Store initial state for logging details

    if not db_was_connected:
        logger.warning("get_user_selected_ai_model: 資料庫未連接，無法獲取用戶設定的 AI 模型。")
        # Log this specific condition
        await log_event(
            db=db, # db here is the one passed to the function, likely None or non-functional
            level=LogLevel.WARNING,
            message="Attempted to get user selected AI model, but DB not connected at call time.",
            source="crud_settings.get_user_selected_ai_model",
            details={"db_manager_connected_status": db_was_connected}
        )
        return None
    try:
        actual_db_instance = db_manager.get_database()
        if actual_db_instance is not None:
            config_collection = actual_db_instance.system_config
            db_doc = await config_collection.find_one({"_id": CONFIG_DOCUMENT_ID})
            if db_doc and "ai_service" in db_doc and isinstance(db_doc["ai_service"], dict):
                ai_settings = StoredAISettings(**db_doc["ai_service"])
                if ai_settings.model:
                    logger.debug(f"從資料庫獲取用戶選擇的 AI 模型: {ai_settings.model}")
                    model_to_return = ai_settings.model # Assign to model_to_return
                else:
                    logger.debug("資料庫中的 ai_service 設定中未指定模型。")
            else:
                logger.debug("資料庫中未找到 ai_service 設定或設定格式不正確。")
        else:
            logger.warning("get_user_selected_ai_model: 無法獲取資料庫實例，即使 db_manager 報告已連接。")
            # Log this condition
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="Could not get DB instance for user selected AI model, though db_manager reported connected.",
                source="crud_settings.get_user_selected_ai_model",
                details={"db_manager_connected_status": db_was_connected}
            )
            return None
    except Exception as e:
        logger.error(f"獲取用戶選擇的 AI 模型時發生錯誤: {e}", exc_info=True)
        # Log error during fetch
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message="Error fetching user selected AI model.",
            source="crud_settings.get_user_selected_ai_model",
            details={"error": str(e), "error_type": type(e).__name__, "db_manager_connected_status": db_was_connected}
        )
        return None # Return None on error

    # Log successful fetch or if not found (after try-except)
    await log_event(
        db=db,
        level=LogLevel.DEBUG, # DEBUG as it might be frequent
        message="User selected AI model retrieval attempt finished.",
        source="crud_settings.get_user_selected_ai_model",
        details={
            "model_found": model_to_return is not None,
            "retrieved_model_name": model_to_return if model_to_return else "N/A",
            "db_manager_connected_status": db_was_connected
        }
    )
    return model_to_return

async def get_connection_info(db: AsyncIOMotorDatabase) -> ConnectionInfo:
    """
    獲取用於手機配對的連線資訊。
    目前返回模擬數據。
    實際應用中，這裡會生成 QR Code、配對碼，並包含伺服器 URL。
    """
    # TODO: 實現真實的 QR Code 生成和配對碼邏輯
    # TODO: 從設定或動態獲取 server_url
    
    # 模擬 server_url，之後應從 config 或 Cloudflare Tunnel 服務獲取
    server_url_from_config = app_env_settings.CLOUDFLARE_TUNNEL_URL or "http://localhost:8000"

    return ConnectionInfo(
        qr_code_image="https://via.placeholder.com/200.png?text=Scan+Me", # 模擬 QR Code 圖片 URL
        pairing_code="XYZ123", # 模擬配對碼
        server_url=server_url_from_config
    )

async def refresh_connection_info(db: AsyncIOMotorDatabase) -> ConnectionInfo:
    """
    刷新並獲取新的手機配對連線資訊。
    目前返回與 get_connection_info 相同的模擬數據。
    """
    # TODO: 實現刷新邏輯，例如使舊的配對碼/QR Code 失效，生成新的。
    return await get_connection_info(db)


async def get_tunnel_status(db: AsyncIOMotorDatabase) -> TunnelStatus:
    """
    獲取 Cloudflare Tunnel 的狀態。
    目前返回模擬數據。
    實際應用中，可能需要與 cloudflared 互動或檢查網路狀態。
    """
    # TODO: 實現真實的 Tunnel 狀態檢查邏輯。
    #       這可能涉及到運行 shell 命令 (如果 cloudflared CLI 可用) 
    #       或檢查特定的網路端點。
    
    # 模擬 Tunnel 狀態
    is_active_mock = True 
    url_mock = app_env_settings.CLOUDFLARE_TUNNEL_URL # "https://your-tunnel-name.trycloudflare.com" 
    error_message_mock = None

    if not url_mock: # 如果 .env 中沒有 CLOUDFLARE_TUNNEL_URL
        is_active_mock = False
        error_message_mock = "Cloudflare Tunnel URL 未在 .env 中配置。"
        
    return TunnelStatus(
        is_active=is_active_mock,
        url=url_mock if is_active_mock else None,
        error_message=error_message_mock
    ) 

# 新增：執行資料庫連線測試的函數
async def perform_db_connection_test(uri: str, db_name: str) -> TestDBConnectionResponse:
    """
    嘗試使用提供的 URI 和資料庫名稱建立臨時的 MongoDB 連線並執行 ping。
    返回連線測試的結果。
    """
    temp_client: Optional[AsyncIOMotorClient] = None
    try:
        logger.info(f"嘗試測試資料庫連線: URI='{uri}', DB='{db_name}'")
        # 建立臨時客戶端，設置合理的超時以避免長時間阻塞
        temp_client = AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=5000, # 5 秒超時
            uuidRepresentation='standard'
        )
        
        # 執行 ping 命令來驗證連線和認證 (如果 URI 中包含)
        await temp_client.admin.command('ping')
        
        # 嘗試訪問指定的資料庫 (這也會檢查 db_name 是否有效，儘管 ping 成功通常意味著伺服器可達)
        # db_instance = temp_client[db_name]
        # await db_instance.list_collection_names() # 可以選擇性地執行更深入的檢查

        logger.info(f"資料庫連線測試成功: URI='{uri}', DB='{db_name}'")
        return TestDBConnectionResponse(
            success=True, 
            message="資料庫連線測試成功。"
        )
    except ConnectionFailure as e:
        logger.error(f"資料庫連線測試失敗 (ConnectionFailure): URI='{uri}', DB='{db_name}'. Error: {e}")
        return TestDBConnectionResponse(
            success=False, 
            message="資料庫連線失敗：無法連接到指定的伺服器或認證失敗。",
            error_details=str(e)
        )
    except OperationFailure as e: # Pymongo 操作錯誤，例如認證失敗後 ping
        logger.error(f"資料庫連線測試失敗 (OperationFailure): URI='{uri}', DB='{db_name}'. Error: {e}")
        # 檢查常見的認證錯誤代碼
        if e.code == 18: # AuthenticationFailed
            message = "資料庫連線失敗：認證失敗，請檢查使用者名稱和密碼。"
        else:
            message = f"資料庫操作失敗：{e.details.get('errmsg', '未知操作錯誤')}。"
        return TestDBConnectionResponse(
            success=False, 
            message=message,
            error_details=str(e)
        )
    except Exception as e:
        logger.error(f"資料庫連線測試時發生意外錯誤: URI='{uri}', DB='{db_name}'. Error: {e}", exc_info=True)
        return TestDBConnectionResponse(
            success=False, 
            message="資料庫連線測試時發生意外錯誤。",
            error_details=str(e)
        )
    finally:
        if temp_client:
            temp_client.close()
            logger.info(f"已關閉臨時資料庫連線測試客戶端: URI='{uri}'") 