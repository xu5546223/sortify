from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from app.models.conversation_models import (
    ConversationInDB, 
    ConversationCreate, 
    ConversationMessage,
    ConversationUpdate
)

logger = logging.getLogger(__name__)

async def create_conversation(
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    first_question: str
) -> ConversationInDB:
    """
    創建新對話
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        first_question: 第一個問題，將作為對話標題
        
    Returns:
        創建的對話對象
    """
    conversation = ConversationInDB(
        title=first_question[:100],  # 限制標題長度
        user_id=user_id,
        messages=[],
        message_count=0,
        total_tokens=0
    )
    
    conversation_dict = conversation.model_dump()
    # 保持 UUID 類型，不轉換為字符串
    conversation_dict['_id'] = conversation_dict.pop('id')
    
    await db.conversations.insert_one(conversation_dict)
    
    logger.info(f"Created conversation {conversation.id} for user {user_id}")
    return conversation


async def get_conversation(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: Optional[UUID] = None
) -> Optional[ConversationInDB]:
    """
    獲取單個對話
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID（可選，用於權限驗證）
        
    Returns:
        對話對象，如果不存在或權限不足則返回 None
        
    Note:
        如果提供 user_id，將檢查對話是否屬於該用戶
        如果不提供 user_id，則不進行權限檢查（向後兼容）
    """
    query = {"_id": conversation_id}
    if user_id is not None:
        query["user_id"] = user_id
    
    conversation_data = await db.conversations.find_one(query)
    
    if not conversation_data:
        if user_id:
            logger.warning(f"Conversation {conversation_id} not found or access denied for user {user_id}")
        else:
            logger.warning(f"Conversation {conversation_id} not found")
        return None
    
    conversation_data['id'] = conversation_data.pop('_id')
    return ConversationInDB(**conversation_data)


async def list_user_conversations(
    db: AsyncIOMotorDatabase,
    user_id: UUID,
    skip: int = 0,
    limit: int = 50
) -> List[ConversationInDB]:
    """
    列出用戶的所有對話（按更新時間降序）
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        skip: 跳過的記錄數
        limit: 返回的最大記錄數
        
    Returns:
        對話列表
    """
    cursor = db.conversations.find(
        {"user_id": user_id}
    ).sort("updated_at", -1).skip(skip).limit(limit)
    
    conversations = []
    async for conversation_data in cursor:
        conversation_data['id'] = conversation_data.pop('_id')
        conversations.append(ConversationInDB(**conversation_data))
    
    logger.info(f"Listed {len(conversations)} conversations for user {user_id}")
    return conversations


# 從統一配置載入歷史對話長度限制
from app.models.context_config import context_config
MAX_MESSAGES_PER_CONVERSATION = context_config.MAX_MESSAGES_PER_CONVERSATION


async def add_message_to_conversation(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID,
    role: str,
    content: str,
    tokens_used: Optional[int] = None
) -> bool:
    """
    添加消息到對話（帶長度控制）
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID（用於權限驗證）
        role: 消息角色（'user' 或 'assistant'）
        content: 消息內容
        tokens_used: 使用的 token 數量
        
    Returns:
        是否成功添加
        
    Note:
        當消息數超過 MAX_MESSAGES_PER_CONVERSATION 時，
        會自動移除最舊的消息以控制對話長度
    """
    message = ConversationMessage(
        role=role,
        content=content,
        timestamp=datetime.now(UTC),
        tokens_used=tokens_used
    )
    
    message_dict = message.model_dump()
    
    # 更新對話：添加消息、更新計數、更新時間
    update_data = {
        "$push": {"messages": message_dict},
        "$inc": {
            "message_count": 1,
            "total_tokens": tokens_used if tokens_used else 0
        },
        "$set": {"updated_at": datetime.now(UTC)}
    }
    
    result = await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        update_data
    )
    
    if result.modified_count > 0:
        logger.info(f"✅ Added {role} message to conversation {conversation_id}")
        
        # 檢查並清理超出長度限制的舊消息
        await _trim_conversation_messages(db, conversation_id, user_id)
        
        return True
    else:
        # 檢查對話是否存在
        conversation_exists = await db.conversations.find_one({"_id": conversation_id})
        if not conversation_exists:
            logger.error(f"❌ Conversation {conversation_id} does not exist in database")
        elif conversation_exists.get("user_id") != user_id:
            logger.error(f"❌ User ID mismatch: conversation user_id={conversation_exists.get('user_id')}, provided user_id={user_id}")
        else:
            logger.error(f"❌ Unknown error: conversation exists but update failed")
        
        logger.warning(f"Failed to add message to conversation {conversation_id}: matched={result.matched_count}, modified={result.modified_count}")
        return False


