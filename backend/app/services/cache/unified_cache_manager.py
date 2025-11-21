"""
統一緩存管理器

提供統一的多層緩存管理接口，自動處理 L1 (Memory) → L2 (Redis) → L3 (Context) 的緩存策略
"""

import asyncio
import hashlib
from typing import Optional, Any, Dict, List, Callable
from enum import Enum
from dataclasses import dataclass
import logging

from app.services.cache.adapters import MemoryCacheAdapter, RedisCacheAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheLayer(str, Enum):
    """緩存層級"""
    MEMORY = "memory"      # L1: 本地記憶體
    REDIS = "redis"        # L2: Redis
    CONTEXT = "context"    # L3: Google Context Cache


class CacheNamespace(str, Enum):
    """緩存命名空間"""
    CONVERSATION = "conv"          # 對話上下文
    PROMPT = "prompt"              # 提示詞模板
    EMBEDDING = "embed"            # 向量 Embedding
    DOCUMENT = "doc"               # 文檔內容
    AI_RESPONSE = "ai_resp"        # AI 回答
    USER_SESSION = "session"       # 用戶會話
    SCHEMA = "schema"              # 資料庫 Schema
    GENERAL = "general"            # 通用緩存


@dataclass
class CacheConfig:
    """緩存配置"""
    namespace: CacheNamespace
    layers: List[CacheLayer] = None  # None 表示使用所有可用層
    ttl_l1: int = 300                # L1 TTL (5分鐘)
    ttl_l2: int = 3600               # L2 TTL (1小時)
    ttl_l3: int = 86400              # L3 TTL (24小時)
    
    def __post_init__(self):
        if self.layers is None:
            self.layers = [CacheLayer.MEMORY, CacheLayer.REDIS]


