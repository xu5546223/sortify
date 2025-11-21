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
from app.services.cache import unified_cache, CacheNamespace
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
) -> ConversationWithMessages:
    """
    獲取對話並驗證所有權，返回包含消息的完整對話
    
    這個依賴函數會：
    1. 從數據庫獲取對話（包含消息）
    2. 如果不存在，拋出 404 錯誤
    3. 檢查當前用戶是否擁有該對話
    4. 如果無權訪問，拋出 403 錯誤並記錄日誌
    
    注意：Conversation 使用 user_id 而不是 owner_id。
    """
    # 直接從數據庫讀取完整數據（包含消息和 cached_document_data）
    conversation_data = await db.conversations.find_one({
        "_id": conversation_id,
        "user_id": current_user.id
    })
    
    if not conversation_data:
        raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
    
    # 轉換 ID
    conversation_data['id'] = conversation_data.pop('_id')
    
    # 構建 ConversationInDB 然後轉換為 ConversationWithMessages
    from app.models.conversation_models import ConversationInDB
    conv_db = ConversationInDB(**conversation_data)
    
    return ConversationWithMessages(**conv_db.model_dump())


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
        conversation_in_db = await crud_conversations.create_conversation(
            db=db,
            user_id=current_user.id,
            first_question=request.first_question
        )
        
        # 緩存對話（使用統一緩存）
        try:
            await unified_cache.set(
                key=f"{current_user.id}:{conversation_in_db.id}",
                value=conversation_in_db.model_dump(mode='json'),
                namespace=CacheNamespace.CONVERSATION,
                ttl=3600  # 1小時
            )
        except Exception as cache_error:
            logger.warning(f"緩存對話失敗: {cache_error}")
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 創建了新對話",
            source="api.conversations.create",
            user_id=str(current_user.id),
            details={"conversation_id": str(conversation_in_db.id), "title": conversation_in_db.title}
        )
        
        return Conversation(
            id=conversation_in_db.id,
            title=conversation_in_db.title,
            user_id=conversation_in_db.user_id,
            created_at=conversation_in_db.created_at,
            updated_at=conversation_in_db.updated_at,
            message_count=conversation_in_db.message_count,
            total_tokens=conversation_in_db.total_tokens,
            cached_documents=getattr(conversation_in_db, 'cached_documents', []),
            is_pinned=getattr(conversation_in_db, 'is_pinned', False)
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
            cached_documents=getattr(conv, 'cached_documents', []),
            is_pinned=getattr(conv, 'is_pinned', False)
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
) -> ConversationWithMessages:
    """
    獲取單個對話的詳細信息
    
    包含完整的消息歷史記錄。
    如果 cached_document_data 不存在或包含舊數據，自動修復。
    """
    # 檢查是否需要修復文檔池
    needs_repair = conversation.cached_documents and (
        not conversation.cached_document_data or 
        any(doc_data.get('filename') == 'unknown' 
            for doc_data in (conversation.cached_document_data or {}).values() 
            if isinstance(doc_data, dict))
    )
    
    logger.debug(f"文檔池檢查: cached_documents={len(conversation.cached_documents or [])}, "
                f"cached_document_data={'存在' if conversation.cached_document_data else '不存在'}, "
                f"needs_repair={needs_repair}")
    
    if needs_repair:
        logger.info(f"檢測到對話 {conversation.id} 的文檔池需要修復，自動觸發修復...")
        
        try:
            from app.services.context.conversation_context_manager import ConversationContextManager
            
            # 創建臨時 context_manager 來修復文檔池
            ctx_mgr = ConversationContextManager(
                db=db,
                conversation_id=str(conversation.id),
                user_id=str(current_user.id)
            )
            
            # 強制重新載入並修復文檔池
            await ctx_mgr._load_document_pool()
            
            # 重新從數據庫讀取對話數據（已包含修復後的 cached_document_data）
            conversation_data = await db.conversations.find_one({
                "_id": conversation.id,
                "user_id": current_user.id
            })
            
            if conversation_data:
                # 重新構建 conversation 對象（包含修復後的 cached_document_data）
                conversation_data['id'] = conversation_data.pop('_id')
                from app.models.conversation_models import ConversationInDB
                updated_conv_db = ConversationInDB(**conversation_data)
                
                # 構建新的 ConversationWithMessages 對象
                conversation = ConversationWithMessages(
                    **updated_conv_db.model_dump(),
                    messages=conversation.messages  # 保留原來的消息
                )
                
                doc_count = len(conversation.cached_document_data or {})
                logger.info(f"✅ 對話 {conversation.id} 的文檔池已自動修復，包含 {doc_count} 個文檔")
                
                # 驗證修復結果
                if doc_count > 0:
                    logger.debug(f"修復後的文檔 ID: {list((conversation.cached_document_data or {}).keys())[:3]}...")
                else:
                    logger.warning(f"⚠️ 修復後文檔池仍為空，可能數據庫中沒有文檔數據")
        except Exception as e:
            logger.error(f"⚠️ 自動修復文檔池失敗: {e}", exc_info=True)
    
    # conversation 已經通過依賴函數獲取並驗證權限
    # 直接緩存並返回
    try:
        cache_key = f"{current_user.id}:{conversation.id}"
        await unified_cache.set(
            key=cache_key,
            value=conversation.model_dump(mode='json'),
            namespace=CacheNamespace.CONVERSATION,
            ttl=3600
        )
        logger.debug(f"💾 對話已緩存: {conversation.id}")
    except Exception as cache_error:
        logger.warning(f"緩存對話失敗: {cache_error}")
    
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
        
        # 使緩存失效
        try:
            await unified_cache.delete(
                key=f"{current_user.id}:{conversation_id}",
                namespace=CacheNamespace.CONVERSATION
            )
        except Exception as e:
            logger.warning(f"清理緩存失敗: {e}")
        
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
    try:
        await unified_cache.delete(
            key=f"{current_user.id}:{conversation_id}",
            namespace=CacheNamespace.CONVERSATION
        )
    except Exception as e:
        logger.warning(f"清理緩存失敗: {e}")
    
    return Conversation(
        id=updated_conversation.id,
        title=updated_conversation.title,
        user_id=updated_conversation.user_id,
        created_at=updated_conversation.created_at,
        updated_at=updated_conversation.updated_at,
        message_count=updated_conversation.message_count,
        total_tokens=updated_conversation.total_tokens,
        cached_documents=getattr(updated_conversation, 'cached_documents', []),
        is_pinned=getattr(updated_conversation, 'is_pinned', False)
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
    try:
        await unified_cache.delete(
            key=f"{current_user.id}:{conversation_id}",
            namespace=CacheNamespace.CONVERSATION
        )
    except Exception as e:
        logger.warning(f"清理緩存失敗: {e}")
    
    return {"success": True, "message": "對話已刪除"}


@router.post("/conversations/{conversation_id}/pin", response_model=Conversation)
@log_api_operation(operation_name="置頂對話", log_success=True)
async def pin_conversation(
    request: Request,
    conversation_id: UUID,
    existing_conversation: Conversation = Depends(get_owned_conversation),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    置頂對話
    
    - **conversation_id**: 對話ID
    
    權限檢查由 get_owned_conversation 依賴函數自動處理。
    """
    # 執行置頂
    updated_conversation = await crud_conversations.pin_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id
    )
    
    if not updated_conversation:
        raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
    
    # 使緩存失效
    try:
        await unified_cache.delete(
            key=f"{current_user.id}:{conversation_id}",
            namespace=CacheNamespace.CONVERSATION
        )
    except Exception as e:
        logger.warning(f"清理緩存失敗: {e}")
    
    return Conversation(
        id=updated_conversation.id,
        title=updated_conversation.title,
        user_id=updated_conversation.user_id,
        created_at=updated_conversation.created_at,
        updated_at=updated_conversation.updated_at,
        message_count=updated_conversation.message_count,
        total_tokens=updated_conversation.total_tokens,
        cached_documents=getattr(updated_conversation, 'cached_documents', []),
        is_pinned=getattr(updated_conversation, 'is_pinned', False)
    )


@router.post("/conversations/{conversation_id}/unpin", response_model=Conversation)
@log_api_operation(operation_name="取消置頂對話", log_success=True)
async def unpin_conversation(
    request: Request,
    conversation_id: UUID,
    existing_conversation: Conversation = Depends(get_owned_conversation),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    取消置頂對話
    
    - **conversation_id**: 對話ID
    
    權限檢查由 get_owned_conversation 依賴函數自動處理。
    """
    # 執行取消置頂
    updated_conversation = await crud_conversations.unpin_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id
    )
    
    if not updated_conversation:
        raise HTTPException(status_code=404, detail="對話不存在或無權訪問")
    
    # 使緩存失效
    try:
        await unified_cache.delete(
            key=f"{current_user.id}:{conversation_id}",
            namespace=CacheNamespace.CONVERSATION
        )
    except Exception as e:
        logger.warning(f"清理緩存失敗: {e}")
    
    return Conversation(
        id=updated_conversation.id,
        title=updated_conversation.title,
        user_id=updated_conversation.user_id,
        created_at=updated_conversation.created_at,
        updated_at=updated_conversation.updated_at,
        message_count=updated_conversation.message_count,
        total_tokens=updated_conversation.total_tokens,
        cached_documents=getattr(updated_conversation, 'cached_documents', []),
        is_pinned=getattr(updated_conversation, 'is_pinned', False)
    )

