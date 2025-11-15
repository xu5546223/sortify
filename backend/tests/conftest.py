"""
全局測試配置

定義全局的 pytest 配置和通用 fixtures。
"""

import pytest
from uuid import UUID


def pytest_configure(config):
    """
    Pytest 配置鉤子 - 註冊自定義標記
    """
    # 註冊測試標記
    config.addinivalue_line(
        "markers",
        "unit: 單元測試，使用 mock，不依賴外部資源"
    )
    config.addinivalue_line(
        "markers",
        "integration: 整合測試，使用真實數據庫，測試完整流程"
    )


# 通用 fixtures（所有測試都可用）

@pytest.fixture
def fixed_uuid():
    """固定的 UUID 用於測試（可預測）"""
    return UUID('12345678-1234-5678-1234-567812345678')


@pytest.fixture
def another_fixed_uuid():
    """另一個固定的 UUID 用於測試"""
    return UUID('87654321-4321-8765-4321-876543218765')
