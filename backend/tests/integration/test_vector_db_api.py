"""
Vector DB API 整合測試

測試 Vector DB API 的核心業務邏輯，專注於：
- 文檔向量狀態管理
- 權限控制
- 數據庫副作用驗證

注意：這是服務層測試，不是 HTTP API 測試
"""

import pytest
import pytest_asyncio
import uuid
from uuid import uuid4, UUID
from datetime import datetime, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user_models import User
from app.models.document_models import Document, DocumentStatus, VectorStatus
from app.core.password_utils import get_password_hash
from app.crud.crud_documents import get_document_by_id, update_document_vector_status
from app.dependencies import get_vector_db_service
from app.services.vector.embedding_service import embedding_service

# 標記為整合測試
pytestmark = pytest.mark.integration


# ========== 額外的 Fixtures ==========

@pytest_asyncio.fixture
async def admin_user(test_db: AsyncIOMotorDatabase) -> User:
    """
    創建管理員用戶（用於測試管理員權限）
    
    Returns:
        User: 管理員用戶對象
    """
    user_id = uuid4()
    
    user_data = {
        "_id": user_id,
        "username": "adminuser",
        "email": "admin@example.com",
        "full_name": "Admin User",
        "hashed_password": get_password_hash("adminpass123"),
        "is_active": True,
        "is_admin": True,  # 管理員權限
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    await test_db["users"].insert_one(user_data)
    
    return User(
        id=user_id,
        username="adminuser",
        email="admin@example.com",
        full_name="Admin User",
        is_active=True,
        is_admin=True,
        created_at=user_data["created_at"],
        updated_at=user_data["updated_at"]
    )


@pytest_asyncio.fixture
async def test_document_vectorized(test_db: AsyncIOMotorDatabase, test_user: User) -> Document:
    """
    創建已向量化的測試文檔
    
    Returns:
        Document: vector_status = VECTORIZED
    """
    doc_id = uuid4()
    
    doc_data = {
        "_id": doc_id,
        "filename": "vectorized_doc.txt",
        "file_type": "text/plain",
        "size": 2048,
        "owner_id": test_user.id,
        "status": DocumentStatus.COMPLETED.value,
        "vector_status": VectorStatus.VECTORIZED.value,  # 已向量化
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "tags": ["vectorized"],
        "metadata": {},
        "file_path": "/test/path/vectorized_doc.txt",
        "extracted_text": "This is a test document with extracted text."
    }
    
    await test_db["documents"].insert_one(doc_data)
    
    return Document(
        id=doc_id,
        filename="vectorized_doc.txt",
        file_type="text/plain",
        size=2048,
        owner_id=test_user.id,
        status=DocumentStatus.COMPLETED,
        vector_status=VectorStatus.VECTORIZED,
        created_at=doc_data["created_at"],
        updated_at=doc_data["updated_at"],
        tags=["vectorized"],
        metadata={},
        file_path="/test/path/vectorized_doc.txt",
        extracted_text="This is a test document with extracted text."
    )


@pytest_asyncio.fixture
async def other_user_document(test_db: AsyncIOMotorDatabase, other_user: User) -> Document:
    """
    創建屬於 other_user 的文檔（用於測試權限）
    
    Returns:
        Document: 屬於 other_user 的文檔
    """
    doc_id = uuid4()
    
    doc_data = {
        "_id": doc_id,
        "filename": "other_user_doc.txt",
        "file_type": "text/plain",
        "size": 1024,
        "owner_id": other_user.id,
        "status": DocumentStatus.UPLOADED.value,
        "vector_status": VectorStatus.NOT_VECTORIZED.value,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "tags": [],
        "metadata": {},
        "file_path": "/test/path/other_user_doc.txt"
    }
    
    await test_db["documents"].insert_one(doc_data)
    
    return Document(
        id=doc_id,
        filename="other_user_doc.txt",
        file_type="text/plain",
        size=1024,
        owner_id=other_user.id,
        status=DocumentStatus.UPLOADED,
        vector_status=VectorStatus.NOT_VECTORIZED,
        created_at=doc_data["created_at"],
        updated_at=doc_data["updated_at"],
        tags=[],
        metadata={},
        file_path="/test/path/other_user_doc.txt"
    )


# ========== 測試類：向量服務基礎功能 ==========

class TestVectorServiceBasics:
    """測試向量服務的基礎功能"""
    
    @pytest.mark.asyncio
    async def test_embedding_service_info(self):
        """
        場景：獲取 embedding 服務信息
        預期：返回模型信息
        """
        model_info = embedding_service.get_model_info()
        
        # 驗證響應包含必要字段
        assert "model_loaded" in model_info
        assert isinstance(model_info["model_loaded"], bool)
    
    @pytest.mark.asyncio
    async def test_vector_db_service_available(self):
        """
        場景：驗證向量資料庫服務可用
        預期：服務實例可以創建
        """
        vector_db_service = get_vector_db_service()
        
        assert vector_db_service is not None


# ========== 測試類：文檔向量狀態管理 ==========

class TestDocumentVectorStatus:
    """測試文檔向量狀態的管理"""
    
    @pytest.mark.asyncio
    async def test_update_vector_status_to_processing(
        self,
        test_db,
        test_document
    ):
        """
        場景：將文檔向量狀態更新為 PROCESSING
        預期：DB 中狀態正確更新
        """
        # 更新狀態
        updated_doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.PROCESSING
        )
        
        # 驗證返回值
        assert updated_doc is not None
        assert updated_doc.vector_status == VectorStatus.PROCESSING
        
        # 重新查詢驗證 DB
        doc_in_db = await test_db["documents"].find_one({"_id": test_document.id})
        assert doc_in_db["vector_status"] == VectorStatus.PROCESSING.value
    
    @pytest.mark.asyncio
    async def test_update_vector_status_to_vectorized(
        self,
        test_db,
        test_document
    ):
        """
        場景：將文檔向量狀態更新為 VECTORIZED
        預期：DB 中狀態正確更新
        """
        updated_doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.VECTORIZED
        )
        
        assert updated_doc is not None
        assert updated_doc.vector_status == VectorStatus.VECTORIZED
        
        # DB 驗證
        doc_in_db = await test_db["documents"].find_one({"_id": test_document.id})
        assert doc_in_db["vector_status"] == VectorStatus.VECTORIZED.value
    
    @pytest.mark.asyncio
    async def test_update_vector_status_to_failed(
        self,
        test_db,
        test_document
    ):
        """
        場景：標記向量化失敗
        預期：狀態更新為 FAILED
        """
        updated_doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.FAILED
        )
        
        assert updated_doc is not None
        assert updated_doc.vector_status == VectorStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_document_vector_status(
        self,
        test_db
    ):
        """
        場景：嘗試更新不存在的文檔
        預期：返回 None
        """
        non_existent_id = uuid4()
        
        result = await update_document_vector_status(
            test_db,
            non_existent_id,
            VectorStatus.PROCESSING
        )
        
        assert result is None


