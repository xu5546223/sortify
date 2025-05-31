# API version 1 routers
from fastapi import APIRouter

# from .system import router as system_router # 不再由此處的 api_v1_router 包含
from .users import router as users_router
from .documents import router as documents_router # 導入新的 documents_router
from .unified_ai import router as unified_ai_router  # 已切換到簡化版的AI路由
# 簡化版路由已整合到主路由中，不再需要並行測試路由
# 預計會引入 documents, logs, dashboard 路由
# from . import documents

# --- CopilotKit Integration --- 
import logging
try:
    from ...copilot_setup import python_backend_sdk # 嘗試從 app.copilot_setup 導入
    from copilotkit.integrations.fastapi import add_fastapi_endpoint
    copilot_v1_logger = logging.getLogger(__name__)
    if not copilot_v1_logger.hasHandlers(): # 避免重複設定 handler
        logging.basicConfig(level=logging.INFO) # 基本配置
except ImportError as e:
    # 如果導入失敗，設置 python_backend_sdk 為 None 並記錄錯誤
    # 這樣即使 copilot_setup.py 有問題，應用也能啟動，但 CopilotKit 功能會受限
    logging.getLogger(__name__).error(f"無法導入 CopilotKit SDK (python_backend_sdk) 從 app.copilot_setup: {e}. CopilotKit v1 端點將不會被註冊。")
    python_backend_sdk = None
# --- End of CopilotKit Integration --- 

api_v1_router = APIRouter() # 移除 prefix="/api/v1"，前綴將在 main.py 中統一添加

# api_v1_router.include_router(system_router, prefix="/system", tags=["System"]) # 移除
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])
api_v1_router.include_router(documents_router, prefix="/documents", tags=["Documents"]) # 註冊新的 documents_router
api_v1_router.include_router(unified_ai_router, prefix="/ai", tags=["AI Services (Simplified)"])  # 已經是簡化版本
# 移除並行測試路由，因為主路由已經切換到簡化版本
# api_v1_router.include_router(documents.router, prefix="/documents", tags=["Documents"]) 

# --- CopilotKit Endpoint Registration ---
# 下面的代碼已移至 main.py 直接註冊到 app 上
# if python_backend_sdk:
#     # 這個端點現在會是 /api/v1/copilotkit_actions (因為 api_v1_router 在 main.py 中有 /api/v1 前綴)
#     # 使用更通用的路徑名，例如 copilotkit_actions
#     add_fastapi_endpoint(api_v1_router, python_backend_sdk, "/copilotkit_actions/")
#     if 'copilot_v1_logger' in locals():
#       copilot_v1_logger.info("CopilotKit Actions 端點已註冊到 api_v1_router，路徑為 /copilotkit_actions/")
# --- End of CopilotKit Endpoint Registration --- 