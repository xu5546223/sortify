"""
統一對話上下文輔助工具

統一所有handler的對話歷史載入邏輯,避免重複代碼
"""
import logging
from typing import Optional
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class UnifiedContextHelper:
    """統一上下文輔助工具"""
    
    @staticmethod
    async def load_and_format_conversation_history(
        db: AsyncIOMotorDatabase,
        conversation_id: Optional[str],
        user_id: Optional[str],
        limit: int = 5,
        max_content_length: int = 2000,  # 默認2000字，生成答案時保留完整信息
        preserve_full_content: bool = False  # 是否保留完整內容（不截斷）
    ) -> str:
        """
        載入並格式化對話歷史為文本
        
        這是一個統一的輔助方法,所有handler都可以使用
        避免在每個handler中重複相同的載入邏輯
        
        Args:
            db: 數據庫連接
            conversation_id: 對話ID
            user_id: 用戶ID
            limit: 載入消息數量
            max_content_length: 單條消息最大長度（當preserve_full_content=False時生效）
            preserve_full_content: 是否保留完整內容（意圖分類時建議True）
            
        Returns:
            str: 格式化的對話歷史文本
        """
        if not conversation_id or not user_id or db is None:
            return ""
        
        try:
            from app.crud import crud_conversations
            
            conversation_uuid = UUID(conversation_id)
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            
            recent_messages = await crud_conversations.get_recent_messages(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid,
                limit=limit
            )
            
            if not recent_messages:
                return ""
            
            # 格式化為文本
            history_text = "=== 對話歷史 ===\n"
            for msg in recent_messages:
                role_name = "用戶" if msg.role == "user" else "助手"
                content = msg.content
                
                # 根據配置決定是否截斷
                if not preserve_full_content and len(content) > max_content_length:
                    content = content[:max_content_length] + "..."
                # 如果preserve_full_content=True，保留完整內容
                
                history_text += f"{role_name}: {content}\n"
            
            history_text += "=== 當前問題 ===\n"
            
            logger.debug(f"格式化了{len(recent_messages)}條歷史消息")
            return history_text
            
        except Exception as e:
            logger.warning(f"載入對話歷史失敗: {e}")
            return ""
    
    @staticmethod
    async def load_conversation_history_list(
        db: AsyncIOMotorDatabase,
        conversation_id: Optional[str],
        user_id: Optional[str],
        limit: int = 5
    ) -> list:
        """
        載入對話歷史為列表格式
        
        用於需要結構化歷史數據的場景(如意圖分類)
        
        Returns:
            list: [{"role": "user", "content": "..."}, ...]
        """
        if not conversation_id or not user_id or db is None:
            return []
        
        try:
            from app.crud import crud_conversations
            
            conversation_uuid = UUID(conversation_id)
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            
            recent_messages = await crud_conversations.get_recent_messages(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid,
                limit=limit
            )
            
            if not recent_messages:
                return []
            
            # 轉換為字典列表
            return [
                {
                    "role": msg.role,
                    "content": msg.content
                }
                for msg in recent_messages
            ]
            
        except Exception as e:
            logger.warning(f"載入對話歷史列表失敗: {e}")
            return []


# 創建全局實例（供所有handler使用）
unified_context_helper = UnifiedContextHelper()

