"""
對話記錄輔助工具

為各個意圖處理器提供統一的對話保存功能
"""
import logging
from typing import Optional
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class ConversationHelper:
    """對話記錄輔助類"""
    
    @staticmethod
    async def save_qa_to_conversation(
        db: AsyncIOMotorDatabase,
        conversation_id: Optional[str],
        user_id: Optional[str],
        question: str,
        answer: str,
        tokens_used: int = 0,
        source_documents: Optional[list] = None
    ) -> bool:
        """
        保存問答對到對話中（自動使用統一上下文管理器）
        
        Args:
            db: 數據庫連接
            conversation_id: 對話ID
            user_id: 用戶ID
            question: 用戶問題
            answer: AI回答
            tokens_used: 使用的Token數
            source_documents: 參考文檔列表
            
        Returns:
            bool: 是否保存成功
        """
        if not conversation_id or not user_id:
            logger.debug("沒有對話ID或用戶ID,跳過對話保存")
            return False
        
        # 診斷 db 參數類型錯誤
        if not hasattr(db, "conversations"):
            logger.error(f"❌ save_qa_to_conversation 收到錯誤的 db 對象: type={type(db)}, value={db}")
            return False
        
        # 嘗試使用統一上下文管理器（推薦方式）
        try:
            from app.services.context.conversation_context_manager import ConversationContextManager
            
            context_manager = ConversationContextManager(
                db=db,
                conversation_id=conversation_id,
                user_id=str(user_id)
            )
            
            # 使用統一管理器保存（會自動更新文檔池）
            success = await context_manager.add_qa_pair(
                question=question,
                answer=answer,
                source_documents=source_documents,
                tokens_used=tokens_used
            )
            
            if success:
                logger.info(f"✅ 統一管理器保存成功: conversation_id={conversation_id}")
                return True
            else:
                logger.warning("⚠️ 統一管理器保存失敗，回退到舊方式")
                
        except Exception as e:
            logger.warning(f"⚠️ 統一管理器失敗，回退到舊方式: {e}")
        
        # 回退到舊方式（向後兼容）
        try:
            from uuid import UUID
            from app.crud import crud_conversations
            from app.services.cache import unified_cache, CacheNamespace

            logger.info(f"開始保存對話（舊方式）: conversation_id={conversation_id}, user_id={user_id}")
            
            conversation_uuid = UUID(conversation_id)
            # 處理 user_id 可能是 UUID 或字符串
            if isinstance(user_id, UUID):
                user_uuid = user_id
            else:
                user_uuid = UUID(str(user_id)) if user_id else None
            
            if not user_uuid:
                logger.error("user_uuid 為 None，無法保存對話")
                return False
            
            logger.info(f"UUID 轉換成功: conversation_uuid={conversation_uuid}, user_uuid={user_uuid}")
            
            # 添加用戶問題
            logger.info(f"準備添加用戶問題: {question[:50]}...")
            result1 = await crud_conversations.add_message_to_conversation(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid,
                role="user",
                content=question,
                tokens_used=None
            )
            logger.info(f"用戶問題添加結果: {result1}")
            
            # 添加 AI 回答
            logger.info(f"準備添加 AI 回答: {answer[:50]}...")
            result2 = await crud_conversations.add_message_to_conversation(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid,
                role="assistant",
                content=answer,
                tokens_used=tokens_used
            )
            logger.info(f"AI 回答添加結果: {result2}")
            
            # 更新對話的文檔緩存(如果有參考文檔)
            if source_documents and len(source_documents) > 0:
                logger.info(f"準備更新文檔緩存: {len(source_documents)} 個文檔")
                cache_result = await crud_conversations.update_cached_documents(
                    db=db,
                    conversation_id=conversation_uuid,
                    user_id=user_uuid,
                    document_ids=source_documents,
                    document_data=None
                )
                logger.info(f"文檔緩存更新結果: {cache_result}")
            else:
                logger.debug("沒有參考文檔,跳過文檔緩存更新")
            
            # 使緩存失效，下次會從 MongoDB 重新載入
            try:
                cache_key = f"{user_uuid}:{conversation_uuid}"
                await unified_cache.delete(
                    key=cache_key,
                    namespace=CacheNamespace.CONVERSATION
                )
                logger.debug(f"已清除對話緩存: {cache_key}")
            except Exception as cache_e:
                logger.warning(f"清除對話緩存失敗 (不影響主流程): {cache_e}")
            
            logger.info(f"✅ 成功保存問答對到對話 {conversation_id}")
            return True
            
        except Exception as e:
            import traceback
            logger.error(f"❌ 保存對話失敗: {e}")
            logger.error(f"錯誤詳情: {traceback.format_exc()}")
            return False


# 創建全局實例
conversation_helper = ConversationHelper()