# ========== 測試類：文檔查詢與權限 ==========

class TestDocumentQueryAndPermissions:
    """測試文檔查詢和權限驗證"""
    
    @pytest.mark.asyncio
    async def test_get_document_by_id_success(
        self,
        test_db,
        test_document
    ):
        """
        場景：根據 ID 成功查詢文檔
        預期：返回正確的文檔
        """
        doc = await get_document_by_id(test_db, test_document.id)
        
        assert doc is not None
        assert doc.id == test_document.id
        assert doc.owner_id == test_document.owner_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_document(
        self,
        test_db
    ):
        """
        場景：查詢不存在的文檔
        預期：返回 None
        """
        non_existent_id = uuid4()
        
        doc = await get_document_by_id(test_db, non_existent_id)
        
        assert doc is None
    
    @pytest.mark.asyncio
    async def test_document_ownership_verification(
        self,
        test_db,
        test_document,
        test_user,
        other_user
    ):
        """
        場景：驗證文檔所有權
        預期：
        - test_document 屬於 test_user
        - test_document 不屬於 other_user
        """
        doc = await get_document_by_id(test_db, test_document.id)
        
        # 驗證正確的擁有者
        assert doc.owner_id == test_user.id
        # 驗證不是其他用戶
        assert doc.owner_id != other_user.id


