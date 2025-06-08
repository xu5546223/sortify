import time
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger(__name__)

class APIRateLimiter:
    """一個簡單的API速率限制器，用於控制請求頻率"""
    
    def __init__(self, requests_per_minute: int):
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute 必須是正數")
        self.interval = 60.0 / requests_per_minute
        self.last_request_time = 0
        self.request_count = 0

    def wait_if_needed(self):
        """同步等待，直到可以發送下一個請求"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.interval:
            wait_time = self.interval - elapsed
            logger.debug(f"速率限制：等待 {wait_time:.2f} 秒")
            time.sleep(wait_time)
            
        self.last_request_time = time.time()
        self.request_count += 1

    async def wait_if_needed_async(self):
        """非同步等待，直到可以發送下一個請求"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.interval:
            wait_time = self.interval - elapsed
            logger.debug(f"速率限制 (async)：等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)
            
        self.last_request_time = time.time()
        self.request_count += 1

    def get_status(self) -> Dict[str, Any]:
        """獲取當前限制器狀態"""
        current_time = time.time()
        return {
            "requests_per_minute_limit": 60.0 / self.interval,
            "current_minute_requests": self.request_count,
            "last_request_time": self.last_request_time,
            "time_until_window_reset": max(0, self.interval - (current_time - self.last_request_time))
        }

# 這個裝飾器在當前的異步實現中不再需要，但保留以供參考
def rate_limited_api_call(limiter: APIRateLimiter):
    """
    用於限制API調用頻率的裝飾器（同步版本）。
    注意：這個同步裝飾器不應該用在異步函數中的異步調用上。
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter.wait_if_needed()
            return func(*args, **kwargs)
        return wrapper
    return decorator

# 全局速率限制器實例
default_rate_limiter = APIRateLimiter(requests_per_minute=15) 