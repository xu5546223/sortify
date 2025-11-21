"""
緩存服務模組

提供多層緩存管理功能：
- ConversationCacheService: 對話緩存（Redis）
- GoogleContextCacheService: Google Context Cache
- UnifiedCacheManager: 統一緩存管理器（推薦使用）
"""

# 舊的緩存服務（已移除）
# from .conversation_cache_service import conversation_cache_service  # 已遷移到統一緩存
from .google_context_cache_service import google_context_cache_service

# 新的統一緩存管理器
from .unified_cache_manager import (
    unified_cache,
    UnifiedCacheManager,
    CacheLayer,
    CacheNamespace,
    CacheConfig,
)

__all__ = [
    # 舊服務（保留 Google Context Cache）
    "google_context_cache_service",
    
    # 新的統一緩存
    "unified_cache",
    "UnifiedCacheManager",
    "CacheLayer",
    "CacheNamespace",
    "CacheConfig",
]
