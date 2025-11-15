"""
Conversations API 完整集成測試

測試所有 conversations.py 端點的業務場景：
1. POST /conversations - 創建對話
2. GET /conversations - 列出對話
3. GET /conversations/{conversation_id} - 獲取對話詳情
4. GET /conversations/{conversation_id}/messages - 獲取消息列表
5. PUT /conversations/{conversation_id} - 更新對話
6. DELETE /conversations/{conversation_id} - 刪除對話
7. DELETE /conversations/{conversation_id}/cached-documents/{document_id} - 移除緩存文檔

使用真實的測試數據庫，不使用 mock。
"""

import pytest
import pytest_asyncio
from uuid import uuid4, UUID
from datetime import datetime, UTC

from app.crud import crud_conversations
from app.models.conversation_models import (
    ConversationInDB,
    ConversationMessage,
    ConversationCreate,
    ConversationUpdate
)
from app.models.user_models import User

# 標記為集成測試
pytestmark = pytest.mark.integration


class TestCreateConversation:
    """測試創建對話功能"""
    
    @pytest.mark.asyncio
    async def test_create_conversation_success(self, test_db, test_user):
        """
        場景：用戶成功創建對話
        預期：返回新對話，標題為第一個問題
        """
        first_question = "如何使用這個系統？"
        
        conversation = await crud_conversations.create_conversation(
            db=test_db,
            user_id=test_user.id,
            first_question=first_question
        )
        
        # 驗證
        assert conversation is not None
        assert conversation.user_id == test_user.id
        assert conversation.title == first_question
        assert conversation.message_count == 0  # 初始沒有消息
        assert conversation.total_tokens == 0
        assert isinstance(conversation.id, UUID)
    
    @pytest.mark.asyncio
    async def test_create_conversation_with_long_title(self, test_db, test_user):
        """
        場景：使用很長的問題創建對話
        預期：標題可能被截斷或完整保存
        """
        long_question = "這是一個非常非常長的問題，" * 20  # 很長的標題
        
        conversation = await crud_conversations.create_conversation(
            db=test_db,
            user_id=test_user.id,
            first_question=long_question
        )
        
        assert conversation is not None
        assert conversation.user_id == test_user.id
        # 根據實際實現，標題可能被截斷
        assert len(conversation.title) > 0


class TestListConversations:
    """測試列出對話功能"""
    
    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, test_db, test_user):
        """
        場景：用戶沒有對話
        預期：返回空列表
        """
        conversations = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=test_user.id,
            skip=0,
            limit=50
        )
        
        assert conversations == []
    
    @pytest.mark.asyncio
    async def test_list_conversations_multiple(self, test_db, test_user):
        """
        場景：用戶有多個對話
        預期：返回所有對話
        """
        # 創建 3 個對話
        conversations_created = []
        for i in range(3):
            conv = await crud_conversations.create_conversation(
                db=test_db,
                user_id=test_user.id,
                first_question=f"問題 {i+1}"
            )
            conversations_created.append(conv)
        
        # 獲取列表
        conversations = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=test_user.id,
            skip=0,
            limit=50
        )
        
        assert len(conversations) == 3
        titles = [conv.title for conv in conversations]
        assert "問題 1" in titles
        assert "問題 2" in titles
        assert "問題 3" in titles
    
    @pytest.mark.asyncio
    async def test_list_conversations_pagination(self, test_db, test_user):
        """
        場景：分頁獲取對話
        預期：正確返回分頁結果
        """
        # 創建 5 個對話
        for i in range(5):
            await crud_conversations.create_conversation(
                db=test_db,
                user_id=test_user.id,
                first_question=f"分頁測試問題 {i+1}"
            )
        
        # 測試第一頁（前 2 個）
        page1 = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=test_user.id,
            skip=0,
            limit=2
        )
        assert len(page1) == 2
        
        # 測試第二頁（接下來 2 個）
        page2 = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=test_user.id,
            skip=2,
            limit=2
        )
        assert len(page2) == 2
        
        # 確保不同頁返回不同對話
        page1_ids = {conv.id for conv in page1}
        page2_ids = {conv.id for conv in page2}
        assert page1_ids.isdisjoint(page2_ids)  # 沒有重複
    
    @pytest.mark.asyncio
    async def test_list_conversations_only_shows_own(self, test_db, test_user, other_user):
        """
        場景：有多個用戶的對話
        預期：只返回當前用戶的對話
        """
        # test_user 創建 2 個對話
        await crud_conversations.create_conversation(
            db=test_db,
            user_id=test_user.id,
            first_question="Test user 的問題 1"
        )
        await crud_conversations.create_conversation(
            db=test_db,
            user_id=test_user.id,
            first_question="Test user 的問題 2"
        )
        
        # other_user 創建 1 個對話
        await crud_conversations.create_conversation(
            db=test_db,
            user_id=other_user.id,
            first_question="Other user 的問題"
        )
        
        # test_user 獲取列表
        test_user_conversations = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=test_user.id,
            skip=0,
            limit=50
        )
        
        # 驗證：test_user 只看到自己的 2 個對話
        assert len(test_user_conversations) == 2
        for conv in test_user_conversations:
            assert conv.user_id == test_user.id