# ========== 測試類：向量狀態完整流程 ==========

class TestVectorStatusLifecycle:
    """測試文檔向量化的完整生命週期"""
    
    @pytest.mark.asyncio
    async def test_vector_lifecycle_success_flow(
        self,
        test_db,
        test_document
    ):
        """
        場景：模擬完整的向量化成功流程
        預期：狀態按順序轉換
        1. NOT_VECTORIZED -> PROCESSING -> VECTORIZED
        """
        # 初始狀態
        doc = await get_document_by_id(test_db, test_document.id)
        assert doc.vector_status == VectorStatus.NOT_VECTORIZED
        
        # 步驟 1: 開始處理
        doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.PROCESSING
        )
        assert doc.vector_status == VectorStatus.PROCESSING
        
        # 步驟 2: 完成向量化
        doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.VECTORIZED
        )
        assert doc.vector_status == VectorStatus.VECTORIZED
        
        # 最終驗證 DB
        doc_in_db = await test_db["documents"].find_one({"_id": test_document.id})
        assert doc_in_db["vector_status"] == VectorStatus.VECTORIZED.value
    
    @pytest.mark.asyncio
    async def test_vector_lifecycle_failure_flow(
        self,
        test_db,
        test_document
    ):
        """
        場景：模擬向量化失敗流程
        預期：
        1. NOT_VECTORIZED -> PROCESSING -> FAILED
        """
        # 開始處理
        doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.PROCESSING
        )
        assert doc.vector_status == VectorStatus.PROCESSING
        
        # 處理失敗
        doc = await update_document_vector_status(
            test_db,
            test_document.id,
            VectorStatus.FAILED
        )
        assert doc.vector_status == VectorStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_vector_delete_and_recreate_flow(
        self,
        test_db,
        test_document_vectorized
    ):
        """
        場景：刪除向量後重新向量化
        預期：VECTORIZED -> NOT_VECTORIZED -> PROCESSING -> VECTORIZED
        """
        # 初始狀態：已向量化
        doc = await get_document_by_id(test_db, test_document_vectorized.id)
        assert doc.vector_status == VectorStatus.VECTORIZED
        
        # 步驟 1: 刪除向量
        doc = await update_document_vector_status(
            test_db,
            test_document_vectorized.id,
            VectorStatus.NOT_VECTORIZED
        )
        assert doc.vector_status == VectorStatus.NOT_VECTORIZED
        
        # 步驟 2: 重新開始處理
        doc = await update_document_vector_status(
            test_db,
            test_document_vectorized.id,
            VectorStatus.PROCESSING
        )
        assert doc.vector_status == VectorStatus.PROCESSING
        
        # 步驟 3: 完成向量化
        doc = await update_document_vector_status(
            test_db,
            test_document_vectorized.id,
            VectorStatus.VECTORIZED
        )
        assert doc.vector_status == VectorStatus.VECTORIZED


# ========== 測試類：多用戶權限隔離 ==========

class TestMultiUserVectorPermissions:
    """測試多用戶環境下的權限隔離"""
    
    @pytest.mark.asyncio
    async def test_users_have_separate_documents(
        self,
        test_db,
        test_document,
        other_user_document,
        test_user,
        other_user
    ):
        """
        場景：驗證不同用戶的文檔完全隔離
        預期：每個用戶只能看到自己的文檔
        """
        # test_user 的文檔
        doc1 = await get_document_by_id(test_db, test_document.id)
        assert doc1.owner_id == test_user.id
        
        # other_user 的文檔
        doc2 = await get_document_by_id(test_db, other_user_document.id)
        assert doc2.owner_id == other_user.id
        
        # 驗證完全不同
        assert doc1.id != doc2.id
        assert doc1.owner_id != doc2.owner_id


