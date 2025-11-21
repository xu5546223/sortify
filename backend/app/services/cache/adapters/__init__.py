"""
緩存適配器模組

提供不同緩存後端的統一接口實現
"""

from .base import ICacheBackend
from .memory_adapter import MemoryCacheAdapter
from .redis_adapter import RedisCacheAdapter

__all__ = [
    "ICacheBackend",
    "MemoryCacheAdapter",
    "RedisCacheAdapter",
]
