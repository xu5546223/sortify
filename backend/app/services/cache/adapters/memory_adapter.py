"""
記憶體緩存適配器

使用 Python 內建數據結構實現的高速本地緩存
"""

import asyncio
import time
import pickle
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)


class MemoryCacheAdapter:
    """
    記憶體緩存適配器（L1 層）
    
    特點：
    - 極快的訪問速度（納秒級）
    - 進程內緩存，不跨實例
    - 自動 TTL 過期
    - LRU 淘汰策略
    """
    
    def __init__(
        self,
        maxsize: int = 1000,
        default_ttl: int = 300,
        name: str = "memory"
    ):
        """
        初始化記憶體緩存
        
        Args:
            maxsize: 最大緩存數量
            default_ttl: 默認 TTL（秒）
            name: 適配器名稱
        """
        self.name = name
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        
        # 使用 TTLCache 自動處理過期
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=default_ttl)
        
        # 統計信息
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0
        
        logger.info(
            f"MemoryCacheAdapter 初始化完成: "
            f"maxsize={maxsize}, default_ttl={default_ttl}s"
        )
    
    async def get(self, key: str) -> Optional[Any]:
        """獲取緩存值"""
        try:
            value = self._cache.get(key)
            if value is not None:
                self._hits += 1
                logger.debug(f"[Memory] 緩存命中: {key}")
                return value
            else:
                self._misses += 1
                logger.debug(f"[Memory] 緩存未命中: {key}")
                return None
        except Exception as e:
            logger.error(f"[Memory] 獲取緩存失敗: {key}, {e}")
            self._misses += 1
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """設置緩存值"""
        try:
            # TTLCache 不支持單個項目的自定義 TTL
            # 如果需要不同的 TTL，應該使用不同的緩存實例
            self._cache[key] = value
            self._sets += 1
            logger.debug(f"[Memory] 緩存已設置: {key}")
            return True
        except Exception as e:
            logger.error(f"[Memory] 設置緩存失敗: {key}, {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """刪除緩存"""
        try:
            if key in self._cache:
                del self._cache[key]
                self._deletes += 1
                logger.debug(f"[Memory] 緩存已刪除: {key}")
                return True
            return False
        except Exception as e:
            logger.error(f"[Memory] 刪除緩存失敗: {key}, {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在"""
        return key in self._cache
    
    async def clear(self, pattern: Optional[str] = None) -> int:
        """清理緩存"""
        try:
            if pattern is None:
                # 清理所有
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"[Memory] 已清理所有緩存: {count} 個")
                return count
            else:
                # 模式匹配清理
                keys_to_delete = [
                    k for k in self._cache.keys() 
                    if self._match_pattern(k, pattern)
                ]
                for key in keys_to_delete:
                    del self._cache[key]
                logger.info(f"[Memory] 已清理匹配緩存: {len(keys_to_delete)} 個")
                return len(keys_to_delete)
        except Exception as e:
            logger.error(f"[Memory] 清理緩存失敗: {e}")
            return 0
    
    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """批量獲取"""
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    async def mset(
        self, 
        mapping: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """批量設置"""
        try:
            for key, value in mapping.items():
                await self.set(key, value, ttl)
            return True
        except Exception as e:
            logger.error(f"[Memory] 批量設置失敗: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """獲取統計信息"""
        import sys
        
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        # 計算實際內存使用（字節）
        try:
            total_memory_bytes = sum(
                sys.getsizeof(k) + sys.getsizeof(v) 
                for k, v in self._cache.items()
            )
            memory_mb = round(total_memory_bytes / (1024 * 1024), 3)
        except Exception as e:
            logger.warning(f"[Memory] 計算內存使用失敗: {e}")
            total_memory_bytes = 0
            memory_mb = 0.0
        
        return {
            "backend": "memory",
            "name": self.name,
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "deletes": self._deletes,
            "hit_rate": round(hit_rate, 2),
            "total_requests": total_requests,
            "default_ttl": self.default_ttl,
            "memory_bytes": total_memory_bytes,
            "memory_mb": memory_mb
        }
    
    async def health_check(self) -> bool:
        """健康檢查（不計入統計）"""
        try:
            # 保存當前統計
            saved_hits = self._hits
            saved_misses = self._misses
            saved_sets = self._sets
            saved_deletes = self._deletes
            
            # 嘗試設置和獲取測試值
            test_key = "__health_check__"
            await self.set(test_key, "ok")
            value = await self.get(test_key)
            await self.delete(test_key)
            
            # 恢復統計（不計入健康檢查的操作）
            self._hits = saved_hits
            self._misses = saved_misses
            self._sets = saved_sets
            self._deletes = saved_deletes
            
            return value == "ok"
        except Exception as e:
            logger.error(f"[Memory] 健康檢查失敗: {e}")
            return False
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """
        簡單的模式匹配
        支持 * 通配符
        """
        import re
        regex_pattern = pattern.replace("*", ".*")
        return bool(re.match(f"^{regex_pattern}$", key))
