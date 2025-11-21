"""
Redis 緩存適配器

使用 Redis 實現的分佈式緩存
"""

import pickle
import json
from typing import Optional, Any, Dict, List
import redis.asyncio as redis
import logging

logger = logging.getLogger(__name__)


class RedisCacheAdapter:
    """
    Redis 緩存適配器（L2 層）
    
    特點：
    - 分佈式緩存，跨實例共享
    - 持久化支持
    - 毫秒級訪問速度
    - 支持多種數據類型
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl: int = 3600,
        name: str = "redis",
        enabled: bool = True
    ):
        """
        初始化 Redis 緩存
        
        Args:
            redis_url: Redis 連接 URL
            default_ttl: 默認 TTL（秒）
            name: 適配器名稱
            enabled: 是否啟用
        """
        self.name = name
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.enabled = enabled
        self.redis_client: Optional[redis.Redis] = None
        
        # 統計信息
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0
        
        logger.info(
            f"RedisCacheAdapter 已創建: "
            f"url={redis_url}, default_ttl={default_ttl}s, enabled={enabled}"
        )
    
    async def connect(self):
        """連接到 Redis"""
        if not self.enabled:
            logger.info(f"[Redis:{self.name}] 已禁用，跳過連接")
            return
        
        try:
            self.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False  # 保持二進制，支持 pickle
            )
            # 測試連接
            await self.redis_client.ping()
            logger.info(f"[Redis:{self.name}] 連接成功")
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 連接失敗: {e}")
            self.enabled = False
            self.redis_client = None
    
    async def disconnect(self):
        """斷開 Redis 連接"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info(f"[Redis:{self.name}] 連接已關閉")
    
    async def get(self, key: str) -> Optional[Any]:
        """獲取緩存值"""
        if not self.enabled or not self.redis_client:
            return None
        
        try:
            value_bytes = await self.redis_client.get(key)
            if value_bytes:
                self._hits += 1
                # 嘗試反序列化
                try:
                    value = pickle.loads(value_bytes)
                    logger.debug(f"[Redis:{self.name}] 緩存命中: {key}")
                    return value
                except:
                    # 如果 pickle 失敗，嘗試 JSON
                    try:
                        value = json.loads(value_bytes)
                        return value
                    except:
                        # 返回原始字符串
                        return value_bytes.decode('utf-8', errors='ignore')
            else:
                self._misses += 1
                logger.debug(f"[Redis:{self.name}] 緩存未命中: {key}")
                return None
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 獲取緩存失敗: {key}, {e}")
            self._misses += 1
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """設置緩存值"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            # 序列化值
            try:
                value_bytes = pickle.dumps(value)
            except:
                # pickle 失敗，嘗試 JSON
                try:
                    value_bytes = json.dumps(value).encode('utf-8')
                except:
                    # JSON 也失敗，轉字符串
                    value_bytes = str(value).encode('utf-8')
            
            # 設置 TTL
            ttl_seconds = ttl if ttl is not None else self.default_ttl
            
            if ttl_seconds > 0:
                await self.redis_client.setex(key, ttl_seconds, value_bytes)
            else:
                await self.redis_client.set(key, value_bytes)
            
            self._sets += 1
            logger.debug(f"[Redis:{self.name}] 緩存已設置: {key}, TTL={ttl_seconds}s")
            return True
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 設置緩存失敗: {key}, {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """刪除緩存"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.delete(key)
            if result > 0:
                self._deletes += 1
                logger.debug(f"[Redis:{self.name}] 緩存已刪除: {key}")
                return True
            return False
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 刪除緩存失敗: {key}, {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.exists(key)
            return result > 0
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 檢查存在失敗: {key}, {e}")
            return False
    
    async def clear(self, pattern: Optional[str] = None) -> int:
        """清理緩存"""
        if not self.enabled or not self.redis_client:
            return 0
        
        try:
            if pattern is None:
                # 清理所有（謹慎使用！）
                await self.redis_client.flushdb()
                logger.warning(f"[Redis:{self.name}] 已清理所有緩存")
                return -1  # 返回特殊值表示清理所有
            else:
                # 模式匹配清理
                cursor = 0
                count = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor=cursor, 
                        match=pattern, 
                        count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
                logger.info(f"[Redis:{self.name}] 已清理匹配緩存: {count} 個")
                return count
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 清理緩存失敗: {e}")
            return 0
    
    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """批量獲取"""
        if not self.enabled or not self.redis_client:
            return {}
        
        try:
            values = await self.redis_client.mget(keys)
            result = {}
            for key, value_bytes in zip(keys, values):
                if value_bytes:
                    try:
                        result[key] = pickle.loads(value_bytes)
                    except:
                        try:
                            result[key] = json.loads(value_bytes)
                        except:
                            result[key] = value_bytes.decode('utf-8', errors='ignore')
            return result
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 批量獲取失敗: {e}")
            return {}
    
    async def mset(
        self, 
        mapping: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """批量設置"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            # 序列化所有值
            serialized_mapping = {}
            for key, value in mapping.items():
                try:
                    serialized_mapping[key] = pickle.dumps(value)
                except:
                    try:
                        serialized_mapping[key] = json.dumps(value).encode('utf-8')
                    except:
                        serialized_mapping[key] = str(value).encode('utf-8')
            
            # 批量設置
            await self.redis_client.mset(serialized_mapping)
            
            # 如果有 TTL，逐個設置
            if ttl and ttl > 0:
                for key in serialized_mapping.keys():
                    await self.redis_client.expire(key, ttl)
            
            self._sets += len(mapping)
            return True
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 批量設置失敗: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """獲取統計信息"""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        stats = {
            "backend": "redis",
            "name": self.name,
            "enabled": self.enabled,
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "deletes": self._deletes,
            "hit_rate": round(hit_rate, 2),
            "total_requests": total_requests,
            "default_ttl": self.default_ttl,
            "memory_bytes": 0,
            "memory_mb": 0.0
        }
        
        # 嘗試獲取 Redis 服務器信息
        if self.enabled and self.redis_client:
            try:
                info = await self.redis_client.info()
                used_memory = info.get("used_memory", 0)
                memory_mb = round(used_memory / (1024 * 1024), 3)
                
                stats.update({
                    "redis_version": info.get("redis_version", "unknown"),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "memory_bytes": used_memory,
                    "memory_mb": memory_mb
                })
            except Exception as e:
                logger.warning(f"[Redis:{self.name}] 獲取服務器信息失敗: {e}")
        
        return stats
    
    async def health_check(self) -> bool:
        """健康檢查（不計入統計）"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            # 保存當前統計
            saved_hits = self._hits
            saved_misses = self._misses
            saved_sets = self._sets
            saved_deletes = self._deletes
            
            # 嘗試 ping
            await self.redis_client.ping()
            
            # 嘗試設置和獲取測試值
            test_key = f"__health_check__{self.name}__"
            await self.set(test_key, "ok", ttl=10)
            value = await self.get(test_key)
            await self.delete(test_key)
            
            # 恢復統計（不計入健康檢查的操作）
            self._hits = saved_hits
            self._misses = saved_misses
            self._sets = saved_sets
            self._deletes = saved_deletes
            
            return value == "ok"
        except Exception as e:
            logger.error(f"[Redis:{self.name}] 健康檢查失敗: {e}")
            return False
