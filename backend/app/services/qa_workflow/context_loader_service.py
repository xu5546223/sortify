"""
對話上下文載入服務

延遲載入對話上下文,只在需要時才從 Redis/MongoDB 載入
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.models.context_config import context_config
from app.models.question_models import ConversationContext

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class ContextLoaderService:
    """上下文載入服務 - 延遲載入策略"""
    
    async def load_conversation_context_if_needed(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: Optional[str],
        user_id: str,
        requires_context: bool
    ) -> Optional[ConversationContext]:
        """
        只在需要時載入對話上下文
        
        Args:
            db: 數據庫連接
            conversation_id: 對話ID
            user_id: 用戶ID
            requires_context: 是否需要上下文(來自分類結果)
            
        Returns:
            ConversationContext or None: 對話上下文
        """
        # 如果不需要上下文,直接返回 None
        if not requires_context:
            logger.debug("不需要載入對話上下文(requires_context=False)")
            return None
        
        # 如果沒有對話ID,無法載入
        if not conversation_id:
            logger.debug("沒有對話ID,無法載入上下文")
            return None
        
        logger.info(f"載入對話上下文: conversation_id={conversation_id}")
        
        try:
            conversation_uuid = UUID(conversation_id)
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            
            # 先嘗試從緩存獲取消息（目前直接返回 None，使用 MongoDB）
            recent_messages, _, _ = await self._load_from_cache(
                db,
                conversation_uuid,
                user_uuid
            )
            
            # 總是從 MongoDB 獲取文檔緩存（Redis不緩存文檔ID）
            _, cached_doc_ids, cached_doc_data = await self._load_from_database(
                db,
                conversation_uuid,
                user_uuid
            )
            
            # 如果消息也沒命中Redis，從MongoDB獲取消息
            if not recent_messages:
                recent_messages, _, _ = await self._load_from_database(
                    db,
                    conversation_uuid,
                    user_uuid
                )
            
            # 轉換 cached_document_data 從 dict 到 list（如果需要）
            cached_doc_list = None
            if cached_doc_data:
                if isinstance(cached_doc_data, dict):
                    # 從 dict 轉換為 list（dict 的 key 是 document_id）
                    cached_doc_list = list(cached_doc_data.values())
                elif isinstance(cached_doc_data, list):
                    # 已經是 list 格式
                    cached_doc_list = cached_doc_data
            
            context = ConversationContext(
                conversation_id=conversation_id,
                recent_messages=recent_messages or [],
                cached_document_ids=cached_doc_ids or [],
                cached_document_data=cached_doc_list,
                message_count=len(recent_messages) if recent_messages else 0
            )
            
            logger.info(
                f"上下文載入完成: {len(context.recent_messages)} 條消息, "
                f"{len(context.cached_document_ids)} 個緩存文檔"
            )
            
            return context
            
        except Exception as e:
            logger.error(f"載入對話上下文失敗: {e}", exc_info=True)
            # 失敗時返回空上下文而不是 None,確保流程可以繼續
            return ConversationContext(
                conversation_id=conversation_id,
                recent_messages=[],
                cached_document_ids=[],
                cached_document_data=None,
                message_count=0
            )
    
    async def _load_from_cache(
        self,
        db: AsyncIOMotorDatabase,
        conversation_uuid: UUID,
        user_uuid: UUID
    ) -> Tuple[Optional[List[Dict]], List[str], Optional[List[Dict]]]:
        """
        從緩存載入對話上下文
        
        注意：conversation_cache_service 已廢棄，
        現在直接使用 MongoDB 查詢（對話數據 Redis 加速效果有限）
        """
        # 直接返回 None，讓調用方使用 _load_from_database
        # 這樣可以保持接口兼容性，同時移除對廢棄服務的依賴
        return None, [], None
    
    async def _load_from_database(
        self,
        db: AsyncIOMotorDatabase,
        conversation_uuid: UUID,
        user_uuid: UUID
    ) -> Tuple[Optional[List[Dict]], List[str], Optional[List[Dict]]]:
        """從 MongoDB 數據庫載入"""
        try:
            from app.crud import crud_conversations
            
            # 獲取最近消息
            recent_messages = await crud_conversations.get_recent_messages(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid,
                limit=5
            )
            
            # 獲取已緩存的文檔
            cached_doc_ids, cached_doc_data = await crud_conversations.get_cached_documents(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid
            )
            
            # 將消息轉換為字典格式
            messages_dict = None
            if recent_messages:
                messages_dict = [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat() if hasattr(msg, 'created_at') else None
                    }
                    for msg in recent_messages
                ]
            
            logger.debug(
                f"從MongoDB載入了 {len(messages_dict) if messages_dict else 0} 條消息, "
                f"{len(cached_doc_ids) if cached_doc_ids else 0} 個緩存文檔"
            )
            
            return messages_dict, cached_doc_ids or [], cached_doc_data
            
        except Exception as e:
            logger.error(f"從數據庫載入失敗: {e}", exc_info=True)
            return None, [], None
    
    def format_conversation_history(
        self,
        recent_messages: List[Dict[str, Any]]
    ) -> str:
        """
        格式化對話歷史為上下文字符串
        
        Args:
            recent_messages: 最近的消息列表
            
        Returns:
            str: 格式化的對話歷史
        """
        if not recent_messages or len(recent_messages) == 0:
            return ""
        
        history_parts = [f"=== 對話歷史(最近 {len(recent_messages)} 條) ==="]
        
        for msg in recent_messages:
            role_name = "用戶" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")
            
            # 使用統一配置的截斷長度
            max_length = context_config.PREVIEW_MAX_LENGTH
            if len(content) > max_length:
                content = content[:max_length] + "..."
            
            history_parts.append(f"{role_name}: {content}")
        
        history_parts.append("=== 當前問題 ===")
        
        return "\n".join(history_parts)


# 創建全局實例
context_loader_service = ContextLoaderService()

