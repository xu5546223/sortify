import json
import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime
import redis.asyncio as redis

from app.core.config import settings
from app.models.conversation_models import ConversationMessage, ConversationInDB

logger = logging.getLogger(__name__)


class ConversationCacheService:
    """對話緩存服務 - 使用 Redis 緩存活躍對話"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.enabled = settings.REDIS_ENABLED
        self.ttl = settings.REDIS_CONVERSATION_TTL
        
    async def connect(self):
        """連接到 Redis"""
        if not self.enabled:
            logger.info("Redis 緩存已禁用")
            return
            
        try:
            self.redis_client = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            # 測試連接
            await self.redis_client.ping()
            logger.info("成功連接到 Redis")
        except Exception as e:
            logger.error(f"連接 Redis 失敗: {e}")
            self.enabled = False
            self.redis_client = None
    
    async def disconnect(self):
        """斷開 Redis 連接"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis 連接已關閉")
    
    def _get_cache_key(self, user_id: UUID, conversation_id: UUID) -> str:
        """生成緩存鍵"""
        return f"conversation:{user_id}:{conversation_id}"
    
    async def get_conversation(
        self, 
        user_id: UUID, 
        conversation_id: UUID
    ) -> Optional[ConversationInDB]:
        """
        從緩存獲取對話
        
        Args:
            user_id: 用戶ID
            conversation_id: 對話ID
            
        Returns:
            對話對象，如果不存在則返回 None
        """
        if not self.enabled or not self.redis_client:
            return None
        
        try:
            cache_key = self._get_cache_key(user_id, conversation_id)
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                logger.debug(f"緩存命中: {cache_key}")
                data = json.loads(cached_data)
                return ConversationInDB(**data)
            else:
                logger.debug(f"緩存未命中: {cache_key}")
                return None
        except Exception as e:
            logger.error(f"從 Redis 獲取對話失敗: {e}")
            return None
    
    async def set_conversation(
        self, 
        user_id: UUID, 
        conversation: ConversationInDB
    ) -> bool:
        """
        將對話保存到緩存
        
        Args:
            user_id: 用戶ID
            conversation: 對話對象
            
        Returns:
            是否成功保存
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            cache_key = self._get_cache_key(user_id, conversation.id)
            data = conversation.model_dump(mode='json')
            
            # 轉換 datetime 為字符串
            if isinstance(data.get('created_at'), datetime):
                data['created_at'] = data['created_at'].isoformat()
            if isinstance(data.get('updated_at'), datetime):
                data['updated_at'] = data['updated_at'].isoformat()
            
            for msg in data.get('messages', []):
                if isinstance(msg.get('timestamp'), datetime):
                    msg['timestamp'] = msg['timestamp'].isoformat()
            
            await self.redis_client.setex(
                cache_key,
                self.ttl,
                json.dumps(data, ensure_ascii=False)
            )
            logger.debug(f"對話已緩存: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"保存對話到 Redis 失敗: {e}")
            return False
    
    async def get_recent_messages(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 5
    ) -> Optional[List[ConversationMessage]]:
        """
        從緩存獲取最近的消息
        
        Args:
            user_id: 用戶ID
            conversation_id: 對話ID
            limit: 消息數量限制
            
        Returns:
            消息列表，如果不存在則返回 None
        """
        conversation = await self.get_conversation(user_id, conversation_id)
        if conversation and conversation.messages:
            return conversation.messages[-limit:]
        return None
    
    async def invalidate_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID
    ) -> bool:
        """
        使對話緩存失效（刪除）
        
        Args:
            user_id: 用戶ID
            conversation_id: 對話ID
            
        Returns:
            是否成功刪除
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            cache_key = self._get_cache_key(user_id, conversation_id)
            result = await self.redis_client.delete(cache_key)
            logger.debug(f"緩存已失效: {cache_key}")
            return result > 0
        except Exception as e:
            logger.error(f"刪除 Redis 緩存失敗: {e}")
            return False
    
    async def update_conversation_ttl(
        self,
        user_id: UUID,
        conversation_id: UUID
    ) -> bool:
        """
        更新對話緩存的 TTL（延長緩存時間）
        
        Args:
            user_id: 用戶ID
            conversation_id: 對話ID
            
        Returns:
            是否成功更新
        """
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            cache_key = self._get_cache_key(user_id, conversation_id)
            result = await self.redis_client.expire(cache_key, self.ttl)
            return result
        except Exception as e:
            logger.error(f"更新 Redis TTL 失敗: {e}")
            return False


# 全局實例
conversation_cache_service = ConversationCacheService()