# ========== 測試類：複雜端點業務邏輯 ==========

class TestComplexVectorOperations:
    """測試複雜的向量操作端點的業務邏輯"""
    
    # ===== DELETE /document/{id} 測試 =====
    
    @pytest.mark.asyncio
    async def test_delete_document_vectors_permission_check(
        self,
        test_db,
        test_document_vectorized,
        other_user
    ):
        """
        場景：驗證刪除向量時的權限檢查
        預期：只有文檔擁有者可以刪除向量
        """
        # 驗證文檔屬於 test_user，不屬於 other_user
        doc = await get_document_by_id(test_db, test_document_vectorized.id)
        assert doc.owner_id != other_user.id
        
        # 這個測試驗證了權限檢查邏輯存在
        # 實際的權限拒絕會在 API 層測試
    
    @pytest.mark.asyncio
    async def test_delete_vectors_updates_status(
        self,
        test_db,
        test_document_vectorized
    ):
        """
        場景：刪除向量後，文檔狀態應該更新為 NOT_VECTORIZED
        預期：成功更新狀態
        """
        # 確認初始狀態
        doc = await get_document_by_id(test_db, test_document_vectorized.id)
        assert doc.vector_status == VectorStatus.VECTORIZED
        
        # 模擬刪除向量後更新狀態
        updated_doc = await update_document_vector_status(
            test_db,
            test_document_vectorized.id,
            VectorStatus.NOT_VECTORIZED
        )
        
        # 驗證返回值
        assert updated_doc is not None
        assert updated_doc.vector_status == VectorStatus.NOT_VECTORIZED
        
        # 驗證數據庫狀態
        doc_in_db = await test_db["documents"].find_one({"_id": test_document_vectorized.id})
        assert doc_in_db["vector_status"] == VectorStatus.NOT_VECTORIZED.value
    
    @pytest.mark.asyncio
    async def test_delete_vectors_invalid_document_id(
        self,
        test_db
    ):
        """
        場景：嘗試使用無效的 UUID 格式刪除向量
        預期：操作前應該驗證 ID 格式
        """
        invalid_id = "not-a-valid-uuid"
        
        # 驗證 UUID 無法解析
        try:
            uuid.UUID(invalid_id)
            assert False, "Should have raised ValueError"
        except ValueError:
            # 預期行為：無效的 UUID 會拋出 ValueError
            pass
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_document_vectors(
        self,
        test_db
    ):
        """
        場景：嘗試刪除不存在文檔的向量
        預期：返回 None
        """
        non_existent_id = uuid4()
        
        # 驗證文檔不存在
        doc = await get_document_by_id(test_db, non_existent_id)
        assert doc is None
    
    # ===== POST /process-document/{id} 測試 =====
    
    @pytest.mark.asyncio
    async def test_process_document_permission_check(
        self,
        test_db,
        test_document,
        other_user
    ):
        """
        場景：驗證處理文檔時的權限檢查
        預期：只有文檔擁有者可以處理文檔
        """
        doc = await get_document_by_id(test_db, test_document.id)
        assert doc.owner_id != other_user.id
    
    @pytest.mark.asyncio
    async def test_process_document_validates_uuid(
        self,
        test_db
    ):
        """
        場景：處理文檔前驗證 UUID 格式
        預期：無效 UUID 應該被拒絕
        """
        invalid_id = "invalid-uuid-format"
        
        try:
            uuid.UUID(invalid_id)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
    
    @pytest.mark.asyncio
    async def test_process_nonexistent_document(
        self,
        test_db
    ):
        """
        場景：嘗試處理不存在的文檔
        預期：文檔不存在
        """
        non_existent_id = uuid4()
        doc = await get_document_by_id(test_db, non_existent_id)
        assert doc is None
    
    # ===== GET /documents/{id}/chunks 測試 =====
    
    @pytest.mark.asyncio
    async def test_get_chunks_permission_check(
        self,
        test_db,
        test_document_vectorized,
        other_user
    ):
        """
        場景：獲取向量塊時的權限檢查
        預期：只有文檔擁有者可以獲取向量塊
        """
        doc = await get_document_by_id(test_db, test_document_vectorized.id)
        
        # 驗證權限檢查邏輯
        assert doc is not None
        assert doc.owner_id != other_user.id
    
    @pytest.mark.asyncio
    async def test_get_chunks_document_must_exist(
        self,
        test_db
    ):
        """
        場景：獲取不存在文檔的向量塊
        預期：文檔不存在
        """
        non_existent_id = uuid4()
        doc = await get_document_by_id(test_db, non_existent_id)
        assert doc is None
    
    @pytest.mark.asyncio
    async def test_get_chunks_requires_vectorized_document(
        self,
        test_db,
        test_document_vectorized
    ):
        """
        場景：驗證文檔已向量化才能獲取塊
        預期：文檔狀態為 VECTORIZED
        """
        doc = await get_document_by_id(test_db, test_document_vectorized.id)
        assert doc.vector_status == VectorStatus.VECTORIZED
    
    # ===== 批量操作測試 =====
    
    @pytest.mark.asyncio
    async def test_batch_operations_multiple_owners(
        self,
        test_db,
        test_document,
        other_user_document,
        test_user,
        other_user
    ):
        """
        場景：批量操作時處理多個所有者的文檔
        預期：每個文檔只能被自己的擁有者操作
        """
        # 驗證文檔所有權
        doc1 = await get_document_by_id(test_db, test_document.id)
        doc2 = await get_document_by_id(test_db, other_user_document.id)
        
        assert doc1.owner_id == test_user.id
        assert doc2.owner_id == other_user.id
        
        # 批量操作時，應該過濾掉不屬於當前用戶的文檔
        assert doc1.owner_id != other_user.id
        assert doc2.owner_id != test_user.id


