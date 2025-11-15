"""
測試 resource_helpers 工具函數

這個測試文件驗證資源獲取和驗證函數的正確性。
使用 pytest-asyncio 測試異步函數，使用 mock 模擬數據庫操作。
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.core.resource_helpers import (
    get_resource_or_404,
    get_owned_resource_or_404,
    validate_resource_exists
)

# 标记为单元测试
pytestmark = pytest.mark.unit


# ========== Mock 類定義 ==========

class MockUser:
    """模擬用戶對象"""
    def __init__(self, user_id: UUID):
        self.id = user_id


class MockDocument:
    """模擬文檔資源"""
    def __init__(self, doc_id: UUID, owner_id: UUID, title: str = "Test Doc"):
        self.id = doc_id
        self.owner_id = owner_id
        self.title = title


# ========== 測試 get_resource_or_404 ==========

@pytest.mark.asyncio
async def test_get_resource_or_404_success():
    """測試成功獲取資源的情況"""
    resource_id = uuid4()
    expected_doc = MockDocument(resource_id, uuid4())
    
    # 模擬 getter 函數（返回資源）
    mock_getter = AsyncMock(return_value=expected_doc)
    mock_db = MagicMock()
    
    # 執行測試
    result = await get_resource_or_404(
        getter_func=mock_getter,
        db=mock_db,
        resource_id=resource_id,
        resource_type="Document"
    )
    
    # 驗證
    assert result == expected_doc
    mock_getter.assert_called_once_with(mock_db, resource_id)


@pytest.mark.asyncio
async def test_get_resource_or_404_not_found():
    """測試資源不存在的情況（應拋出 404）"""
    resource_id = uuid4()
    
    # 模擬 getter 函數（返回 None）
    mock_getter = AsyncMock(return_value=None)
    mock_db = MagicMock()
    
    # 執行測試並驗證異常
    with pytest.raises(HTTPException) as exc_info:
        await get_resource_or_404(
            getter_func=mock_getter,
            db=mock_db,
            resource_id=resource_id,
            resource_type="Document"
        )
    
    # 驗證異常狀態碼和消息
    assert exc_info.value.status_code == 404
    assert "Document" in str(exc_info.value.detail)
    assert str(resource_id) in str(exc_info.value.detail)


# ========== 測試 get_owned_resource_or_404 ==========

@pytest.mark.asyncio
async def test_get_owned_resource_or_404_success():
    """測試成功獲取自己擁有的資源"""
    user_id = uuid4()
    resource_id = uuid4()
    
    user = MockUser(user_id)
    document = MockDocument(resource_id, user_id)
    
    # 模擬 getter 函數
    mock_getter = AsyncMock(return_value=document)
    mock_db = MagicMock()
    
    # 執行測試
    result = await get_owned_resource_or_404(
        getter_func=mock_getter,
        db=mock_db,
        resource_id=resource_id,
        current_user=user,
        resource_type="Document"
    )
    
    # 驗證
    assert result == document
    mock_getter.assert_called_once_with(mock_db, resource_id)


@pytest.mark.asyncio
async def test_get_owned_resource_or_404_not_found():
    """測試資源不存在的情況（應拋出 404）"""
    user_id = uuid4()
    resource_id = uuid4()
    
    user = MockUser(user_id)
    
    # 模擬 getter 函數（返回 None）
    mock_getter = AsyncMock(return_value=None)
    mock_db = MagicMock()
    
    # 執行測試並驗證異常
    with pytest.raises(HTTPException) as exc_info:
        await get_owned_resource_or_404(
            getter_func=mock_getter,
            db=mock_db,
            resource_id=resource_id,
            current_user=user,
            resource_type="Document"
        )
    
    # 驗證是 404 錯誤
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_owned_resource_or_404_permission_denied():
    """測試訪問別人的資源（應拋出 403）"""
    owner_id = uuid4()
    other_user_id = uuid4()
    resource_id = uuid4()
    
    user = MockUser(other_user_id)
    document = MockDocument(resource_id, owner_id)  # 文檔屬於別人
    
    # 模擬 getter 函數（返回資源）
    mock_getter = AsyncMock(return_value=document)
    mock_db = MagicMock()
    
    # 執行測試並驗證異常
    with pytest.raises(HTTPException) as exc_info:
        await get_owned_resource_or_404(
            getter_func=mock_getter,
            db=mock_db,
            resource_id=resource_id,
            current_user=user,
            resource_type="Document"
        )
    
    # 驗證是 403 錯誤
    assert exc_info.value.status_code == 403
    assert "permission" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_get_owned_resource_or_404_custom_owner_field():
    """測試使用自定義的 owner_field"""
    user_id = uuid4()
    resource_id = uuid4()
    
    # 創建一個使用不同字段名的資源
    class MockCustomResource:
        def __init__(self, res_id: UUID, creator_id: UUID):
            self.id = res_id
            self.creator_id = creator_id  # 使用 creator_id 而不是 owner_id
    
    user = MockUser(user_id)
    resource = MockCustomResource(resource_id, user_id)
    
    # 模擬 getter 函數
    mock_getter = AsyncMock(return_value=resource)
    mock_db = MagicMock()
    
    # 執行測試，指定自定義的 owner_field
    result = await get_owned_resource_or_404(
        getter_func=mock_getter,
        db=mock_db,
        resource_id=resource_id,
        current_user=user,
        resource_type="CustomResource",
        owner_field="creator_id"
    )
    
    # 驗證
    assert result == resource


# ========== 測試 validate_resource_exists ==========

def test_validate_resource_exists_success():
    """測試驗證資源存在（資源不為 None）"""
    resource = MockDocument(uuid4(), uuid4())
    
    # 應該返回原資源，不拋出異常
    result = validate_resource_exists(resource, "Document")
    
    assert result == resource


def test_validate_resource_exists_not_found():
    """測試驗證資源不存在（資源為 None）"""
    # 執行測試並驗證異常
    with pytest.raises(HTTPException) as exc_info:
        validate_resource_exists(None, "Document")
    
    # 驗證異常
    assert exc_info.value.status_code == 404
    assert "Document not found" in str(exc_info.value.detail)


def test_validate_resource_exists_with_resource_id():
    """測試驗證資源不存在時包含資源 ID"""
    resource_id = str(uuid4())
    
    # 執行測試並驗證異常
    with pytest.raises(HTTPException) as exc_info:
        validate_resource_exists(None, "Document", resource_id)
    
    # 驗證異常消息包含 ID
    assert exc_info.value.status_code == 404
    assert resource_id in str(exc_info.value.detail)


# ========== 集成測試示例 ==========

@pytest.mark.asyncio
async def test_typical_usage_pattern():
    """測試典型使用模式：先獲取資源，再檢查權限"""
    user_id = uuid4()
    resource_id = uuid4()
    
    user = MockUser(user_id)
    document = MockDocument(resource_id, user_id, "My Document")
    
    # 模擬 CRUD 操作
    async def mock_get_document(db, doc_id):
        """模擬 crud_documents.get_document_by_id"""
        if doc_id == resource_id:
            return document
        return None
    
    mock_db = MagicMock()
    
    # 使用 get_owned_resource_or_404 獲取並驗證權限
    result = await get_owned_resource_or_404(
        getter_func=mock_get_document,
        db=mock_db,
        resource_id=resource_id,
        current_user=user,
        resource_type="Document"
    )
    
    # 驗證結果
    assert result.id == resource_id
    assert result.owner_id == user_id
    assert result.title == "My Document"


@pytest.mark.asyncio
async def test_error_propagation():
    """測試數據庫錯誤是否正確傳播"""
    
    # 模擬 getter 函數拋出數據庫錯誤
    async def mock_getter_with_error(db, resource_id):
        raise Exception("Database connection error")
    
    mock_db = MagicMock()
    resource_id = uuid4()
    
    # 驗證異常被正確傳播（不被捕獲）
    with pytest.raises(Exception) as exc_info:
        await get_resource_or_404(
            getter_func=mock_getter_with_error,
            db=mock_db,
            resource_id=resource_id,
            resource_type="Document"
        )
    
    assert "Database connection error" in str(exc_info.value)


# ========== 邊界情況測試 ==========

@pytest.mark.asyncio
async def test_get_owned_resource_with_none_user():
    """測試當 current_user 為 None 時的行為"""
    resource_id = uuid4()
    document = MockDocument(resource_id, uuid4())
    
    mock_getter = AsyncMock(return_value=document)
    mock_db = MagicMock()
    
    # 當 user 為 None 時應該拋出錯誤
    # 這取決於 ownership_checker 的實現
    # 如果需要，可以在這裡添加相應的測試


@pytest.mark.asyncio
async def test_multiple_sequential_calls():
    """測試連續多次調用是否正常工作"""
    user_id = uuid4()
    user = MockUser(user_id)
    
    # 創建多個文檔
    docs = [MockDocument(uuid4(), user_id, f"Doc {i}") for i in range(3)]
    
    async def mock_get_document(db, doc_id):
        for doc in docs:
            if doc.id == doc_id:
                return doc
        return None
    
    mock_db = MagicMock()
    
    # 連續獲取多個文檔
    results = []
    for doc in docs:
        result = await get_owned_resource_or_404(
            getter_func=mock_get_document,
            db=mock_db,
            resource_id=doc.id,
            current_user=user,
            resource_type="Document"
        )
        results.append(result)
    
    # 驗證所有文檔都正確獲取
    assert len(results) == 3
    assert all(r.owner_id == user_id for r in results)
