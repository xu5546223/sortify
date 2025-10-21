import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_db
from app.models.user_models import User
from app.core.security import get_current_active_user
from app.models.conversation_models import (
    Conversation,
    ConversationCreate,
    ConversationUpdate,
    ConversationWithMessages,
    ConversationListResponse,
    ConversationMessage
)
from app.crud import crud_conversations
from app.services.cache.conversation_cache_service import conversation_cache_service
from app.core.logging_utils import log_event, LogLevel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/conversations", response_model=Conversation)
async def create_conversation(
    request: ConversationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    創建新對話
    
    - **first_question**: 第一個問題，將作為對話標題
    """
    try:
        conversation = await crud_conversations.create_conversation(
            db=db,
            user_id=current_user.id,
            first_question=request.first_question
        )
        
        # 緩存新創建的對話
        await conversation_cache_service.set_conversation(
            user_id=current_user.id,
            conversation=conversation
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 創建了新對話",
            source="api.conversations.create",
            user_id=str(current_user.id),
            details={"conversation_id": str(conversation.id), "title": conversation.title}
        )
        
        return Conversation(
            id=conversation.id,
            title=conversation.title,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            total_tokens=conversation.total_tokens
        )
    except Exception as e:
        logger.error(f"創建對話失敗: {e}")
        raise HTTPException(status_code=500, detail=f"創建對話失敗: {str(e)}")


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = Query(0, ge=0, description="跳過的記錄數"),
    limit: int = Query(50, ge=1, le=100, description="返回的最大記錄數"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取用戶的對話列表（按更新時間降序）
    
    - **skip**: 跳過的記錄數（用於分頁）
    - **limit**: 返回的最大記錄數
    """
    try:
        conversations_db = await crud_conversations.list_user_conversations(
            db=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        
        total = await crud_conversations.get_conversation_count(
            db=db,
            user_id=current_user.id
        )
        
        conversations = []
        for conv in conversations_db:
            # 調試：檢查每個對話的 cached_documents
            cached_docs = getattr(conv, 'cached_documents', [])
            logger.info(f"對話 {conv.id}: title={conv.title}, cached_documents={len(cached_docs)} 個")
            
            conversations.append(
                Conversation(
                    id=conv.id,
                    title=conv.title,
                    user_id=conv.user_id,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    message_count=conv.message_count,
                    total_tokens=conv.total_tokens,
                    cached_documents=cached_docs
                )
            )
        
        response = ConversationListResponse(
            conversations=conversations,
            total=total
        )
        
        # 調試：檢查響應中的 cached_documents
        logger.info(f"準備返回 {len(conversations)} 個對話")
        for i, conv in enumerate(response.conversations):
            logger.info(f"  [{i}] {conv.id}: cached_documents={conv.cached_documents}")
        
        return response
    except Exception as e:
        logger.error(f"獲取對話列表失敗: {e}")
        raise HTTPException(status_code=500, detail=f"獲取對話列表失敗: {str(e)}")


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取對話詳情（包含所有消息）
    
    - **conversation_id**: 對話ID
    """
    try:
        # 先嘗試從緩存獲取
        conversation = await conversation_cache_service.get_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id
        )
        
        # 如果緩存未命中，從數據庫獲取
        if not conversation:
            conversation = await crud_conversations.get_conversation(
                db=db,
                conversation_id=conversation_id,
                user_id=current_user.id
            )
            
            if not conversation:
                raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
            
            # 將對話保存到緩存
            await conversation_cache_service.set_conversation(
                user_id=current_user.id,
                conversation=conversation
            )
        
        # 更新緩存 TTL
        await conversation_cache_service.update_conversation_ttl(
            user_id=current_user.id,
            conversation_id=conversation_id
        )
        
        # 調試：檢查對話數據
        cached_docs = getattr(conversation, 'cached_documents', [])
        logger.info(f"返回對話 {conversation_id}: messages={len(conversation.messages)}, cached_documents={len(cached_docs)} 個")
        
        return ConversationWithMessages(
            id=conversation.id,
            title=conversation.title,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            total_tokens=conversation.total_tokens,
            cached_documents=cached_docs,
            messages=conversation.messages
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取對話詳情失敗: {e}")
        raise HTTPException(status_code=500, detail=f"獲取對話詳情失敗: {str(e)}")


@router.delete("/conversations/{conversation_id}/cached-documents/{document_id}", status_code=204)
async def remove_cached_document(
    conversation_id: UUID,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    從對話緩存中移除指定的文檔
    
    - **conversation_id**: 對話ID
    - **document_id**: 要移除的文檔ID
    """
    try:
        success = await crud_conversations.remove_cached_document(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            document_id=document_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="對話不存在或文檔未在緩存中")
        
        # 使 Redis 緩存失效
        from app.services.cache.conversation_cache_service import conversation_cache_service
        await conversation_cache_service.invalidate_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id
        )
        
        logger.info(f"Successfully removed document {document_id} from conversation {conversation_id}")
        return {"message": "文檔已從緩存中移除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移除緩存文檔失敗: {e}")
        raise HTTPException(status_code=500, detail=f"移除緩存文檔失敗: {str(e)}")


@router.get("/conversations/{conversation_id}/messages", response_model=List[ConversationMessage])
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="返回的最大消息數"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取對話的消息列表
    
    - **conversation_id**: 對話ID
    - **limit**: 返回的最大消息數（最近的 N 條）
    """
    try:
        messages = await crud_conversations.get_recent_messages(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            limit=limit
        )
        
        return messages
    except Exception as e:
        logger.error(f"獲取對話消息失敗: {e}")
        raise HTTPException(status_code=500, detail=f"獲取對話消息失敗: {str(e)}")


@router.put("/conversations/{conversation_id}", response_model=Conversation)
async def update_conversation(
    conversation_id: UUID,
    update_data: ConversationUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    更新對話信息（例如標題）
    
    - **conversation_id**: 對話ID
    - **title**: 新的對話標題
    """
    try:
        conversation = await crud_conversations.update_conversation(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            update_data=update_data
        )
        
        if not conversation:
            raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
        
        # 使緩存失效
        await conversation_cache_service.invalidate_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 更新了對話",
            source="api.conversations.update",
            user_id=str(current_user.id),
            details={"conversation_id": str(conversation_id)}
        )
        
        return Conversation(
            id=conversation.id,
            title=conversation.title,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            total_tokens=conversation.total_tokens
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新對話失敗: {e}")
        raise HTTPException(status_code=500, detail=f"更新對話失敗: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    刪除對話
    
    - **conversation_id**: 對話ID
    """
    try:
        success = await crud_conversations.delete_conversation(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
        
        # 刪除緩存
        await conversation_cache_service.invalidate_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 刪除了對話",
            source="api.conversations.delete",
            user_id=str(current_user.id),
            details={"conversation_id": str(conversation_id)}
        )
        
        return {"success": True, "message": "對話已刪除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除對話失敗: {e}")
        raise HTTPException(status_code=500, detail=f"刪除對話失敗: {str(e)}")

