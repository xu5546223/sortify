import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from app.core.resource_helpers import get_owned_resource_or_404
from app.core.logging_decorators import log_api_operation

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== 依賴函數 ==========

async def get_owned_conversation(
    conversation_id: UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    獲取對話並驗證所有權
    
    這個依賴函數會：
    1. 從數據庫獲取對話
    2. 如果不存在，拋出 404 錯誤
    3. 檢查當前用戶是否擁有該對話
    4. 如果無權訪問，拋出 403 錯誤並記錄日誌
    
    使用 resource_helpers 簡化權限檢查和日誌記錄。
    注意：Conversation 使用 user_id 而不是 owner_id。
    """
    return await get_owned_resource_or_404(
        getter_func=crud_conversations.get_conversation,
        db=db,
        resource_id=conversation_id,
        current_user=current_user,
        resource_type="Conversation",
        owner_field="user_id",  # Conversation 使用 user_id
        log_unauthorized=True
    )


# ========== API 端點 ==========


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
@log_api_operation(operation_name="列出對話", log_success=True, success_level=LogLevel.DEBUG)
async def list_conversations(
    request: Request,
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
    
    conversations = [
        Conversation(
            id=conv.id,
            title=conv.title,
            user_id=conv.user_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=conv.message_count,
            total_tokens=conv.total_tokens,
            cached_documents=getattr(conv, 'cached_documents', [])
        )
        for conv in conversations_db
    ]
    
    return ConversationListResponse(
        conversations=conversations,
        total=total
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessages)
@log_api_operation(operation_name="獲取對話詳情", log_success=True, success_level=LogLevel.DEBUG)
async def get_conversation(
    request: Request,
    conversation: ConversationWithMessages = Depends(get_owned_conversation),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    獲取對話詳情（包含所有消息）
    
    - **conversation_id**: 對話ID
    
    權限檢查由 get_owned_conversation 依賴函數自動處理。
    """
    # 嘗試從緩存獲取（可選優化）
    conversation_id = conversation.id
    cached_conversation = await conversation_cache_service.get_conversation(
        user_id=current_user.id,
        conversation_id=conversation_id
    )
    
    if cached_conversation:
        # 更新緩存 TTL
        await conversation_cache_service.update_conversation_ttl(
            user_id=current_user.id,
            conversation_id=conversation_id
        )
        return cached_conversation
    
    # 保存到緩存
    await conversation_cache_service.set_conversation(
        user_id=current_user.id,
        conversation=conversation
    )
    
    return conversation


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
@log_api_operation(operation_name="獲取對話消息", log_success=True, success_level=LogLevel.DEBUG)
async def get_conversation_messages(
    request: Request,
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
    messages = await crud_conversations.get_recent_messages(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        limit=limit
    )
    
    return messages if messages else []


@router.put("/conversations/{conversation_id}", response_model=Conversation)
@log_api_operation(operation_name="更新對話", log_success=True)
async def update_conversation(
    request: Request,
    conversation_id: UUID,
    update_data: ConversationUpdate,
    existing_conversation: Conversation = Depends(get_owned_conversation),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    更新對話信息（例如標題）
    
    - **conversation_id**: 對話ID
    - **title**: 新的對話標題
    
    權限檢查由 get_owned_conversation 依賴函數自動處理。
    """
    # 執行更新
    updated_conversation = await crud_conversations.update_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        update_data=update_data
    )
    
    if not updated_conversation:
        raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
    
    # 使緩存失效
    await conversation_cache_service.invalidate_conversation(
        user_id=current_user.id,
        conversation_id=conversation_id
    )
    
    return Conversation(
        id=updated_conversation.id,
        title=updated_conversation.title,
        user_id=updated_conversation.user_id,
        created_at=updated_conversation.created_at,
        updated_at=updated_conversation.updated_at,
        message_count=updated_conversation.message_count,
        total_tokens=updated_conversation.total_tokens
    )


@router.delete("/conversations/{conversation_id}")
@log_api_operation(operation_name="刪除對話", log_success=True)
async def delete_conversation(
    request: Request,
    conversation_id: UUID,
    existing_conversation: Conversation = Depends(get_owned_conversation),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    刪除對話
    
    - **conversation_id**: 對話ID
    
    權限檢查由 get_owned_conversation 依賴函數自動處理。
    """
    # 執行刪除
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
    
    return {"success": True, "message": "對話已刪除"}