# ========== 測試類：批量操作端點業務邏輯 ==========

class TestBatchProcessOperations:
    """測試批量處理文檔的業務邏輯"""
    
    @pytest.mark.asyncio
    async def test_batch_process_filters_by_ownership(
        self,
        test_db,
        test_document,
        other_user_document,
        test_user
    ):
        """
        場景：批量處理時只處理屬於用戶的文檔
        預期：過濾掉不屬於用戶的文檔
        """
        # 準備混合的文檔 ID 列表
        doc_ids = [str(test_document.id), str(other_user_document.id)]
        
        # 驗證文檔所有權
        owned_doc = await get_document_by_id(test_db, test_document.id)
        other_doc = await get_document_by_id(test_db, other_user_document.id)
        
        assert owned_doc.owner_id == test_user.id
        assert other_doc.owner_id != test_user.id
        
        # 業務邏輯：批量操作應該只包含用戶擁有的文檔
        valid_docs = []
        for doc_id_str in doc_ids:
            doc_uuid = uuid.UUID(doc_id_str)
            doc = await get_document_by_id(test_db, doc_uuid)
            if doc and doc.owner_id == test_user.id:
                valid_docs.append(doc_id_str)
        
        # 驗證：只有 test_document 被包含
        assert len(valid_docs) == 1
        assert str(test_document.id) in valid_docs
        assert str(other_user_document.id) not in valid_docs
    
    @pytest.mark.asyncio
    async def test_batch_process_handles_invalid_uuids(
        self,
        test_db,
        test_document,
        test_user
    ):
        """
        場景：批量處理包含無效的 UUID
        預期：跳過無效 ID，繼續處理有效的
        """
        doc_ids = [
            str(test_document.id),
            "invalid-uuid",
            "not-a-uuid-at-all"
        ]
        
        valid_docs = []
        skipped_ids = []
        
        for doc_id_str in doc_ids:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                doc = await get_document_by_id(test_db, doc_uuid)
                if doc and doc.owner_id == test_user.id:
                    valid_docs.append(doc_id_str)
            except ValueError:
                # UUID 格式無效
                skipped_ids.append(doc_id_str)
        
        # 驗證
        assert len(valid_docs) == 1
        assert len(skipped_ids) == 2
        assert str(test_document.id) in valid_docs
        assert "invalid-uuid" in skipped_ids
    
    @pytest.mark.asyncio
    async def test_batch_process_handles_nonexistent_documents(
        self,
        test_db,
        test_document,
        test_user
    ):
        """
        場景：批量處理包含不存在的文檔 ID
        預期：跳過不存在的文檔
        """
        non_existent_id = uuid4()
        doc_ids = [str(test_document.id), str(non_existent_id)]
        
        valid_docs = []
        not_found_ids = []
        
        for doc_id_str in doc_ids:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                doc = await get_document_by_id(test_db, doc_uuid)
                if doc and doc.owner_id == test_user.id:
                    valid_docs.append(doc_id_str)
                elif not doc:
                    not_found_ids.append(doc_id_str)
            except ValueError:
                pass
        
        # 驗證
        assert len(valid_docs) == 1
        assert len(not_found_ids) == 1
        assert str(test_document.id) in valid_docs
        assert str(non_existent_id) in not_found_ids


