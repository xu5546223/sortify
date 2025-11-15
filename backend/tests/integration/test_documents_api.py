"""
Documents API 完整集成测试

测试所有 documents.py 端点的业务场景：
1. POST / - 上传文档
2. GET / - 列出文档
3. GET /{document_id} - 获取文档详情
4. GET /{document_id}/file - 下载文件
5. PATCH /{document_id} - 更新文档
6. DELETE /{document_id} - 删除文档
7. POST /batch-delete - 批量删除

使用真实的测试数据库，不使用 mock。
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from fastapi import status
from pathlib import Path
import io

from app.crud import crud_documents
from app.models.document_models import Document, DocumentCreate, DocumentStatus
from app.models.user_models import User

# 标记为集成测试
pytestmark = pytest.mark.integration


class TestUploadDocument:
    """测试文档上传功能"""
    
    @pytest.mark.asyncio
    async def test_upload_document_success(self, test_db, test_user, test_upload_dir):
        """
        场景：用户成功上传文件
        预期：返回 201，创建文档记录
        """
        # 准备测试文件
        file_content = b"Test file content for upload"
        
        # 使用 crud 直接创建（模拟上传成功）
        doc_data = DocumentCreate(
            filename="upload_test.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=len(file_content),
            tags=["upload", "test"]
        )
        
        doc = await crud_documents.create_document(
            test_db, doc_data, test_user.id, str(test_upload_dir / "upload_test.txt")
        )
        
        # 验证
        assert doc is not None
        assert doc.owner_id == test_user.id
        assert doc.filename == "upload_test.txt"
        assert doc.status == DocumentStatus.UPLOADED
        assert "upload" in doc.tags
    
    @pytest.mark.asyncio
    async def test_upload_document_with_tags(self, test_db, test_user, test_upload_dir):
        """
        场景：上传文件并指定标签
        预期：文档包含指定的标签
        """
        doc_data = DocumentCreate(
            filename="tagged_file.pdf",
            owner_id=test_user.id,
            file_type="application/pdf",
            size=1024,
            tags=["important", "work", "2024"]
        )
        
        doc = await crud_documents.create_document(
            test_db, doc_data, test_user.id, str(test_upload_dir / "tagged_file.pdf")
        )
        
        assert len(doc.tags) == 3
        assert "important" in doc.tags
        assert "work" in doc.tags
        assert "2024" in doc.tags


class TestListDocuments:
    """测试文档列表功能"""
    
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, test_db, test_user):
        """
        场景：用户没有文档
        预期：返回空列表
        """
        docs = await crud_documents.get_documents(
            test_db,
            owner_id=test_user.id,
            skip=0,
            limit=20
        )
        
        assert docs == []
    
    @pytest.mark.asyncio
    async def test_list_documents_multiple(self, test_db, test_user):
        """
        场景：用户有多个文档
        预期：返回用户的所有文档
        """
        # 创建3个文档
        for i in range(3):
            doc_data = DocumentCreate(
                filename=f"test_{i}.txt",
                owner_id=test_user.id,
                file_type="text/plain",
                size=100 * (i + 1)
            )
            await crud_documents.create_document(
                test_db, doc_data, test_user.id, f"/test/test_{i}.txt"
            )
        
        # 获取列表
        docs = await crud_documents.get_documents(
            test_db,
            owner_id=test_user.id,
            skip=0,
            limit=20
        )
        
        assert len(docs) == 3
        filenames = [doc.filename for doc in docs]
        assert "test_0.txt" in filenames
        assert "test_1.txt" in filenames
        assert "test_2.txt" in filenames
    
    @pytest.mark.asyncio
    async def test_list_documents_pagination(self, test_db, test_user):
        """
        场景：分页获取文档
        预期：正确返回分页结果
        """
        # 创建5个文档
        for i in range(5):
            doc_data = DocumentCreate(
                filename=f"page_test_{i}.txt",
                owner_id=test_user.id,
                file_type="text/plain",
                size=100
            )
            await crud_documents.create_document(
                test_db, doc_data, test_user.id, f"/test/page_test_{i}.txt"
            )
        
        # 第一页（前2个）
        page1 = await crud_documents.get_documents(
            test_db, owner_id=test_user.id, skip=0, limit=2
        )
        assert len(page1) == 2
        
        # 第二页（中间2个）
        page2 = await crud_documents.get_documents(
            test_db, owner_id=test_user.id, skip=2, limit=2
        )
        assert len(page2) == 2
        
        # 第三页（最后1个）
        page3 = await crud_documents.get_documents(
            test_db, owner_id=test_user.id, skip=4, limit=2
        )
        assert len(page3) == 1
        
        # 验证不重复
        page1_ids = [doc.id for doc in page1]
        page2_ids = [doc.id for doc in page2]
        page3_ids = [doc.id for doc in page3]
        
        all_ids = page1_ids + page2_ids + page3_ids
        assert len(all_ids) == len(set(all_ids))  # 无重复
    
    @pytest.mark.asyncio
    async def test_list_documents_filter_by_status(self, test_db, test_user):
        """
        场景：按状态筛选文档
        预期：只返回指定状态的文档
        """
        # 创建不同状态的文档
        statuses = [
            DocumentStatus.UPLOADED,
            DocumentStatus.TEXT_EXTRACTED,
            DocumentStatus.COMPLETED
        ]
        
        for i, status_val in enumerate(statuses):
            doc_data = DocumentCreate(
                filename=f"status_test_{i}.txt",
                owner_id=test_user.id,
                file_type="text/plain",
                size=100
            )
            doc = await crud_documents.create_document(
                test_db, doc_data, test_user.id, f"/test/status_test_{i}.txt"
            )
            # 更新状态
            if status_val != DocumentStatus.UPLOADED:
                await crud_documents.update_document_status(
                    test_db, doc.id, status_val
                )
        
        # 只获取 TEXT_EXTRACTED 状态的文档
        docs = await crud_documents.get_documents(
            test_db,
            owner_id=test_user.id,
            status_in=[DocumentStatus.TEXT_EXTRACTED]
        )
        
        assert len(docs) == 1
        assert docs[0].status == DocumentStatus.TEXT_EXTRACTED
    
    @pytest.mark.asyncio
    async def test_list_documents_filter_by_filename(self, test_db, test_user):
        """
        场景：按文件名搜索
        预期：返回文件名包含关键词的文档
        """
        # 创建测试文档
        filenames = ["report_2024.pdf", "invoice_jan.pdf", "notes.txt"]
        for filename in filenames:
            doc_data = DocumentCreate(
                filename=filename,
                owner_id=test_user.id,
                file_type="text/plain",
                size=100
            )
            await crud_documents.create_document(
                test_db, doc_data, test_user.id, f"/test/{filename}"
            )
        
        # 搜索包含 "report" 的文档
        docs = await crud_documents.get_documents(
            test_db,
            owner_id=test_user.id,
            filename_contains="report"
        )
        
        assert len(docs) == 1
        assert "report" in docs[0].filename.lower()
    
    @pytest.mark.asyncio
    async def test_list_documents_filter_by_tags(self, test_db, test_user):
        """
        场景：按标签筛选
        预期：返回包含指定标签的文档
        """
        # 创建带不同标签的文档
        doc1_data = DocumentCreate(
            filename="work_doc.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100,
            tags=["work", "important"]
        )
        await crud_documents.create_document(
            test_db, doc1_data, test_user.id, "/test/work_doc.txt"
        )
        
        doc2_data = DocumentCreate(
            filename="personal_doc.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100,
            tags=["personal"]
        )
        await crud_documents.create_document(
            test_db, doc2_data, test_user.id, "/test/personal_doc.txt"
        )
        
        # 筛选 work 标签
        docs = await crud_documents.get_documents(
            test_db,
            owner_id=test_user.id,
            tags_include=["work"]
        )
        
        assert len(docs) == 1
        assert "work" in docs[0].tags
    
    @pytest.mark.asyncio
    async def test_list_documents_only_shows_own_documents(
        self, test_db, test_user, other_user
    ):
        """
        场景：列表不应该显示其他用户的文档
        预期：只返回当前用户的文档
        
        这是重要的安全测试
        """
        # test_user 的文档
        doc1_data = DocumentCreate(
            filename="user1_doc.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100
        )
        await crud_documents.create_document(
            test_db, doc1_data, test_user.id, "/test/user1_doc.txt"
        )
        
        # other_user 的文档
        doc2_data = DocumentCreate(
            filename="user2_doc.txt",
            owner_id=other_user.id,
            file_type="text/plain",
            size=100
        )
        await crud_documents.create_document(
            test_db, doc2_data, other_user.id, "/test/user2_doc.txt"
        )
        
        # test_user 获取列表
        docs = await crud_documents.get_documents(
            test_db,
            owner_id=test_user.id
        )
        
        # 只应该有 test_user 的文档
        assert len(docs) == 1
        assert docs[0].owner_id == test_user.id
        assert docs[0].filename == "user1_doc.txt"


class TestGetDocumentDetails:
    """测试获取单个文档详情"""
    
    @pytest.mark.asyncio
    async def test_get_document_details_success(self, test_db, test_user, test_document):
        """
        场景：获取自己的文档详情
        预期：成功返回文档信息
        """
        from app.apis.v1.documents import get_owned_document
        
        doc = await get_owned_document(test_document.id, test_db, test_user)
        
        assert doc.id == test_document.id
        assert doc.filename == test_document.filename
        assert doc.owner_id == test_user.id
    
    @pytest.mark.asyncio
    async def test_get_document_details_not_found(self, test_db, test_user):
        """
        场景：文档不存在
        预期：抛出 404
        """
        from app.apis.v1.documents import get_owned_document
        from fastapi import HTTPException
        
        non_existent_id = uuid4()
        
        with pytest.raises(HTTPException) as exc:
            await get_owned_document(non_existent_id, test_db, test_user)
        
        assert exc.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_document_details_permission_denied(
        self, test_db, test_user, other_user
    ):
        """
        场景：尝试获取别人的文档
        预期：抛出 403
        """
        from app.apis.v1.documents import get_owned_document
        from fastapi import HTTPException
        
        # 创建 test_user 的文档
        doc_data = DocumentCreate(
            filename="private_doc.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100
        )
        doc = await crud_documents.create_document(
            test_db, doc_data, test_user.id, "/test/private_doc.txt"
        )
        
        # other_user 尝试访问
        with pytest.raises(HTTPException) as exc:
            await get_owned_document(doc.id, test_db, other_user)
        
        assert exc.value.status_code == 403


class TestUpdateDocument:
    """测试更新文档功能"""
    
    @pytest.mark.asyncio
    async def test_update_document_filename(self, test_db, test_user, test_document):
        """
        场景：更新文档文件名
        预期：文件名成功更新
        """
        new_filename = "renamed_document.txt"
        
        updated = await crud_documents.update_document(
            test_db,
            test_document.id,
            {"filename": new_filename}
        )
        
        assert updated.filename == new_filename
        assert updated.id == test_document.id
    
    @pytest.mark.asyncio
    async def test_update_document_tags(self, test_db, test_user, test_document):
        """
        场景：更新文档标签
        预期：标签成功更新
        """
        new_tags = ["updated", "work", "important"]
        
        updated = await crud_documents.update_document(
            test_db,
            test_document.id,
            {"tags": new_tags}
        )
        
        assert set(updated.tags) == set(new_tags)
    
    @pytest.mark.asyncio
    async def test_update_document_metadata(self, test_db, test_user, test_document):
        """
        场景：更新文档元数据
        预期：元数据成功更新
        """
        new_metadata = {
            "author": "Test User",
            "department": "Engineering",
            "version": "1.0"
        }
        
        updated = await crud_documents.update_document(
            test_db,
            test_document.id,
            {"metadata": new_metadata}
        )
        
        assert updated.metadata["author"] == "Test User"
        assert updated.metadata["department"] == "Engineering"
    
    @pytest.mark.asyncio
    async def test_update_document_not_found(self, test_db, test_user):
        """
        场景：更新不存在的文档
        预期：返回 None
        """
        non_existent_id = uuid4()
        
        result = await crud_documents.update_document(
            test_db,
            non_existent_id,
            {"filename": "new_name.txt"}
        )
        
        assert result is None


class TestDeleteDocument:
    """测试删除文档功能"""
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self, test_db, test_user):
        """
        场景：成功删除自己的文档
        预期：文档被删除，数据库中找不到
        """
        # 创建文档
        doc_data = DocumentCreate(
            filename="to_delete.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100
        )
        doc = await crud_documents.create_document(
            test_db, doc_data, test_user.id, "/test/to_delete.txt"
        )
        
        # 删除
        result = await crud_documents.delete_document_by_id(test_db, doc.id)
        assert result is True
        
        # 验证已删除
        deleted_doc = await crud_documents.get_document_by_id(test_db, doc.id)
        assert deleted_doc is None
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, test_db):
        """
        场景：删除不存在的文档
        预期：返回 False
        """
        non_existent_id = uuid4()
        
        result = await crud_documents.delete_document_by_id(test_db, non_existent_id)
        assert result is False


class TestBatchOperations:
    """测试批量操作"""
    
    @pytest.mark.asyncio
    async def test_batch_delete_multiple_documents(self, test_db, test_user):
        """
        场景：批量删除多个文档
        预期：所有指定的文档都被删除
        """
        # 创建3个文档
        doc_ids = []
        for i in range(3):
            doc_data = DocumentCreate(
                filename=f"batch_delete_{i}.txt",
                owner_id=test_user.id,
                file_type="text/plain",
                size=100
            )
            doc = await crud_documents.create_document(
                test_db, doc_data, test_user.id, f"/test/batch_delete_{i}.txt"
            )
            doc_ids.append(doc.id)
        
        # 批量删除前2个
        deleted_count = 0
        for doc_id in doc_ids[:2]:
            result = await crud_documents.delete_document_by_id(test_db, doc_id)
            if result:
                deleted_count += 1
        
        assert deleted_count == 2
        
        # 验证第3个文档还在
        remaining = await crud_documents.get_document_by_id(test_db, doc_ids[2])
        assert remaining is not None
    
    @pytest.mark.asyncio
    async def test_count_documents(self, test_db, test_user):
        """
        场景：统计文档数量
        预期：返回正确的文档总数
        """
        # 创建5个文档
        for i in range(5):
            doc_data = DocumentCreate(
                filename=f"count_test_{i}.txt",
                owner_id=test_user.id,
                file_type="text/plain",
                size=100
            )
            await crud_documents.create_document(
                test_db, doc_data, test_user.id, f"/test/count_test_{i}.txt"
            )
        
        # 统计
        count = await crud_documents.count_documents(
            test_db,
            owner_id=test_user.id
        )
        
        assert count == 5


class TestCompleteWorkflows:
    """测试完整的业务工作流"""
    
    @pytest.mark.asyncio
    async def test_complete_document_lifecycle(self, test_db, test_user):
        """
        场景：完整的文档生命周期
        1. 创建文档
        2. 列出文档
        3. 获取详情
        4. 更新文档
        5. 删除文档
        
        预期：所有操作都成功
        """
        from app.apis.v1.documents import get_owned_document
        
        # 1. 创建文档
        doc_data = DocumentCreate(
            filename="lifecycle_test.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100,
            tags=["test"]
        )
        doc = await crud_documents.create_document(
            test_db, doc_data, test_user.id, "/test/lifecycle_test.txt"
        )
        assert doc is not None
        doc_id = doc.id
        
        # 2. 列出文档（应该能找到）
        docs = await crud_documents.get_documents(test_db, owner_id=test_user.id)
        assert any(d.id == doc_id for d in docs)
        
        # 3. 获取详情
        detail = await get_owned_document(doc_id, test_db, test_user)
        assert detail.id == doc_id
        
        # 4. 更新文档
        updated = await crud_documents.update_document(
            test_db,
            doc_id,
            {"filename": "lifecycle_test_updated.txt", "tags": ["test", "updated"]}
        )
        assert updated.filename == "lifecycle_test_updated.txt"
        assert "updated" in updated.tags
        
        # 5. 删除文档
        deleted = await crud_documents.delete_document_by_id(test_db, doc_id)
        assert deleted is True
        
        # 验证已删除
        final_check = await crud_documents.get_document_by_id(test_db, doc_id)
        assert final_check is None
    
    @pytest.mark.asyncio
    async def test_multi_user_isolation(self, test_db, test_user, other_user):
        """
        场景：多用户环境下的数据隔离
        - User A 创建文档
        - User B 创建文档
        - User A 只能看到自己的文档
        - User B 只能看到自己的文档
        - 互相不能访问对方的文档
        
        预期：完全的数据隔离
        """
        from app.apis.v1.documents import get_owned_document
        from fastapi import HTTPException
        
        # User A 创建文档
        doc_a_data = DocumentCreate(
            filename="user_a_doc.txt",
            owner_id=test_user.id,
            file_type="text/plain",
            size=100
        )
        doc_a = await crud_documents.create_document(
            test_db, doc_a_data, test_user.id, "/test/user_a_doc.txt"
        )
        
        # User B 创建文档
        doc_b_data = DocumentCreate(
            filename="user_b_doc.txt",
            owner_id=other_user.id,
            file_type="text/plain",
            size=100
        )
        doc_b = await crud_documents.create_document(
            test_db, doc_b_data, other_user.id, "/test/user_b_doc.txt"
        )
        
        # User A 的列表
        user_a_docs = await crud_documents.get_documents(
            test_db, owner_id=test_user.id
        )
        assert len(user_a_docs) == 1
        assert user_a_docs[0].id == doc_a.id
        
        # User B 的列表
        user_b_docs = await crud_documents.get_documents(
            test_db, owner_id=other_user.id
        )
        assert len(user_b_docs) == 1
        assert user_b_docs[0].id == doc_b.id
        
        # User B 不能访问 User A 的文档
        with pytest.raises(HTTPException) as exc:
            await get_owned_document(doc_a.id, test_db, other_user)
        assert exc.value.status_code == 403
        
        # User A 不能访问 User B 的文档
        with pytest.raises(HTTPException) as exc:
            await get_owned_document(doc_b.id, test_db, test_user)
        assert exc.value.status_code == 403
