"""
緩存適配器基礎接口

定義所有緩存後端必須實現的統一接口
"""

from typing import Protocol, Optional, Any, Dict, List
from abc import abstractmethod


class ICacheBackend(Protocol):
    """
    統一緩存接口
    
    所有緩存適配器都必須實現這個接口，確保可以無縫切換後端
    """
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        獲取緩存值
        
        Args:
            key: 緩存鍵
            
        Returns:
            緩存的值，不存在則返回 None
        """
        ...
    
    @abstractmethod
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """
        設置緩存值
        
        Args:
            key: 緩存鍵
            value: 要緩存的值
            ttl: 過期時間（秒），None 表示永不過期
            
        Returns:
            是否設置成功
        """
        ...
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        刪除緩存
        
        Args:
            key: 緩存鍵
            
        Returns:
            是否刪除成功
        """
        ...
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        檢查鍵是否存在
        
        Args:
            key: 緩存鍵
            
        Returns:
            是否存在
        """
        ...
    
    @abstractmethod
    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        清理緩存
        
        Args:
            pattern: 可選的匹配模式，None 表示清理所有
            
        Returns:
            清理的鍵數量
        """
        ...
    
    @abstractmethod
    async def mget(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量獲取
        
        Args:
            keys: 鍵列表
            
        Returns:
            鍵值對字典
        """
        ...
    
    @abstractmethod
    async def mset(
        self, 
        mapping: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """
        批量設置
        
        Args:
            mapping: 鍵值對字典
            ttl: 過期時間（秒）
            
        Returns:
            是否設置成功
        """
        ...
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """
        獲取統計信息
        
        Returns:
            統計信息字典
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康檢查
        
        Returns:
            是否健康
        """
        ...