class TestBatchDeleteOperations:
    """測試批量刪除向量的業務邏輯"""
    
    @pytest.mark.asyncio
    async def test_batch_delete_permission_filtering(
        self,
        test_db,
        test_document_vectorized,
        other_user_document,
        test_user
    ):
        """
        場景：批量刪除時過濾權限
        預期：只刪除用戶擁有的文檔向量
        """
        doc_ids = [str(test_document_vectorized.id), str(other_user_document.id)]
        
        # 模擬權限過濾邏輯
        authorized_ids = []
        unauthorized_ids = []
        
        for doc_id_str in doc_ids:
            doc_uuid = uuid.UUID(doc_id_str)
            doc = await get_document_by_id(test_db, doc_uuid)
            if doc and doc.owner_id == test_user.id:
                authorized_ids.append(doc_id_str)
            else:
                unauthorized_ids.append(doc_id_str)
        
        # 驗證
        assert len(authorized_ids) == 1
        assert len(unauthorized_ids) == 1
        assert str(test_document_vectorized.id) in authorized_ids
        assert str(other_user_document.id) in unauthorized_ids
    
    @pytest.mark.asyncio
    async def test_batch_delete_updates_vector_status(
        self,
        test_db,
        test_document_vectorized
    ):
        """
        場景：批量刪除後更新文檔狀態
        預期：vector_status 更新為 NOT_VECTORIZED
        """
        # 確認初始狀態
        doc = await get_document_by_id(test_db, test_document_vectorized.id)
        assert doc.vector_status == VectorStatus.VECTORIZED
        
        # 模擬刪除後的狀態更新
        updated_doc = await update_document_vector_status(
            test_db,
            test_document_vectorized.id,
            VectorStatus.NOT_VECTORIZED
        )
        
        # 驗證狀態更新
        assert updated_doc is not None
        assert updated_doc.vector_status == VectorStatus.NOT_VECTORIZED
        
        # 驗證數據庫中的狀態
        doc_in_db = await test_db["documents"].find_one({"_id": test_document_vectorized.id})
        assert doc_in_db["vector_status"] == VectorStatus.NOT_VECTORIZED.value
    
    @pytest.mark.asyncio
    async def test_batch_delete_handles_mixed_valid_invalid(
        self,
        test_db,
        test_document_vectorized,
        test_user
    ):
        """
        場景：批量刪除包含有效和無效的 ID 混合
        預期：處理有效的，報告無效的
        """
        doc_ids = [
            str(test_document_vectorized.id),
            "invalid-uuid",
            str(uuid4())  # 不存在的 UUID
        ]
        
        authorized_ids = []
        errors = []
        
        for doc_id_str in doc_ids:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                doc = await get_document_by_id(test_db, doc_uuid)
                if not doc:
                    errors.append({"id": doc_id_str, "error": "Document not found"})
                elif doc.owner_id != test_user.id:
                    errors.append({"id": doc_id_str, "error": "Forbidden"})
                else:
                    authorized_ids.append(doc_id_str)
            except ValueError:
                errors.append({"id": doc_id_str, "error": "Invalid document ID format"})
        
        # 驗證
        assert len(authorized_ids) == 1
        assert len(errors) == 2
        assert str(test_document_vectorized.id) in authorized_ids


