import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from motor.motor_asyncio import AsyncIOMotorDatabase
from .db.mongodb_utils import db_manager
from .db.db_init import create_database_indexes
from .dependencies import get_db
from .core.middleware import RequestContextLogMiddleware
from .core.logging_utils import log_event
from .models.log_models import LogLevel
from .core.startup import preload_on_startup
from .core.config import settings
from .core.exceptions import SortifyBaseException

# API 路由導入
from .apis.v1 import api_v1_router as generic_v1_router
from .apis.v1 import (
    logs as logs_api_v1,
    dashboard as dashboard_api_v1,
    auth as auth_api_v1,
    system as system_api_v1,
    vector_db as vector_db_api_v1,
    embedding as embedding_api_v1,
    unified_ai as unified_ai_api_v1,
    cache_monitoring as cache_monitoring_api_v1,
    gmail as gmail_api_v1,
    clustering as clustering_api_v1,
    conversations as conversations_api_v1,
    device_auth as device_auth_api_v1,
    qa_analytics as qa_analytics_api_v1,
    qa_stream as qa_stream_api_v1,
    suggested_questions as suggested_questions_api_v1,
)

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
        if db_manager.db is not None:
            await create_database_indexes(db_manager.db) # 創建索引

        
        # 初始化統一緩存管理器
        try:
            from .services.cache import unified_cache
            await unified_cache.initialize()
            std_logger.info("統一緩存管理器初始化完成")
        except Exception as e:
            std_logger.warning(f"統一緩存管理器初始化失敗: {e}")
        
        # Redis 連接已整合到統一緩存管理器中
        # 由 unified_cache.initialize() 自動管理
        
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
        
        # 關閉統一緩存管理器
        try:
            from .services.cache import unified_cache
            await unified_cache.shutdown()
            std_logger.info("統一緩存管理器已關閉")
        except Exception as e:
            std_logger.error(f"關閉統一緩存管理器失敗: {e}")
        
        # Redis 連接管理已整合到統一緩存中
        # 不需要額外關閉
        
        # 關閉向量資料庫連接
        try:
            from .services.vector.vector_db_service import vector_db_service
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
    allow_origins=settings.ALLOWED_ORIGINS + ["http://localhost:3000"],  # 使用 settings 中的配置
    allow_credentials=True, # 允許cookies
    allow_methods=["*"],  # 允許所有 HTTP 方法
    allow_headers=["*"],  # 允許所有 HTTP 標頭
)

# 添加中介軟體 (RequestContextLogMiddleware 應在 CORS 之後)
app.add_middleware(RequestContextLogMiddleware)

# --- Custom Exception Handlers ---

@app.exception_handler(SortifyBaseException)
async def sortify_exception_handler(request: Request, exc: SortifyBaseException):
    """處理自定義 Sortify 異常"""
    db = await get_db()
    request_id = request.state.request_id if hasattr(request.state, "request_id") else "N/A"
    
    # 記錄錯誤
    await log_event(
        db=db,
        level=LogLevel.ERROR if exc.status_code >= 500 else LogLevel.WARNING,
        message=f"Sortify Exception: {exc.message}",
        source="sortify_exception_handler",
        request_id=request_id,
        details={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            **exc.details
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )

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

# 註冊 V1 API 路由 - 使用配置列表統一管理
ROUTERS_CONFIG = [
    {"router": generic_v1_router, "prefix": "/api/v1", "tags": ["v1"]},
    {"router": logs_api_v1.router, "prefix": "/api/v1/logs", "tags": ["v1 - Logs"]},
    {"router": dashboard_api_v1.router, "prefix": "/api/v1/dashboard", "tags": ["v1 - Dashboard"]},
    {"router": auth_api_v1.router, "prefix": "/api/v1/auth", "tags": ["v1 - Authentication"]},
    {"router": system_api_v1.router, "prefix": "/api/v1/system", "tags": ["v1 - System"]},
    {"router": vector_db_api_v1.router, "prefix": "/api/v1/vector-db", "tags": ["v1 - Vector Database"]},
    {"router": embedding_api_v1.router, "prefix": "/api/v1/embedding", "tags": ["v1 - Embedding"]},
    {"router": unified_ai_api_v1.router, "prefix": "/api/v1/unified-ai", "tags": ["v1 - Unified AI Services"]},
    {"router": cache_monitoring_api_v1.router, "prefix": "/api/v1/cache", "tags": ["v1 - Cache Monitoring"]},
    {"router": gmail_api_v1.router, "prefix": "/api/v1/gmail", "tags": ["v1 - Gmail Services"]},
    {"router": clustering_api_v1.router, "prefix": "/api/v1/clustering", "tags": ["v1 - Clustering"]},
    {"router": conversations_api_v1.router, "prefix": "/api/v1", "tags": ["v1 - Conversations"]},
    {"router": qa_analytics_api_v1.router, "prefix": "/api/v1/qa/analytics", "tags": ["v1 - QA Analytics"]},
    {"router": qa_stream_api_v1.router, "prefix": "/api/v1", "tags": ["v1 - QA Streaming"]},
    {"router": device_auth_api_v1.router, "prefix": "/api/v1/device-auth", "tags": ["v1 - Device Authentication"]},
    {"router": suggested_questions_api_v1.router, "prefix": "/api/v1", "tags": ["v1 - Suggested Questions"]},
]

# 批量註冊路由
for config in ROUTERS_CONFIG:
    app.include_router(**config)

std_logger.info(f"已註冊 {len(ROUTERS_CONFIG)} 個路由模組") 