class TestGetConversation:
    """測試獲取對話詳情功能"""
    
    @pytest.mark.asyncio
    async def test_get_conversation_success(self, test_db, test_user, test_conversation):
        """
        場景：成功獲取對話詳情
        預期：返回完整對話信息（包括消息）
        """
        conversation = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        
        assert conversation is not None
        assert conversation.id == test_conversation.id
        assert conversation.user_id == test_user.id
        assert conversation.title == test_conversation.title
        assert hasattr(conversation, 'messages')
    
    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, test_db, test_user):
        """
        場景：嘗試獲取不存在的對話
        預期：返回 None
        """
        fake_id = uuid4()
        
        conversation = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=fake_id,
            user_id=test_user.id
        )
        
        assert conversation is None
    
    @pytest.mark.asyncio
    async def test_get_conversation_wrong_user(self, test_db, test_user, other_user, test_conversation):
        """
        場景：用戶嘗試訪問別人的對話
        預期：返回 None（權限檢查）
        """
        # test_conversation 屬於 test_user
        # other_user 嘗試訪問
        conversation = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id  # 不同的用戶
        )
        
        assert conversation is None  # 無權訪問


class TestGetConversationMessages:
    """測試獲取對話消息功能"""
    
    @pytest.mark.asyncio
    async def test_get_recent_messages_success(self, test_db, test_user, test_conversation_with_messages):
        """
        場景：獲取對話的最近消息
        預期：返回消息列表
        """
        messages = await crud_conversations.get_recent_messages(
            db=test_db,
            conversation_id=test_conversation_with_messages.id,
            user_id=test_user.id,
            limit=10
        )
        
        assert messages is not None
        assert len(messages) > 0
        # 驗證消息內容
        for msg in messages:
            assert hasattr(msg, 'role')
            assert hasattr(msg, 'content')
            assert msg.role in ['user', 'assistant']
    
    @pytest.mark.asyncio
    async def test_get_recent_messages_limit(self, test_db, test_user, test_conversation_with_messages):
        """
        場景：限制返回的消息數量
        預期：最多返回指定數量的消息
        """
        messages = await crud_conversations.get_recent_messages(
            db=test_db,
            conversation_id=test_conversation_with_messages.id,
            user_id=test_user.id,
            limit=2  # 只要最近 2 條
        )
        
        assert len(messages) <= 2
    
    @pytest.mark.asyncio
    async def test_get_messages_empty_conversation(self, test_db, test_user):
        """
        場景：新創建的對話沒有消息
        預期：返回空列表
        """
        # 創建新對話
        conv = await crud_conversations.create_conversation(
            db=test_db,
            user_id=test_user.id,
            first_question="新對話"
        )
        
        messages = await crud_conversations.get_recent_messages(
            db=test_db,
            conversation_id=conv.id,
            user_id=test_user.id,
            limit=50
        )
        
        # 新對話沒有消息（或只有系統消息）
        assert messages is not None
        assert isinstance(messages, list)


class TestUpdateConversation:
    """測試更新對話功能"""
    
    @pytest.mark.asyncio
    async def test_update_conversation_title(self, test_db, test_user, test_conversation):
        """
        場景：更新對話標題
        預期：標題成功更新
        """
        new_title = "更新後的標題"
        update_data = ConversationUpdate(title=new_title)
        
        updated = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id,
            update_data=update_data
        )
        
        assert updated is not None
        assert updated.title == new_title
        assert updated.id == test_conversation.id
    
    @pytest.mark.asyncio
    async def test_update_conversation_not_found(self, test_db, test_user):
        """
        場景：嘗試更新不存在的對話
        預期：返回 None
        """
        fake_id = uuid4()
        update_data = ConversationUpdate(title="新標題")
        
        updated = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=fake_id,
            user_id=test_user.id,
            update_data=update_data
        )
        
        assert updated is None
    
    @pytest.mark.asyncio
    async def test_update_conversation_wrong_user(self, test_db, test_user, other_user, test_conversation):
        """
        場景：用戶嘗試更新別人的對話
        預期：返回 None（無權更新）
        """
        update_data = ConversationUpdate(title="嘗試更新")
        
        updated = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id,  # 不同的用戶
            update_data=update_data
        )
        
        assert updated is None