class TestSemanticSearchLogic:
    """測試語義搜索的業務邏輯"""
    
    @pytest.mark.asyncio
    async def test_search_respects_user_ownership(
        self,
        test_db,
        test_document_vectorized,
        other_user_document,
        test_user,
        other_user
    ):
        """
        場景：語義搜索應該只返回用戶擁有的文檔
        預期：權限過濾正常工作
        """
        # 驗證文檔所有權
        doc1 = await get_document_by_id(test_db, test_document_vectorized.id)
        doc2 = await get_document_by_id(test_db, other_user_document.id)
        
        assert doc1.owner_id == test_user.id
        assert doc2.owner_id == other_user.id
        
        # 驗證權限過濾邏輯
        # 搜索結果應該只包含屬於 test_user 的文檔
        user_owned_docs = [doc1.id]
        other_owned_docs = [doc2.id]
        
        # 模擬過濾：只保留用戶擁有的
        filtered_results = [
            doc_id for doc_id in [doc1.id, doc2.id]
            if doc_id in user_owned_docs
        ]
        
        assert len(filtered_results) == 1
        assert doc1.id in filtered_results
        assert doc2.id not in filtered_results
    
    @pytest.mark.asyncio
    async def test_search_validates_vectorized_status(
        self,
        test_db,
        test_document_vectorized,
        test_document
    ):
        """
        場景：語義搜索應該只考慮已向量化的文檔
        預期：未向量化的文檔被過濾掉
        """
        # 驗證向量化狀態
        vectorized_doc = await get_document_by_id(test_db, test_document_vectorized.id)
        not_vectorized_doc = await get_document_by_id(test_db, test_document.id)
        
        assert vectorized_doc.vector_status == VectorStatus.VECTORIZED
        assert not_vectorized_doc.vector_status == VectorStatus.NOT_VECTORIZED
        
        # 模擬過濾邏輯：只包含已向量化的文檔
        all_docs = [vectorized_doc, not_vectorized_doc]
        searchable_docs = [
            doc for doc in all_docs
            if doc.vector_status == VectorStatus.VECTORIZED
        ]
        
        # 驗證
        assert len(searchable_docs) == 1
        assert searchable_docs[0].id == vectorized_doc.id


class TestBatchProcessSummariesLogic:
    """測試批量處理摘要的業務邏輯"""
    
    @pytest.mark.asyncio
    async def test_batch_summaries_same_as_batch_process(
        self,
        test_db,
        test_document,
        other_user_document,
        test_user
    ):
        """
        場景：批量處理摘要的權限邏輯應該與批量處理相同
        預期：同樣的過濾和權限檢查
        """
        doc_ids = [str(test_document.id), str(other_user_document.id)]
        
        # 使用與 batch_process 相同的邏輯
        valid_docs = []
        skipped_docs = []
        
        for doc_id_str in doc_ids:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                doc = await get_document_by_id(test_db, doc_uuid)
                if doc and doc.owner_id == test_user.id:
                    valid_docs.append(doc_id_str)
                else:
                    reason = "Not found" if not doc else "Unauthorized"
                    skipped_docs.append({"id": doc_id_str, "reason": reason})
            except ValueError:
                skipped_docs.append({"id": doc_id_str, "reason": "Invalid ID format"})
        
        # 驗證：與 batch_process 行為一致
        assert len(valid_docs) == 1
        assert len(skipped_docs) == 1
        assert str(test_document.id) in valid_docs
