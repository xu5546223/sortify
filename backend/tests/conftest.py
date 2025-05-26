pytest_plugins = "pytest_asyncio" # 明確註冊 pytest-asyncio 插件

import pytest
import pytest_asyncio
import asyncio
from fastapi.testclient import TestClient
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

from motor.motor_asyncio import AsyncIOMotorDatabase

# 由於測試的執行路徑問題，我們可能需要調整導入路徑
# 假設 tests 目錄與 app 目錄同級
import sys
import os

# 將 backend 目錄添加到 sys.path
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# 如果 conftest.py 在 tests/ 內部，而 app 在 backend/app，則需要回退兩級到 backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from app.main import app  # 從您的應用程式導入 app
from app.dependencies import get_db # 導入 get_db 依賴

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """為 pytest-asyncio 創建一個事件循環，使其在整個測試會話中可用。"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def mock_db_session() -> AsyncMock:
    """創建一個 AsyncMock 來模擬 AsyncIOMotorDatabase。"""
    mock_db = AsyncMock(spec=AsyncIOMotorDatabase)
    # 如果您的 CRUD 操作直接在 db 物件上調用集合 (例如 db["collection_name"])
    # 您可能需要更細緻地模擬這個行為，例如:
    mock_db.__getitem__.return_value = AsyncMock() # 返回一個模擬的集合物件
    return mock_db

@pytest.fixture
def client(mock_db_session: AsyncMock) -> TestClient:
    """創建一個同步的 FastAPI TestClient，並覆蓋 get_db 依賴以使用 mock_db_session。"""
    
    async def override_get_db():
        return mock_db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # 創建同步的 TestClient
    test_client = TestClient(app)
    
    yield test_client
    
    # 清理，移除依賴覆蓋
    app.dependency_overrides.clear()

# 如果某些 CRUD 模組是直接導入並在 API 函數中調用的，
# 我們可能還需要模擬這些 CRUD 模組本身。
# 例如，如果 app.apis.v1.system 直接導入了 crud_settings

@pytest.fixture
def mock_crud_settings() -> MagicMock:
    mock = MagicMock()
    # 根據需要模擬 crud_settings 中的方法
    # 例如: mock.get_system_settings = AsyncMock(return_value={...})
    return mock

@pytest.fixture
def mock_crud_users() -> MagicMock:
    mock = MagicMock()
    # 根據需要模擬 crud_users 中的方法
    # 例如: mock.create_or_update = AsyncMock(return_value=ConnectedDevice(...))
    return mock 