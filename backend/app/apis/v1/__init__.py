# API version 1 routers
from fastapi import APIRouter

# from .system import router as system_router # 不再由此處的 api_v1_router 包含
from .users import router as users_router
from .documents import router as documents_router # 導入新的 documents_router
from .unified_ai import router as unified_ai_router  # 已切換到簡化版的AI路由
# 簡化版路由已整合到主路由中，不再需要並行測試路由
# 預計會引入 documents, logs, dashboard 路由
# from . import documents

api_v1_router = APIRouter() # 移除 prefix="/api/v1"，前綴將在 main.py 中統一添加

# api_v1_router.include_router(system_router, prefix="/system", tags=["System"]) # 移除
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])
api_v1_router.include_router(documents_router, prefix="/documents", tags=["Documents"]) # 註冊新的 documents_router
api_v1_router.include_router(unified_ai_router, prefix="/ai", tags=["AI Services (Simplified)"])  # 已經是簡化版本
# 移除並行測試路由，因為主路由已經切換到簡化版本
# api_v1_router.include_router(documents.router, prefix="/documents", tags=["Documents"]) 