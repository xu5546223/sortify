import logging # 新增
import logging # 新增
from fastapi import FastAPI, Depends, HTTPException, Request # Add Request
from fastapi.exceptions import RequestValidationError # Add RequestValidationError
from fastapi.responses import JSONResponse # Add JSONResponse
from fastapi import status  # 添加 status 模組導入
from contextlib import asynccontextmanager
from .db.mongodb_utils import db_manager # 更改為相對導入
from .apis.v1 import api_v1_router as generic_v1_router # 引入 v1 路由並更改為相對導入, 並重命名
from .apis.v1 import logs as logs_api_v1 # 新增
from .apis.v1 import dashboard as dashboard_api_v1 # 新增
from .apis.v1 import auth as auth_api_v1 # <--- 新增 auth router 導入
from .apis.v1 import system as system_api_v1 # 新增 system_routes 導入
from .apis.v1 import vector_db as vector_db_api_v1 # 新增 vector_db router 導入
from .apis.v1 import embedding as embedding_api_v1 # 新增 embedding router 導入
from .apis.v1 import unified_ai as unified_ai_api_v1 # 新增統一AI router導入
from motor.motor_asyncio import AsyncIOMotorDatabase
from .dependencies import get_db
from .core.middleware import RequestContextLogMiddleware # 新增中介軟體
from .core.logging_utils import log_event # 新增日誌工具
from .models.log_models import LogLevel # 新增 LogLevel
from fastapi.middleware.cors import CORSMiddleware # 新增 CORS 中介軟體
from .core.startup import preload_on_startup
import asyncio
from .core.config import settings

# 配置標準日誌記錄器
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler() # 輸出到控制台，也可以配置輸出到檔案
    ]
)
std_logger = logging.getLogger(__name__) # 獲取 main.py 的 logger, 避免與 log_event 中的 logger 衝突

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時
    startup_success = False
    db_instance_for_log = None
    
    try:
        await db_manager.connect_to_mongo() # 確保連接已建立
        
        # 使用新的智能預熱機制
        try:
            std_logger.info("開始應用程序智能預熱...")
            await preload_on_startup()
            std_logger.info("智能預熱完成")
        except asyncio.CancelledError:
            std_logger.info("應用啟動被中斷，正在優雅關閉...")
            raise
        except Exception as e:
            std_logger.error(f"智能預熱過程發生錯誤: {e}")
            std_logger.info("將繼續啟動，功能將在首次使用時按需加載")
        
        db_for_log = db_manager.get_db_client() # 獲取已建立的連接 (這是 AsyncIOMotorClient)
        
        # 更直接的方法是 db_manager 提供一個獲取 AsyncIOMotorDatabase 的方法
        # 暫時假設 db_manager.get_database() 能返回 AsyncIOMotorDatabase
        if db_manager.db is not None: # 使用 is not None 而不是直接做布林值測試
            db_instance_for_log = db_manager.db
        elif db_for_log is not None: # 使用 is not None
            try:
                from .core.config import settings as app_settings
                if app_settings.DB_NAME:
                    db_instance_for_log = db_for_log[app_settings.DB_NAME]
            except ImportError:
                std_logger.error("無法導入 settings 來獲取 DB_NAME 以進行啟動日誌記錄")
            except AttributeError:
                 std_logger.error("app_settings 中未定義 DB_NAME")

        if db_instance_for_log is not None: # 使用 is not None
            await log_event(
                db=db_instance_for_log,
                level=LogLevel.INFO,
                message="應用程式啟動完成。",
                source="application_lifecycle",
                module_name="main",
                func_name="lifespan_startup"
            )
        else:
            std_logger.warning("無法在應用程式啟動時獲取資料庫實例以記錄日誌。")
        
        startup_success = True
        std_logger.info("Sortify AI Assistant Backend 應用程式已啟動。")
        
    except asyncio.CancelledError:
        std_logger.info("應用啟動被用戶中斷")
        raise
    except Exception as e:
        std_logger.error(f"應用啟動失敗: {e}")
        raise
    
    try:
        yield # 應用程式運行中
    except asyncio.CancelledError:
        std_logger.info("應用運行被中斷，開始清理...")
        raise
    finally:
        # 應用程式關閉時 - 確保清理工作執行
        std_logger.info("開始應用程式關閉清理...")
        
        # 關閉向量資料庫連接
        try:
            from .services.vector_db_service import vector_db_service
            vector_db_service.close_connection()
            std_logger.info("向量資料庫連接已關閉")
        except Exception as e:
            std_logger.error(f"關閉向量資料庫連接失敗: {e}")
        
        # 記錄關閉日誌
        if startup_success and db_instance_for_log is not None:
            try:
                await log_event(
                    db=db_instance_for_log,
                    level=LogLevel.INFO,
                    message="應用程式準備關閉。",
                    source="application_lifecycle",
                    module_name="main",
                    func_name="lifespan_shutdown"
                )
            except Exception as e:
                std_logger.warning(f"記錄關閉日誌失敗: {e}")
        else:
            std_logger.warning("跳過關閉日誌記錄")
        
        # 關閉數據庫連接
        try:
            await db_manager.close_mongo_connection()
            std_logger.info("MongoDB 連接已關閉")
        except Exception as e:
            std_logger.error(f"關閉 MongoDB 連接失敗: {e}")
        
        std_logger.info("Sortify AI Assistant Backend 應用程式已關閉。")

