"""
單元測試配置

單元測試使用 mock，不依賴外部資源（數據庫、網絡等）。
專注於測試單個函數或類的邏輯。
"""

import pytest
from unittest.mock import Mock, AsyncMock
from uuid import UUID, uuid4


# 可以添加單元測試專用的 fixtures
@pytest.fixture
def mock_db():
    """
    模擬數據庫連接
    
    用於單元測試，不連接真實數據庫
    """
    return Mock()


@pytest.fixture
def mock_user():
    """
    模擬用戶對象
    
    用於測試權限檢查等功能
    """
    user = Mock()
    user.id = uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def mock_resource():
    """
    模擬資源對象（如 Document、Conversation）
    
    用於測試所有權檢查等功能
    """
    resource = Mock()
    resource.id = uuid4()
    resource.owner_id = uuid4()
    return resource
