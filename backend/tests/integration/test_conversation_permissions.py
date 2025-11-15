"""
Conversation 權限測試

專門測試對話相關的權限和安全性：
1. 用戶只能訪問自己的對話
2. 用戶不能訪問/修改/刪除別人的對話
3. 權限檢查的一致性

這些測試確保重構後權限邏輯保持一致。
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime, UTC

from app.crud import crud_conversations
from app.models.conversation_models import ConversationInDB, ConversationMessage, ConversationUpdate
from app.models.user_models import User

# 標記為集成測試
pytestmark = pytest.mark.integration


class TestConversationAccessControl:
    """測試對話訪問控制"""
    
    @pytest.mark.asyncio
    async def test_cannot_get_other_user_conversation(self, test_db, test_user, other_user, test_conversation):
        """
        場景：用戶嘗試訪問別人的對話
        預期：無法獲取對話（返回 None）
        """
        # test_conversation 屬於 test_user
        # other_user 嘗試訪問
        conversation = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id
        )
        
        assert conversation is None
    
    @pytest.mark.asyncio
    async def test_cannot_update_other_user_conversation(self, test_db, test_user, other_user, test_conversation):
        """
        場景：用戶嘗試更新別人的對話
        預期：更新失敗（返回 None）
        """
        update_data = ConversationUpdate(title="嘗試篡改別人的對話")
        
        result = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id,
            update_data=update_data
        )
        
        assert result is None
        
        # 驗證對話未被修改
        original = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        assert original.title == test_conversation.title  # 標題沒變
    
    @pytest.mark.asyncio
    async def test_cannot_delete_other_user_conversation(self, test_db, test_user, other_user, test_conversation):
        """
        場景：用戶嘗試刪除別人的對話
        預期：刪除失敗（返回 False）
        """
        success = await crud_conversations.delete_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id
        )
        
        assert success is False
        
        # 驗證對話仍然存在
        still_exists = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        assert still_exists is not None
    
    @pytest.mark.asyncio
    async def test_cannot_get_messages_from_other_user_conversation(
        self, test_db, test_user, other_user, test_conversation_with_messages
    ):
        """
        場景：用戶嘗試獲取別人對話的消息
        預期：無法獲取（返回空或 None）
        """
        # test_conversation_with_messages 屬於 test_user
        # other_user 嘗試訪問消息
        messages = await crud_conversations.get_recent_messages(
            db=test_db,
            conversation_id=test_conversation_with_messages.id,
            user_id=other_user.id,
            limit=50
        )
        
        # 根據實現，可能返回 None 或空列表
        assert messages is None or len(messages) == 0


class TestConversationOwnership:
    """測試對話所有權驗證"""
    
    @pytest.mark.asyncio
    async def test_list_only_shows_own_conversations(self, test_db, test_user, other_user):
        """
        場景：系統中有多個用戶的對話
        預期：list_user_conversations 只返回自己的對話
        """
        # test_user 創建 3 個對話
        test_user_conv_ids = []
        for i in range(3):
            conv = await crud_conversations.create_conversation(
                db=test_db,
                user_id=test_user.id,
                first_question=f"Test user 問題 {i+1}"
            )
            test_user_conv_ids.append(conv.id)
        
        # other_user 創建 2 個對話
        other_user_conv_ids = []
        for i in range(2):
            conv = await crud_conversations.create_conversation(
                db=test_db,
                user_id=other_user.id,
                first_question=f"Other user 問題 {i+1}"
            )
            other_user_conv_ids.append(conv.id)
        
        # test_user 獲取列表
        test_user_conversations = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=test_user.id,
            skip=0,
            limit=50
        )
        
        # 驗證 test_user 只看到自己的對話
        assert len(test_user_conversations) == 3
        returned_ids = [conv.id for conv in test_user_conversations]
        for conv_id in test_user_conv_ids:
            assert conv_id in returned_ids
        for conv_id in other_user_conv_ids:
            assert conv_id not in returned_ids
        
        # other_user 獲取列表
        other_user_conversations = await crud_conversations.list_user_conversations(
            db=test_db,
            user_id=other_user.id,
            skip=0,
            limit=50
        )
        
        # 驗證 other_user 只看到自己的對話
        assert len(other_user_conversations) == 2
        returned_ids = [conv.id for conv in other_user_conversations]
        for conv_id in other_user_conv_ids:
            assert conv_id in returned_ids
        for conv_id in test_user_conv_ids:
            assert conv_id not in returned_ids
    
    @pytest.mark.asyncio
    async def test_count_only_own_conversations(self, test_db, test_user, other_user):
        """
        場景：系統中有多個用戶的對話
        預期：get_conversation_count 只計數自己的對話
        """
        # test_user 創建 3 個對話
        for i in range(3):
            await crud_conversations.create_conversation(
                db=test_db,
                user_id=test_user.id,
                first_question=f"Test user 問題 {i+1}"
            )
        
        # other_user 創建 5 個對話
        for i in range(5):
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
        
        assert test_user_count == 3
        assert other_user_count == 5


class TestConversationIsolation:
    """測試對話隔離性"""
    
    @pytest.mark.asyncio
    async def test_operations_are_isolated_between_users(self, test_db, test_user, other_user):
        """
        場景：完整的操作隔離測試
        預期：一個用戶的操作不影響另一個用戶
        """
        # 1. test_user 創建對話
        test_conv = await crud_conversations.create_conversation(
            db=test_db,
            user_id=test_user.id,
            first_question="Test user 的對話"
        )
        
        # 2. other_user 創建對話
        other_conv = await crud_conversations.create_conversation(
            db=test_db,
            user_id=other_user.id,
            first_question="Other user 的對話"
        )
        
        # 3. test_user 無法訪問 other_user 的對話
        cannot_access = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=other_conv.id,
            user_id=test_user.id
        )
        assert cannot_access is None
        
        # 4. other_user 無法訪問 test_user 的對話
        cannot_access_2 = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conv.id,
            user_id=other_user.id
        )
        assert cannot_access_2 is None
        
        # 5. test_user 更新自己的對話 - 應該成功
        updated = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=test_conv.id,
            user_id=test_user.id,
            update_data=ConversationUpdate(title="更新後的標題")
        )
        assert updated is not None
        assert updated.title == "更新後的標題"
        
        # 6. other_user 嘗試更新 test_user 的對話 - 應該失敗
        failed_update = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=test_conv.id,
            user_id=other_user.id,
            update_data=ConversationUpdate(title="嘗試篡改")
        )
        assert failed_update is None
        
        # 7. 驗證對話沒有被篡改
        still_original = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conv.id,
            user_id=test_user.id
        )
        assert still_original.title == "更新後的標題"  # 保持 test_user 的更新
        
        # 8. test_user 刪除自己的對話 - 應該成功
        deleted = await crud_conversations.delete_conversation(
            db=test_db,
            conversation_id=test_conv.id,
            user_id=test_user.id
        )
        assert deleted is True
        
        # 9. 驗證 test_user 的對話被刪除，但 other_user 的對話仍然存在
        test_conv_gone = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conv.id,
            user_id=test_user.id
        )
        assert test_conv_gone is None
        
        other_conv_still_exists = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=other_conv.id,
            user_id=other_user.id
        )
        assert other_conv_still_exists is not None


class TestCachedDocumentPermissions:
    """測試緩存文檔操作的權限"""
    
    @pytest.mark.asyncio
    async def test_cannot_remove_cached_document_from_other_user_conversation(
        self, test_db, test_user, other_user
    ):
        """
        場景：用戶嘗試從別人的對話中移除緩存文檔
        預期：操作失敗
        """
        # 創建 test_user 的對話，包含緩存文檔
        conv_id = uuid4()
        doc_id = str(uuid4())
        
        conversation_data = {
            "_id": conv_id,
            "title": "帶緩存文檔的對話",
            "user_id": test_user.id,
            "messages": [],
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "message_count": 0,
            "total_tokens": 0,
            "cached_documents": [doc_id],
            "cached_document_data": None
        }
        
        await test_db["conversations"].insert_one(conversation_data)
        
        # other_user 嘗試移除文檔
        success = await crud_conversations.remove_cached_document(
            db=test_db,
            conversation_id=conv_id,
            user_id=other_user.id,  # 不同的用戶
            document_id=doc_id
        )
        
        assert success is False
        
        # 驗證文檔沒有被移除
        conv = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=conv_id,
            user_id=test_user.id
        )
        assert doc_id in conv.cached_documents  # 文檔還在


class TestPermissionConsistency:
    """測試權限檢查的一致性"""
    
    @pytest.mark.asyncio
    async def test_all_operations_reject_unauthorized_access(
        self, test_db, test_user, other_user, test_conversation
    ):
        """
        場景：對所有操作進行統一的權限檢查
        預期：所有操作都拒絕未授權訪問
        """
        # test_conversation 屬於 test_user
        
        # 1. GET - 獲取對話
        get_result = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id
        )
        assert get_result is None, "GET 應該拒絕未授權訪問"
        
        # 2. GET messages - 獲取消息
        messages_result = await crud_conversations.get_recent_messages(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id,
            limit=50
        )
        assert messages_result is None or len(messages_result) == 0, "GET messages 應該拒絕未授權訪問"
        
        # 3. UPDATE - 更新對話
        update_result = await crud_conversations.update_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id,
            update_data=ConversationUpdate(title="未授權更新")
        )
        assert update_result is None, "UPDATE 應該拒絕未授權訪問"
        
        # 4. DELETE - 刪除對話
        delete_result = await crud_conversations.delete_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=other_user.id
        )
        assert delete_result is False, "DELETE 應該拒絕未授權訪問"
        
        # 5. 驗證對話仍然完好無損
        original = await crud_conversations.get_conversation(
            db=test_db,
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        assert original is not None, "對話應該仍然存在"
        assert original.title == test_conversation.title, "對話標題應該未被修改"
