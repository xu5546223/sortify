"""
AI服務模塊

統一AI服務、配置和提示詞管理

注意: 為避免循環導入,不在 __init__.py 中導入所有內容
請直接從子模塊導入,例如:
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
"""

# 只導出模塊名稱,不實際導入(避免循環依賴)
__all__ = [
    'unified_ai_service_simplified',
    'unified_ai_config',
    'prompt_manager_simplified',
    'ai_cache_manager'
]