class UnifiedCacheManager:
    """
    統一緩存管理器
    
    核心功能：
    1. 多層緩存自動管理（L1 → L2 → L3）
    2. 自動降級和回填
    3. 統一的 get/set/delete 接口
    4. 命名空間隔離
    5. 統計和監控
    
    使用範例：
        # 基本使用
        value = await unified_cache.get("user:123", namespace=CacheNamespace.USER_SESSION)
        await unified_cache.set("user:123", {"name": "John"}, namespace=CacheNamespace.USER_SESSION)
        
        # 自定義配置
        config = CacheConfig(
            namespace=CacheNamespace.PROMPT,
            layers=[CacheLayer.MEMORY, CacheLayer.REDIS],
            ttl_l1=600,
            ttl_l2=7200
        )
        await unified_cache.set_with_config("my_prompt", content, config)
    """
    
    def __init__(self):
        """初始化統一緩存管理器"""
        # 初始化各層適配器
        self.l1_memory = MemoryCacheAdapter(
            maxsize=1000,
            default_ttl=300,  # 5分鐘
            name="L1_memory"
        )
        
        self.l2_redis = RedisCacheAdapter(
            redis_url=settings.REDIS_URL,
            default_ttl=3600,  # 1小時
            name="L2_redis",
            enabled=settings.REDIS_ENABLED
        )
        
        # L3 Context Cache 會在需要時初始化
        self.l3_context = None
        
        # 緩存層映射
        self._layer_adapters = {
            CacheLayer.MEMORY: self.l1_memory,
            CacheLayer.REDIS: self.l2_redis,
        }
        
        # 默認配置（按命名空間）
        self._default_configs: Dict[CacheNamespace, CacheConfig] = {
            CacheNamespace.CONVERSATION: CacheConfig(
                namespace=CacheNamespace.CONVERSATION,
                layers=[CacheLayer.MEMORY, CacheLayer.REDIS],
                ttl_l1=300,    # 5分鐘
                ttl_l2=3600    # 1小時
            ),
            CacheNamespace.PROMPT: CacheConfig(
                namespace=CacheNamespace.PROMPT,
                layers=[CacheLayer.MEMORY, CacheLayer.REDIS],
                ttl_l1=1800,   # 30分鐘
                ttl_l2=7200    # 2小時
            ),
            CacheNamespace.AI_RESPONSE: CacheConfig(
                namespace=CacheNamespace.AI_RESPONSE,
                layers=[CacheLayer.MEMORY, CacheLayer.REDIS],
                ttl_l1=900,    # 15分鐘
                ttl_l2=3600    # 1小時
            ),
            CacheNamespace.EMBEDDING: CacheConfig(
                namespace=CacheNamespace.EMBEDDING,
                layers=[CacheLayer.MEMORY],  # 只用記憶體
                ttl_l1=600     # 10分鐘
            ),
        }
        
        logger.info("UnifiedCacheManager 初始化完成")
    
    async def initialize(self):
        """初始化所有緩存適配器"""
        try:
            # 連接 Redis
            await self.l2_redis.connect()
            logger.info("統一緩存管理器初始化完成")
        except Exception as e:
            logger.error(f"初始化緩存管理器失敗: {e}")
    
    async def shutdown(self):
        """關閉所有連接"""
        try:
            await self.l2_redis.disconnect()
            logger.info("統一緩存管理器已關閉")
        except Exception as e:
            logger.error(f"關閉緩存管理器失敗: {e}")
    
    def _build_key(self, key: str, namespace: CacheNamespace) -> str:
        """構建帶命名空間的完整鍵"""
        return f"{namespace.value}:{key}"
    
    def _get_config(self, namespace: CacheNamespace) -> CacheConfig:
        """獲取命名空間的配置"""
        return self._default_configs.get(
            namespace,
            CacheConfig(namespace=namespace)  # 使用默認配置
        )
    
    async def get(
        self,
        key: str,
        namespace: CacheNamespace = CacheNamespace.GENERAL,
        layers: Optional[List[CacheLayer]] = None
    ) -> Optional[Any]:
        """
        獲取緩存值（自動多層查找）
        
        查找順序：L1 → L2 → L3
        找到後自動回填到上層緩存
        
        Args:
            key: 緩存鍵
            namespace: 命名空間
            layers: 指定查找的層級，None 表示使用配置的所有層
            
        Returns:
            緩存的值，不存在則返回 None
        """
        full_key = self._build_key(key, namespace)
        config = self._get_config(namespace)
        search_layers = layers if layers is not None else config.layers
        
        value = None
        found_layer = None
        
        # 逐層查找
        for layer in search_layers:
            adapter = self._layer_adapters.get(layer)
            if not adapter:
                continue
            
            try:
                value = await adapter.get(full_key)
                if value is not None:
                    found_layer = layer
                    logger.debug(f"[UnifiedCache] 在 {layer.value} 層找到: {full_key}")
                    break
            except Exception as e:
                logger.warning(f"[UnifiedCache] {layer.value} 層查找失敗: {e}")
                continue
        
        # 如果找到了，回填到上層緩存
        if value is not None and found_layer:
            await self._backfill(full_key, value, config, found_layer, search_layers)
        
        return value
    
    async def _backfill(
        self,
        full_key: str,
        value: Any,
        config: CacheConfig,
        found_layer: CacheLayer,
        search_layers: List[CacheLayer]
    ):
        """
        回填緩存到上層
        
        例如：在 L2 找到數據，回填到 L1
        """
        found_index = search_layers.index(found_layer)
        upper_layers = search_layers[:found_index]
        
        for layer in upper_layers:
            adapter = self._layer_adapters.get(layer)
            if not adapter:
                continue
            
            try:
                # 根據層級使用不同的 TTL
                ttl = config.ttl_l1 if layer == CacheLayer.MEMORY else config.ttl_l2
                await adapter.set(full_key, value, ttl=ttl)
                logger.debug(f"[UnifiedCache] 回填到 {layer.value}: {full_key}")
            except Exception as e:
                logger.warning(f"[UnifiedCache] 回填到 {layer.value} 失敗: {e}")
    
    async def set(
        self,
        key: str,
        value: Any,
        namespace: CacheNamespace = CacheNamespace.GENERAL,
        ttl: Optional[int] = None,
        layers: Optional[List[CacheLayer]] = None
    ) -> bool:
        """
        設置緩存值（自動多層寫入）
        
        Args:
            key: 緩存鍵
            value: 要緩存的值
            namespace: 命名空間
            ttl: 過期時間（秒），None 表示使用配置的 TTL
            layers: 指定寫入的層級，None 表示使用配置的所有層
            
        Returns:
            是否全部設置成功
        """
        full_key = self._build_key(key, namespace)
        config = self._get_config(namespace)
        write_layers = layers if layers is not None else config.layers
        
        success_count = 0
        total_count = len(write_layers)
        
        # 寫入所有層
        for layer in write_layers:
            adapter = self._layer_adapters.get(layer)
            if not adapter:
                continue
            
            try:
                # 根據層級使用不同的 TTL
                layer_ttl = ttl if ttl is not None else (
                    config.ttl_l1 if layer == CacheLayer.MEMORY else config.ttl_l2
                )
                
                success = await adapter.set(full_key, value, ttl=layer_ttl)
                if success:
                    success_count += 1
                    logger.debug(f"[UnifiedCache] 寫入 {layer.value} 成功: {full_key}")
            except Exception as e:
                logger.warning(f"[UnifiedCache] 寫入 {layer.value} 失敗: {e}")
        
        return success_count == total_count
    
    async def delete(
        self,
        key: str,
        namespace: CacheNamespace = CacheNamespace.GENERAL,
        layers: Optional[List[CacheLayer]] = None
    ) -> bool:
        """
        刪除緩存（所有層）
        
        Args:
            key: 緩存鍵
            namespace: 命名空間
            layers: 指定刪除的層級，None 表示刪除所有層
            
        Returns:
            是否有至少一層刪除成功
        """
        full_key = self._build_key(key, namespace)
        config = self._get_config(namespace)
        delete_layers = layers if layers is not None else config.layers
        
        success = False
        
        for layer in delete_layers:
            adapter = self._layer_adapters.get(layer)
            if not adapter:
                continue
            
            try:
                result = await adapter.delete(full_key)
                if result:
                    success = True
                    logger.debug(f"[UnifiedCache] 從 {layer.value} 刪除: {full_key}")
            except Exception as e:
                logger.warning(f"[UnifiedCache] 從 {layer.value} 刪除失敗: {e}")
        
        return success
    
    async def exists(
        self,
        key: str,
        namespace: CacheNamespace = CacheNamespace.GENERAL
    ) -> bool:
        """檢查鍵是否存在（任意層）"""
        value = await self.get(key, namespace)
        return value is not None
    
    async def clear(
        self,
        namespace: Optional[CacheNamespace] = None,
        pattern: Optional[str] = None
    ) -> Dict[str, int]:
        """
        清理緩存
        
        Args:
            namespace: 指定命名空間，None 表示所有
            pattern: 匹配模式
            
        Returns:
            每層清理的數量
        """
        results = {}
        
        # 構建清理模式
        if namespace:
            clear_pattern = f"{namespace.value}:{pattern if pattern else '*'}"
        else:
            clear_pattern = pattern
        
        for layer_name, adapter in self._layer_adapters.items():
            try:
                count = await adapter.clear(clear_pattern)
                results[layer_name.value] = count
                logger.info(f"[UnifiedCache] {layer_name.value} 清理了 {count} 個緩存")
            except Exception as e:
                logger.error(f"[UnifiedCache] {layer_name.value} 清理失敗: {e}")
                results[layer_name.value] = -1
        
        return results
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        獲取統計信息
        
        Returns:
            包含所有層級統計的字典
        """
        stats = {
            "layers": {},
            "namespaces": list(CacheNamespace),
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # 收集各層統計
        for layer_name, adapter in self._layer_adapters.items():
            try:
                layer_stats = await adapter.get_stats()
                stats["layers"][layer_name.value] = layer_stats
            except Exception as e:
                logger.error(f"[UnifiedCache] 獲取 {layer_name.value} 統計失敗: {e}")
                stats["layers"][layer_name.value] = {"error": str(e)}
        
        # 計算總體命中率
        total_hits = sum(
            layer.get("hits", 0) 
            for layer in stats["layers"].values() 
            if isinstance(layer, dict)
        )
        total_requests = sum(
            layer.get("total_requests", 0) 
            for layer in stats["layers"].values() 
            if isinstance(layer, dict)
        )
        stats["overall_hit_rate"] = (
            round(total_hits / total_requests * 100, 2) 
            if total_requests > 0 else 0
        )
        
        return stats
    
    async def health_check(self) -> Dict[str, bool]:
        """
        健康檢查
        
        Returns:
            各層的健康狀態
        """
        health = {}
        
        for layer_name, adapter in self._layer_adapters.items():
            try:
                is_healthy = await adapter.health_check()
                health[layer_name.value] = is_healthy
            except Exception as e:
                logger.error(f"[UnifiedCache] {layer_name.value} 健康檢查失敗: {e}")
                health[layer_name.value] = False
        
        return health


# 全局統一緩存實例
unified_cache = UnifiedCacheManager()