async def _trim_conversation_messages(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID
) -> None:
    """
    裁剪對話消息，保持在長度限制內
    
    當消息數超過 MAX_MESSAGES_PER_CONVERSATION 時，
    移除最舊的消息直到符合限制
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID
    """
    # 獲取當前消息數量
    conversation = await db.conversations.find_one(
        {"_id": conversation_id, "user_id": user_id},
        {"message_count": 1}
    )
    
    if not conversation:
        return
    
    message_count = conversation.get("message_count", 0)
    
    # 如果未超過限制，不需要裁剪
    if message_count <= MAX_MESSAGES_PER_CONVERSATION:
        return
    
    # 計算需要移除的消息數量
    messages_to_remove = message_count - MAX_MESSAGES_PER_CONVERSATION
    
    logger.info(
        f"🗑️ 對話 {conversation_id} 消息數 ({message_count}) 超過限制 ({MAX_MESSAGES_PER_CONVERSATION})，"
        f"移除最舊的 {messages_to_remove} 條消息"
    )
    
    # 使用 $pop 移除最舊的消息（-1 表示移除第一個元素）
    # 需要執行多次以移除多條消息
    for _ in range(messages_to_remove):
        await db.conversations.update_one(
            {"_id": conversation_id, "user_id": user_id},
            {"$pop": {"messages": -1}}  # -1 移除第一條（最舊的）
        )
    
    # 更新 message_count（因為 $pop 不會自動更新計數）
    await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"message_count": MAX_MESSAGES_PER_CONVERSATION}}
    )
    
    logger.info(f"✅ 已裁剪對話 {conversation_id}，保留最近 {MAX_MESSAGES_PER_CONVERSATION} 條消息")


async def get_recent_messages(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID,
    limit: int = 5
) -> List[ConversationMessage]:
    """
    獲取對話的最近 N 條消息（用於 AI 上下文）
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID（用於權限驗證）
        limit: 返回的最大消息數
        
    Returns:
        消息列表
    """
    conversation_data = await db.conversations.find_one(
        {"_id": conversation_id, "user_id": user_id},
        {"messages": {"$slice": -limit}}  # 獲取最後 N 條消息
    )
    
    if not conversation_data or 'messages' not in conversation_data:
        logger.warning(f"No messages found for conversation {conversation_id}")
        return []
    
    messages = [ConversationMessage(**msg) for msg in conversation_data['messages']]
    logger.info(f"Retrieved {len(messages)} recent messages from conversation {conversation_id}")
    return messages


async def delete_conversation(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID
) -> bool:
    """
    刪除對話
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID（用於權限驗證）
        
    Returns:
        是否成功刪除
    """
    result = await db.conversations.delete_one({
        "_id": conversation_id,
        "user_id": user_id
    })
    
    if result.deleted_count > 0:
        logger.info(f"Deleted conversation {conversation_id} for user {user_id}")
        return True
    else:
        logger.warning(f"Failed to delete conversation {conversation_id}")
        return False


