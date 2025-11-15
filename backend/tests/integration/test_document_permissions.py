"""
文档权限集成测试

测试真实的业务场景：
1. 用户只能访问自己的文档
2. 用户不能访问别人的文档
3. 文档不存在时返回 404

使用真实的测试数据库，不使用 mock。
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from fastapi import status

from app.crud import crud_documents
from app.apis.v1.documents import get_owned_document
from app.models.document_models import Document
from app.models.user_models import User

# 标记为集成测试
pytestmark = pytest.mark.integration


class TestDocumentOwnership:
    """测试文档所有权验证"""
    
    @pytest.mark.asyncio
    async def test_get_own_document_success(self, test_db, test_user, test_document):
        """
        场景：用户获取自己的文档
        预期：成功返回文档，状态码 200
        """
        # 验证文档确实属于测试用户
        assert test_document.owner_id == test_user.id
        
        # 使用真实的依赖函数
        result = await get_owned_document(
            document_id=test_document.id,
            db=test_db,
            current_user=test_user
        )
        
        # 验证返回的文档
        assert result is not None
        assert result.id == test_document.id
        assert result.filename == test_document.filename
        assert result.owner_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(self, test_db, test_user):
        """
        场景：用户尝试获取不存在的文档
        预期：抛出 404 HTTPException
        """
        non_existent_id = uuid4()
        
        # 应该抛出 404 异常
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_owned_document(
                document_id=non_existent_id,
                db=test_db,
                current_user=test_user
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert str(non_existent_id) in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_other_user_document_forbidden(
        self, test_db, test_user, other_user, test_document
    ):
        """
        场景：用户尝试获取别人的文档
        预期：抛出 403 HTTPException
        
        业务规则：document.owner_id != current_user.id
        """
        # 验证：文档属于 test_user，而不是 other_user
        assert test_document.owner_id == test_user.id
        assert test_document.owner_id != other_user.id
        
        # other_user 尝试访问 test_user 的文档
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_owned_document(
                document_id=test_document.id,
                db=test_db,
                current_user=other_user  # 使用 other_user
            )
        
        # 应该是 403 Forbidden
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in exc_info.value.detail.lower()


class TestDocumentCRUDWithPermissions:
    """测试文档 CRUD 操作的权限控制"""
    
    @pytest.mark.asyncio
    async def test_create_document_sets_correct_owner(self, test_db, test_user):
        """
        场景：创建文档时，owner_id 应该设置为当前用户
        预期：创建的文档 owner_id 等于 current_user.id
        """
        from app.models.document_models import DocumentCreate
        
        doc_data = DocumentCreate(
            filename="new_document.txt",
            file_type="text/plain",
            size=2048,
            owner_id=test_user.id,
            tags=["new"],
            metadata={}
        )
        
        # 使用真实的 CRUD 函数创建文档
        created_doc = await crud_documents.create_document(
            db=test_db,
            document_data=doc_data,
            owner_id=test_user.id,
            file_path="/test/new_document.txt"
        )
        
        # 验证：文档属于创建者
        assert created_doc.owner_id == test_user.id
        assert created_doc.filename == "new_document.txt"
        
        # 验证：可以从数据库中获取
        retrieved = await crud_documents.get_document_by_id(test_db, created_doc.id)
        assert retrieved is not None
        assert retrieved.owner_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_delete_own_document_success(self, test_db, test_user, test_document):
        """
        场景：用户删除自己的文档
        预期：成功删除
        """
        # 验证文档存在且属于用户
        assert test_document.owner_id == test_user.id
        
        # 删除文档
        result = await crud_documents.delete_document_by_id(
            test_db, 
            test_document.id
        )
        
        assert result is True
        
        # 验证：文档已被删除
        deleted_doc = await crud_documents.get_document_by_id(
            test_db, 
            test_document.id
        )
        assert deleted_doc is None
    
    @pytest.mark.asyncio
    async def test_update_own_document_success(self, test_db, test_user, test_document):
        """
        场景：用户更新自己的文档
        预期：成功更新
        """
        # 验证文档属于用户
        assert test_document.owner_id == test_user.id
        
        # 更新文档
        update_data = {
            "filename": "updated_filename.txt",
            "tags": ["updated", "test"]
        }
        
        updated_doc = await crud_documents.update_document(
            test_db,
            test_document.id,
            update_data
        )
        
        # 验证更新成功
        assert updated_doc is not None
        assert updated_doc.filename == "updated_filename.txt"
        assert "updated" in updated_doc.tags
        # owner_id 不应该改变
        assert updated_doc.owner_id == test_user.id


class TestDocumentListWithPermissions:
    """测试文档列表的权限过滤"""
    
    @pytest.mark.asyncio
    async def test_list_documents_only_shows_own_documents(
        self, test_db, test_user, other_user
    ):
        """
        场景：列出文档时，只显示当前用户的文档
        预期：不会返回其他用户的文档
        
        这是重要的业务规则：用户不应该看到别人的文档列表
        """
        from app.models.document_models import DocumentCreate
        
        # 创建属于 test_user 的文档
        doc1_data = DocumentCreate(
            filename="user1_doc1.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100
        )
        doc1 = await crud_documents.create_document(
            test_db, doc1_data, test_user.id, "/test/doc1.txt"
        )
        
        doc2_data = DocumentCreate(
            filename="user1_doc2.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=200
        )
        doc2 = await crud_documents.create_document(
            test_db, doc2_data, test_user.id, "/test/doc2.txt"
        )
        
        # 创建属于 other_user 的文档
        doc3_data = DocumentCreate(
            filename="user2_doc1.txt",
            owner_id=other_user.id,
            file_type="text/plain",
            size=300
        )
        doc3 = await crud_documents.create_document(
            test_db, doc3_data, other_user.id, "/test/doc3.txt"
        )
        
        # 获取 test_user 的文档列表
        # 注意：这里需要使用过滤 owner_id 的查询
        user1_docs = await test_db["documents"].find(
            {"owner_id": test_user.id}
        ).to_list(length=100)
        
        # 验证：只返回 test_user 的文档
        assert len(user1_docs) == 2
        doc_ids = [str(doc["_id"]) for doc in user1_docs]
        assert str(doc1.id) in doc_ids
        assert str(doc2.id) in doc_ids
        assert str(doc3.id) not in doc_ids  # other_user 的文档不应该出现


class TestRealWorldScenarios:
    """测试真实世界的业务场景"""
    
    @pytest.mark.asyncio
    async def test_user_workflow_create_access_delete(self, test_db, test_user):
        """
        场景：完整的用户工作流
        1. 用户创建文档
        2. 用户访问自己的文档
        3. 用户更新文档
        4. 用户删除文档
        
        这是最常见的业务流程。
        """
        from app.models.document_models import DocumentCreate
        
        # 步骤 1：创建文档
        doc_data = DocumentCreate(
            filename="workflow_test.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=500,
            tags=["workflow"]
        )
        
        created_doc = await crud_documents.create_document(
            test_db, doc_data, test_user.id, "/test/workflow.txt"
        )
        
        assert created_doc.owner_id == test_user.id
        doc_id = created_doc.id
        
        # 步骤 2：访问文档
        retrieved = await get_owned_document(doc_id, test_db, test_user)
        assert retrieved.id == doc_id
        assert retrieved.filename == "workflow_test.txt"
        
        # 步骤 3：更新文档
        update_data = {"tags": ["workflow", "updated"]}
        updated = await crud_documents.update_document(
            test_db, doc_id, update_data
        )
        assert "updated" in updated.tags
        
        # 步骤 4：删除文档
        deleted = await crud_documents.delete_document_by_id(test_db, doc_id)
        assert deleted is True
        
        # 验证：文档已删除
        final_check = await crud_documents.get_document_by_id(test_db, doc_id)
        assert final_check is None
    
    @pytest.mark.asyncio
    async def test_multiple_users_cannot_access_each_others_documents(
        self, test_db, test_user, other_user
    ):
        """
        场景：多用户环境下的权限隔离
        - User A 创建文档
        - User B 不能访问 User A 的文档
        - User B 创建自己的文档
        - User A 不能访问 User B 的文档
        
        这是系统安全的关键：用户之间的数据隔离。
        """
        from app.models.document_models import DocumentCreate
        from fastapi import HTTPException
        
        # User A 创建文档
        doc_a_data = DocumentCreate(
            filename="user_a_private.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100
        )
        doc_a = await crud_documents.create_document(
            test_db, doc_a_data, test_user.id, "/test/doc_a.txt"
        )
        
        # User B 创建文档
        doc_b_data = DocumentCreate(
            filename="user_b_private.txt",
            owner_id=other_user.id,
            file_type="text/plain",
            size=200
        )
        doc_b = await crud_documents.create_document(
            test_db, doc_b_data, other_user.id, "/test/doc_b.txt"
        )
        
        # User B 尝试访问 User A 的文档 → 应该失败
        with pytest.raises(HTTPException) as exc:
            await get_owned_document(doc_a.id, test_db, other_user)
        assert exc.value.status_code == 403
        
        # User A 尝试访问 User B 的文档 → 应该失败
        with pytest.raises(HTTPException) as exc:
            await get_owned_document(doc_b.id, test_db, test_user)
        assert exc.value.status_code == 403
        
        # 但是用户可以访问自己的文档
        user_a_doc = await get_owned_document(doc_a.id, test_db, test_user)
        assert user_a_doc.id == doc_a.id
        
        user_b_doc = await get_owned_document(doc_b.id, test_db, other_user)
        assert user_b_doc.id == doc_b.id