app = FastAPI(
    title="Sortify AI Assistant Backend",
    description="處理文件上傳、AI 分析、資料庫互動及提供 API 服務。",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 中介軟體設定
# 注意：在生產環境中，應將 allow_origins 明確指定為您的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # 使用 settings 中的配置
    allow_credentials=True, # 允許cookies
    allow_methods=["*"],  # 允許所有 HTTP 方法
    allow_headers=["*"],  # 允許所有 HTTP 標頭
)

# 添加中介軟體 (RequestContextLogMiddleware 應在 CORS 之後)
app.add_middleware(RequestContextLogMiddleware)

# --- Custom Exception Handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    db = await get_db() # Get DB instance for logging
    request_id = request.state.request_id if hasattr(request.state, "request_id") else "N/A"
    user_id_for_log = None # Implement logic to get user_id from token if available without full auth
    
    # Log the validation error in detail
    await log_event(
        db=db,
        level=LogLevel.WARNING,
        message="Request validation failed.",
        source="validation_error_handler",
        request_id=request_id,
        user_id=user_id_for_log, # May be None if auth hasn't run or failed
        details={"errors": exc.errors(), "body": await request.body() if await request.body() else None} # Log errors and body
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body}, # Standard FastAPI validation error response
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    db = await get_db() # Get DB instance for logging
    request_id = request.state.request_id if hasattr(request.state, "request_id") else "N/A"
    user_id_for_log = None # Implement logic to get user_id from token if available

    # Log the HTTPException
    await log_event(
        db=db,
        level=LogLevel.WARNING if exc.status_code < 500 else LogLevel.ERROR,
        message=f"HTTPException caught: {exc.detail}",
        source="http_exception_handler",
        request_id=request_id,
        user_id=user_id_for_log,
        details={"status_code": exc.status_code, "detail": exc.detail, "headers": exc.headers}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    db = await get_db() # Get DB instance for logging
    request_id = request.state.request_id if hasattr(request.state, "request_id") else "N/A"
    user_id_for_log = None # Implement logic to get user_id from token if available

    # Log the generic exception
    await log_event(
        db=db,
        level=LogLevel.CRITICAL, # Or ERROR, depending on severity assessment
        message=f"Unhandled exception: {str(exc)}",
        source="generic_exception_handler",
        request_id=request_id,
        user_id=user_id_for_log,
        details={"error_type": type(exc).__name__, "error_message": str(exc), "traceback": "Add traceback here if feasible/desired"} # Consider adding traceback
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please contact support."},
    )

# --- End of Custom Exception Handlers ---

@app.get("/")
async def read_root():
    return {"message": "歡迎使用 Sortify AI 助理後端服務"}

# 專門用於測試 MongoDB 連接的端點
@app.get("/test-db-connection")
async def test_db_connection(db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        # 嘗試執行一個簡單的操作，例如 ping 資料庫
        await db.command("ping")
        # 嘗試列出集合名稱
        collections = await db.list_collection_names()
        return {
            "connection": "成功",
            "message": "已成功連接到 MongoDB 資料庫",
            "database": db.name,
            "collections": collections
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"資料庫連接測試失敗: {str(e)}")

# 註冊 V1 API 路由
# 假設 api_v1_router 是從 apis/v1/__init__.py 匯總的路由
# 如果不是，並且您希望將所有 v1 路由都放在 /api/v1 下，
# 則 logs 和 dashboard 的 prefix 也應包含 /api/v1
app.include_router(generic_v1_router, prefix="/api/v1") # 為 generic_v1_router 添加 /api/v1 前綴

# 註冊新的 Logs 和 Dashboard 路由
app.include_router(logs_api_v1.router, prefix="/api/v1/logs", tags=["v1 - Logs"])
app.include_router(dashboard_api_v1.router, prefix="/api/v1/dashboard", tags=["v1 - Dashboard"])

# 註冊新的 Auth 路由
app.include_router(auth_api_v1.router, prefix="/api/v1/auth", tags=["v1 - Authentication"]) # <--- 新增 auth router 註冊

# 註冊新的 System 路由
app.include_router(system_api_v1.router, prefix="/api/v1/system", tags=["v1 - System"])

# 註冊新的向量資料庫路由
app.include_router(vector_db_api_v1.router, prefix="/api/v1/vector-db", tags=["v1 - Vector Database"])

# 註冊新的 Embedding 模型路由
app.include_router(embedding_api_v1.router, prefix="/api/v1/embedding", tags=["v1 - Embedding"])

# 註冊新的統一AI路由
app.include_router(unified_ai_api_v1.router, prefix="/api/v1/unified-ai", tags=["v1 - Unified AI Services"])

# 直接在 app 上註冊 CopilotKit 端點
try:
    from .copilot_setup import python_backend_sdk
    from .copilotkit.integrations.fastapi import add_fastapi_endpoint
    if python_backend_sdk:
        # 同時註冊有無斜線的路徑
        add_fastapi_endpoint(app, python_backend_sdk, "/api/v1/copilotkit_actions")
        std_logger.info("CopilotKit Actions 端點已直接註冊到 app，路徑為 /api/v1/copilotkit_actions 及 /api/v1/copilotkit_actions/")
except ImportError as e:
    std_logger.error(f"無法導入 CopilotKit SDK 或相關函數: {e}")
except Exception as e:
    std_logger.error(f"註冊 CopilotKit 端點時發生錯誤: {e}")

# 之後會在這裡引入其他 API 路由 


# ---- 用於調試路由 ----
from fastapi.routing import APIRoute
print("---- Registered Routes ----")
for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"Path: {route.path}, Name: {route.name}, Methods: {route.methods}")
    else:
        # Could be Mount or WebSocketRoute etc.
        print(f"Path: {route.path if hasattr(route, 'path') else 'N/A'}, Type: {type(route)}")
print("---- End of Routes ----") 