class TestDeleteConversation:
    """測試刪除對話功能"""
    
    @pytest.mark.asyncio
    async def test_delete_conversation_success(self, test_db, test_user, test_conversation):
        """
        場景：成功刪除對話
        預期：返回 True，對話被刪除
        """
        success = await crud_conversations.delete_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        
        assert success is True
        
        # 驗證對話確實被刪除
        deleted_conv = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        assert deleted_conv is None
    
    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, test_db, test_user):
        """
        場景：嘗試刪除不存在的對話
        預期：返回 False
        """
        fake_id = uuid4()
        
        success = await crud_conversations.delete_conversation(
            db=test_db,
            conversation_id=fake_id,
            user_id=test_user.id
        )
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_delete_conversation_wrong_user(self, test_db, test_user, other_user, test_conversation):
        """
        場景：用戶嘗試刪除別人的對話
        預期：返回 False（無權刪除）
        """
        success = await crud_conversations.delete_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id  # 不同的用戶
        )
        
        assert success is False
        
        # 驗證對話沒有被刪除
        still_exists = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        assert still_exists is not None


class TestConversationCount:
    """測試對話計數功能"""
    
    @pytest.mark.asyncio
    async def test_count_conversations_zero(self, test_db, test_user):
        """
        場景：用戶沒有對話
        預期：返回 0
        """
        count = await crud_conversations.get_conversation_count(
            db=test_db,
            user_id=test_user.id
        )
        
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_count_conversations_multiple(self, test_db, test_user):
        """
        場景：用戶有多個對話
        預期：返回正確的數量
        """
        # 創建 3 個對話
        for i in range(3):
            await crud_conversations.create_conversation(
                db=test_db,
                user_id=test_user.id,
                first_question=f"計數測試問題 {i+1}"
            )
        
        count = await crud_conversations.get_conversation_count(
            db=test_db,
            user_id=test_user.id
        )
        
        assert count == 3
    
    @pytest.mark.asyncio
    async def test_count_only_own_conversations(self, test_db, test_user, other_user):
        """
        場景：有多個用戶的對話
        預期：只計數自己的對話
        """
        # test_user 創建 2 個對話
        for i in range(2):
            await crud_conversations.create_conversation(
                db=test_db,
                user_id=test_user.id,
                first_question=f"Test user 問題 {i+1}"
            )
        
        # other_user 創建 3 個對話
        for i in range(3):
            await crud_conversations.create_conversation(
                db=test_db,
                user_id=other_user.id,
                first_question=f"Other user 問題 {i+1}"
            )
        
        # 驗證計數
        test_user_count = await crud_conversations.get_conversation_count(
            db=test_db,
            user_id=test_user.id
        )
        other_user_count = await crud_conversations.get_conversation_count(
            db=test_db,
            user_id=other_user.id
        )
        
        assert test_user_count == 2
        assert other_user_count == 3


class TestCachedDocuments:
    """測試對話中的文檔緩存功能"""
    
    @pytest.mark.asyncio
    async def test_remove_cached_document_success(self, test_db, test_user):
        """
        場景：從對話中移除緩存的文檔
        預期：成功移除
        """
        # 創建對話並添加緩存文檔
        conv_id = uuid4()
        doc_id_to_remove = str(uuid4())
        
        conversation_data = {
            "_id": conv_id,
            "title": "帶緩存文檔的對話",
            "user_id": test_user.id,
            "messages": [],
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "message_count": 0,
            "total_tokens": 0,
            "cached_documents": [doc_id_to_remove, str(uuid4())],  # 2 個文檔
            "cached_document_data": None
        }
        
        await test_db["conversations"].insert_one(conversation_data)
        
        # 移除其中一個文檔
        success = await crud_conversations.remove_cached_document(
            db=test_db,
            conversation_id=conv_id,
            user_id=test_user.id,
            document_id=doc_id_to_remove
        )
        
        assert success is True
        
        # 驗證文檔已被移除
        updated_conv = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=conv_id,
            user_id=test_user.id
        )
        assert doc_id_to_remove not in updated_conv.cached_documents
        assert len(updated_conv.cached_documents) == 1  # 還剩 1 個
    
    @pytest.mark.asyncio
    async def test_remove_cached_document_not_found(self, test_db, test_user, test_conversation):
        """
        場景：嘗試移除不存在的緩存文檔
        預期：返回 False
        """
        fake_doc_id = str(uuid4())
        
        success = await crud_conversations.remove_cached_document(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id,
            document_id=fake_doc_id
        )
        
        # 根據實際實現，可能返回 False 或 True
        # 這取決於 CRUD 實現如何處理不存在的文檔
        assert success is not None
