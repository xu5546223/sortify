"""
測試 OwnershipChecker 工具類

這個測試文件驗證新創建的工具類功能正常。
"""

import pytest
from uuid import uuid4, UUID
from fastapi import HTTPException
from app.core.ownership_checker import OwnershipChecker

# 标记为单元测试
pytestmark = pytest.mark.unit


class MockUser:
    """模擬用戶對象"""
    def __init__(self, user_id: UUID):
        self.id = user_id


class MockResource:
    """模擬資源對象"""
    def __init__(self, resource_id: UUID, owner_id: UUID):
        self.id = resource_id
        self.owner_id = owner_id


def test_check_ownership_success():
    """測試所有權檢查通過的情況"""
    user_id = uuid4()
    
    # 應該不拋出異常
    OwnershipChecker.check_ownership(
        resource_owner_id=user_id,
        current_user_id=user_id,
        resource_type="Document"
    )


def test_check_ownership_failure():
    """測試所有權檢查失敗的情況"""
    owner_id = uuid4()
    other_user_id = uuid4()
    
    # 應該拋出 403 異常
    with pytest.raises(HTTPException) as exc_info:
        OwnershipChecker.check_ownership(
            resource_owner_id=owner_id,
            current_user_id=other_user_id,
            resource_type="Document"
        )
    
    assert exc_info.value.status_code == 403
    assert "permission" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_require_ownership_success():
    """測試 require_ownership 成功的情況"""
    user_id = uuid4()
    resource = MockResource(uuid4(), user_id)
    user = MockUser(user_id)
    
    # 應該不拋出異常
    await OwnershipChecker.require_ownership(
        resource=resource,
        current_user=user,
        resource_type="Document"
    )


@pytest.mark.asyncio
async def test_require_ownership_not_found():
    """測試資源不存在的情況"""
    user = MockUser(uuid4())
    
    # 資源為 None，應該拋出 404
    with pytest.raises(HTTPException) as exc_info:
        await OwnershipChecker.require_ownership(
            resource=None,
            current_user=user,
            resource_type="Document"
        )
    
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_require_ownership_permission_denied():
    """測試 require_ownership 當用戶不是所有者時拋出 403"""
    owner_id = uuid4()
    other_user_id = uuid4()
    
    resource = MockResource(uuid4(), owner_id)
    user = MockUser(other_user_id)
    
    # 應該拋出 403 異常
    with pytest.raises(HTTPException) as exc_info:
        await OwnershipChecker.require_ownership(
            resource=resource,
            current_user=user,
            resource_type="Document"
        )
    
    assert exc_info.value.status_code == 403
    assert "permission" in str(exc_info.value.detail).lower()


def test_is_owner_true():
    """測試 is_owner 返回 True 的情況"""
    user_id = uuid4()
    resource_id = uuid4()
    
    user = MockUser(user_id)
    resource = MockResource(resource_id, user_id)
    
    assert OwnershipChecker.is_owner(resource, user) is True


def test_is_owner_false():
    """測試 is_owner 返回 False 的情況"""
    owner_id = uuid4()
    other_user_id = uuid4()
    resource_id = uuid4()
    
    user = MockUser(other_user_id)
    resource = MockResource(resource_id, owner_id)
    
    assert OwnershipChecker.is_owner(resource, user) is False


def test_is_owner_none_resource():
    """測試資源為 None 的情況"""
    user = MockUser(uuid4())
    
    assert OwnershipChecker.is_owner(None, user) is False


def test_is_owner_none_user():
    """測試用戶為 None 的情況"""
    resource = MockResource(uuid4(), uuid4())
    
    assert OwnershipChecker.is_owner(resource, None) is False
