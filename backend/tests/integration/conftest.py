"""
集成测试配置

使用真实的测试数据库，测试完整的业务流程。
"""

import pytest
import pytest_asyncio
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from uuid import uuid4
from datetime import datetime, UTC
from typing import AsyncGenerator
from pymongo import MongoClient
from bson.codec_options import CodecOptions
from bson.binary import UuidRepresentation

# 设置测试环境变量
os.environ["TESTING"] = "1"

from app.core.config import settings
from app.crud import crud_users, crud_documents, crud_conversations
from app.models.user_models import UserCreate, User
from app.models.document_models import Document, DocumentCreate, DocumentStatus
from app.models.conversation_models import ConversationInDB, ConversationMessage
from app.core.password_utils import get_password_hash

# 使用独立的测试数据库
TEST_DB_NAME = "sortify_test_db"
TEST_MONGODB_URL = os.getenv("TEST_MONGODB_URL", "mongodb://localhost:27017")


@pytest.fixture(scope="function")
def event_loop():
    """
    创建事件循环用于每个测试函数
    
    scope="function" 确保每个测试都有独立的事件循环
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db_client():
    """
    创建测试数据库客户端（每个测试独立）
    
    配置 UUID 表示方式为 STANDARD，支持原生 UUID 对象
    改为 function scope 避免事件循环关闭问题
    """
    client = AsyncIOMotorClient(
        TEST_MONGODB_URL,
        uuidRepresentation='standard'  # 支持原生 UUID
    )
    yield client
    client.close()


@pytest_asyncio.fixture
async def test_db(test_db_client) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """
    提供干净的测试数据库（每个测试独立）
    
    每个测试前清空数据，确保测试隔离。
    配置 UUID 支持。
    """
    # 获取数据库并配置 UUID 编码选项
    db = test_db_client[TEST_DB_NAME]
    
    # 配置集合以支持原生 UUID
    codec_options = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)
    
    # 清空所有测试集合
    collections = await db.list_collection_names()
    for collection_name in collections:
        await db[collection_name].delete_many({})
    
    yield db
    
    # 测试后清理（可选，因为下次测试前也会清理）
    collections = await db.list_collection_names()
    for collection_name in collections:
        await db[collection_name].delete_many({})


@pytest_asyncio.fixture
async def test_user(test_db: AsyncIOMotorDatabase) -> User:
    """
    创建测试用户（真实写入数据库）
    
    Returns:
        User: 测试用户对象，包含 id、username、email 等
    """
    user_id = uuid4()
    
    # 直接插入用户数据（避免依赖 crud 复杂逻辑）
    # 注意：MongoDB 不支持原生 UUID，需要转换
    user_data = {
        "_id": user_id,  # MongoDB 会自动处理 UUID
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "hashed_password": get_password_hash("testpass123"),
        "is_active": True,
        "is_admin": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    await test_db["users"].insert_one(user_data)
    
    # 返回 User 对象
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        is_active=True,
        is_admin=False,
        created_at=user_data["created_at"],
        updated_at=user_data["updated_at"]
    )


@pytest_asyncio.fixture
async def other_user(test_db: AsyncIOMotorDatabase) -> User:
    """
    创建另一个测试用户（用于测试权限）
    
    Returns:
        User: 另一个测试用户
    """
    user_id = uuid4()
    
    user_data = {
        "_id": user_id,  # MongoDB 会自动处理 UUID
        "username": "otheruser",
        "email": "other@example.com",
        "full_name": "Other User",
        "hashed_password": get_password_hash("otherpass123"),
        "is_active": True,
        "is_admin": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    await test_db["users"].insert_one(user_data)
    
    return User(
        id=user_id,
        username="otheruser",
        email="other@example.com",
        full_name="Other User",
        is_active=True,
        is_admin=False,
        created_at=user_data["created_at"],
        updated_at=user_data["updated_at"]
    )


@pytest_asyncio.fixture
async def test_document(test_db: AsyncIOMotorDatabase, test_user: User) -> Document:
    """
    创建测试文档（真实写入数据库）
    
    Returns:
        Document: 属于 test_user 的测试文档
    """
    doc_id = uuid4()
    
    doc_data = {
        "_id": doc_id,  # MongoDB 会自动处理 UUID
        "filename": "test_document.txt",
        "file_type": "text/plain",
        "size": 1024,
        "owner_id": test_user.id,  # UUID 对象
        "status": DocumentStatus.UPLOADED.value,
        "vector_status": "not_vectorized",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "tags": ["test", "integration"],
        "metadata": {},
        "file_path": "/test/path/test_document.txt"
    }
    
    await test_db["documents"].insert_one(doc_data)
    
    return Document(
        id=doc_id,
        filename="test_document.txt",
        file_type="text/plain",
        size=1024,
        owner_id=test_user.id,
        status=DocumentStatus.UPLOADED,
        created_at=doc_data["created_at"],
        updated_at=doc_data["updated_at"],
        tags=["test", "integration"],
        metadata={},
        file_path="/test/path/test_document.txt"
    )


@pytest.fixture
def test_upload_dir(tmp_path):
    """
    创建临时上传目录
    
    使用 pytest 的 tmp_path fixture，自动清理。
    """
    upload_dir = tmp_path / "test_uploads"
    upload_dir.mkdir(exist_ok=True)
    return upload_dir


@pytest_asyncio.fixture
async def test_conversation(test_db: AsyncIOMotorDatabase, test_user: User) -> ConversationInDB:
    """
    创建测试对话（真实写入数据库）
    
    Returns:
        ConversationInDB: 属于 test_user 的测试对话
    """
    conversation_id = uuid4()
    
    # 创建初始消息
    initial_message = ConversationMessage(
        role="user",
        content="這是一個測試問題",
        timestamp=datetime.now(UTC),
        tokens_used=50
    )
    
    conversation_data = {
        "_id": conversation_id,
        "title": "測試對話",
        "user_id": test_user.id,
        "messages": [initial_message.model_dump()],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "message_count": 1,
        "total_tokens": 50,
        "cached_documents": [],
        "cached_document_data": None
    }
    
    await test_db["conversations"].insert_one(conversation_data)
    
    return ConversationInDB(
        id=conversation_id,
        title="測試對話",
        user_id=test_user.id,
        messages=[initial_message],
        created_at=conversation_data["created_at"],
        updated_at=conversation_data["updated_at"],
        message_count=1,
        total_tokens=50,
        cached_documents=[],
        cached_document_data=None
    )


@pytest_asyncio.fixture
async def test_conversation_with_messages(test_db: AsyncIOMotorDatabase, test_user: User) -> ConversationInDB:
    """
    创建包含多条消息的测试对话
    
    Returns:
        ConversationInDB: 包含多条消息的测试对话
    """
    conversation_id = uuid4()
    
    # 创建多条消息
    messages = [
        ConversationMessage(
            role="user",
            content="第一個問題",
            timestamp=datetime.now(UTC),
            tokens_used=30
        ),
        ConversationMessage(
            role="assistant",
            content="第一個回答",
            timestamp=datetime.now(UTC),
            tokens_used=100
        ),
        ConversationMessage(
            role="user",
            content="第二個問題",
            timestamp=datetime.now(UTC),
            tokens_used=40
        ),
        ConversationMessage(
            role="assistant",
            content="第二個回答",
            timestamp=datetime.now(UTC),
            tokens_used=120
        )
    ]
    
    conversation_data = {
        "_id": conversation_id,
        "title": "多消息測試對話",
        "user_id": test_user.id,
        "messages": [msg.model_dump() for msg in messages],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "message_count": len(messages),
        "total_tokens": sum(msg.tokens_used or 0 for msg in messages),
        "cached_documents": [],
        "cached_document_data": None
    }
    
    await test_db["conversations"].insert_one(conversation_data)
    
    return ConversationInDB(
        id=conversation_id,
        title="多消息測試對話",
        user_id=test_user.id,
        messages=messages,
        created_at=conversation_data["created_at"],
        updated_at=conversation_data["updated_at"],
        message_count=len(messages),
        total_tokens=conversation_data["total_tokens"],
        cached_documents=[],
        cached_document_data=None
    )