async def update_conversation(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID,
    update_data: ConversationUpdate
) -> Optional[ConversationInDB]:
    """
    更新對話信息
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID（用於權限驗證）
        update_data: 更新數據
        
    Returns:
        更新後的對話對象，如果失敗則返回 None
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
        return await get_conversation(db, conversation_id)
    
    update_dict['updated_at'] = datetime.now(UTC)
    
    result = await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": update_dict}
    )
    
    if result.modified_count > 0:
        logger.info(f"Updated conversation {conversation_id}")
        return await get_conversation(db, conversation_id)
    else:
        logger.warning(f"Failed to update conversation {conversation_id}")
        return None


async def get_conversation_count(
    db: AsyncIOMotorDatabase,
    user_id: UUID
) -> int:
    """
    獲取用戶的對話總數
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        
    Returns:
        對話總數
    """
    count = await db.conversations.count_documents({"user_id": user_id})
    return count


async def update_cached_documents(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID,
    document_ids: List[str],
    document_data: Optional[dict] = None
) -> bool:
    """
    更新對話的文檔緩存
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID
        document_ids: 新的文檔ID列表
        document_data: 文檔詳細數據（可選）
        
    Returns:
        是否成功更新
    """
    update_data = {
        "$addToSet": {"cached_documents": {"$each": document_ids}},
        "$set": {"updated_at": datetime.now(UTC)}
    }
    
    if document_data:
        update_data["$set"]["cached_document_data"] = document_data
    
    result = await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        update_data
    )
    
    if result.modified_count > 0 or result.matched_count > 0:
        logger.info(f"✅ Updated cached documents for conversation {conversation_id}: {len(document_ids)} documents (matched={result.matched_count}, modified={result.modified_count})")
        return True
    else:
        conversation_exists = await db.conversations.find_one({"_id": conversation_id})
        if not conversation_exists:
            logger.error(f"❌ Conversation {conversation_id} does not exist for caching documents")
        elif conversation_exists.get("user_id") != user_id:
            logger.error(f"❌ User ID mismatch when caching: conversation user_id={conversation_exists.get('user_id')}, provided user_id={user_id}")
        
        logger.warning(f"Failed to update cached documents for conversation {conversation_id}: matched={result.matched_count}, modified={result.modified_count}")
        return False


async def get_cached_documents(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID
) -> tuple[List[str], Optional[dict]]:
    """
    獲取對話的緩存文檔
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID
        
    Returns:
        (文檔ID列表, 文檔數據字典)
    """
    conversation_data = await db.conversations.find_one(
        {"_id": conversation_id, "user_id": user_id},
        {"cached_documents": 1, "cached_document_data": 1}
    )
    
    if not conversation_data:
        return [], None
    
    cached_docs = conversation_data.get('cached_documents', [])
    cached_data = conversation_data.get('cached_document_data')
    
    logger.info(f"Retrieved {len(cached_docs)} cached documents for conversation {conversation_id}")
    return cached_docs, cached_data


async def remove_cached_document(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID,
    document_id: str
) -> bool:
    """
    從對話緩存中移除指定的文檔
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID
        document_id: 要移除的文檔ID
        
    Returns:
        是否成功移除
    """
    result = await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {
            "$pull": {"cached_documents": document_id},
            "$unset": {f"cached_document_data.{document_id}": ""},  # 同時移除文檔數據
            "$set": {"updated_at": datetime.now(UTC)}
        }
    )
    
    if result.modified_count > 0 or result.matched_count > 0:
        logger.info(f"✅ Removed document {document_id} from conversation {conversation_id} cache")
        return True
    else:
        logger.warning(f"Failed to remove document {document_id} from conversation {conversation_id}")
        return False


async def pin_conversation(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID
) -> Optional[ConversationInDB]:
    """
    置頂對話
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID
        
    Returns:
        更新後的對話對象，如果失敗則返回 None
    """
    result = await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"is_pinned": True, "updated_at": datetime.now(UTC)}}
    )
    
    if result.modified_count > 0:
        logger.info(f"✅ Pinned conversation {conversation_id} for user {user_id}")
        return await get_conversation(db, conversation_id, user_id)
    else:
        logger.warning(f"Failed to pin conversation {conversation_id} for user {user_id}")
        return None


async def unpin_conversation(
    db: AsyncIOMotorDatabase,
    conversation_id: UUID,
    user_id: UUID
) -> Optional[ConversationInDB]:
    """
    取消置頂對話
    
    Args:
        db: 數據庫連接
        conversation_id: 對話ID
        user_id: 用戶ID
        
    Returns:
        更新後的對話對象，如果失敗則返回 None
    """
    result = await db.conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"is_pinned": False, "updated_at": datetime.now(UTC)}}
    )
    
    if result.modified_count > 0:
        logger.info(f"✅ Unpinned conversation {conversation_id} for user {user_id}")
        return await get_conversation(db, conversation_id, user_id)
    else:
        logger.warning(f"Failed to unpin conversation {conversation_id} for user {user_id}")
        return None

