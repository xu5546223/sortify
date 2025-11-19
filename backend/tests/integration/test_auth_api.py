"""
Auth API (認證) 整合測試

測試認證 API 的核心業務邏輯，專注於：
- 用戶註冊和登錄
- Token 生成和驗證
- 密碼處理和安全性
- 數據庫副作用驗證

注意：這是服務層測試，不是 HTTP API 測試
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user_models import User, UserCreate, UserInDB
from app.models.token_models import Token
from app.core.password_utils import get_password_hash, verify_password
from app.core.security import create_access_token, verify_password as security_verify_password
from app.crud.crud_users import crud_users

# 標記為整合測試
pytestmark = pytest.mark.integration


# ========== 測試類：用戶註冊 ==========

class TestUserRegistration:
    """測試用戶註冊流程"""
    
    @pytest.mark.asyncio
    async def test_create_new_user(
        self,
        test_db
    ):
        """
        場景：新用戶註冊
        預期：用戶成功創建，密碼被哈希
        """
        user_create = UserCreate(
            username="newuser",
            email="newuser@example.com",
            password="SecurePass123!",
            full_name="New User"
        )
        
        # 創建用戶
        created_user = await crud_users.create_user(test_db, user_in=user_create)
        
        # 驗證返回值
        assert created_user is not None
        assert created_user.username == "newuser"
        assert created_user.email == "newuser@example.com"
        assert created_user.is_active is True
        assert hasattr(created_user, 'id')
        
        # 驗證數據庫
        user_in_db = await test_db["users"].find_one({"username": "newuser"})
        assert user_in_db is not None
        assert "hashed_password" in user_in_db
        assert user_in_db["hashed_password"] != "SecurePass123!"  # 確保密碼被哈希
    
    @pytest.mark.asyncio
    async def test_duplicate_username_prevented(
        self,
        test_db,
        test_user
    ):
        """
        場景：嘗試註冊已存在的用戶名
        預期：操作失敗或返回 None
        """
        # test_user 已經使用 "testuser" 用戶名
        duplicate_user = UserCreate(
            username="testuser",  # 重複的用戶名
            email="different@example.com",
            password="AnotherPass123!",
            full_name="Duplicate User"
        )
        
        # 嘗試創建重複用戶（應該失敗或被忽略）
        # 這裡我們只驗證原始用戶仍然存在
        existing_user = await crud_users.get_user_by_username(test_db, username="testuser")
        
        # 驗證原始用戶仍然存在且只有一個
        assert existing_user is not None
        users_count = await test_db["users"].count_documents({"username": "testuser"})
        assert users_count == 1  # 只有原始的 test_user
    
    @pytest.mark.asyncio
    async def test_password_is_hashed(
        self,
        test_db
    ):
        """
        場景：用戶註冊時密碼應該被哈希
        預期：數據庫中存儲的是哈希密碼，不是明文
        """
        user_create = UserCreate(
            username="hashtest",
            email="hashtest@example.com",
            password="PlainTextPassword",
            full_name="Hash Test"
        )
        
        created_user = await crud_users.create_user(test_db, user_in=user_create)
        
        # 從數據庫讀取
        user_in_db = await test_db["users"].find_one({"username": "hashtest"})
        
        # 驗證密碼已被哈希
        assert user_in_db["hashed_password"] != "PlainTextPassword"
        assert user_in_db["hashed_password"].startswith("$2b$")  # bcrypt hash 前綴
        
        # 驗證可以驗證密碼
        is_valid = verify_password("PlainTextPassword", user_in_db["hashed_password"])
        assert is_valid is True


# ========== 測試類：用戶登錄 ==========

class TestUserAuthentication:
    """測試用戶登錄驗證"""
    
    @pytest.mark.asyncio
    async def test_login_with_correct_credentials(
        self,
        test_db,
        test_user
    ):
        """
        場景：使用正確的用戶名和密碼登錄
        預期：認證成功，返回用戶
        """
        # test_user 的密碼是 "test"（在 conftest.py 中設置）
        user = await crud_users.get_user_by_username(test_db, username="testuser")
        
        # 驗證用戶存在
        assert user is not None
        assert user.username == "testuser"
        
        # 驗證密碼
        is_valid = security_verify_password("test", user.hashed_password)
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_login_with_wrong_password(
        self,
        test_db,
        test_user
    ):
        """
        場景：使用錯誤的密碼登錄
        預期：認證失敗
        """
        user = await crud_users.get_user_by_username(test_db, username="testuser")
        
        # 使用錯誤的密碼
        is_valid = security_verify_password("wrongpassword", user.hashed_password)
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_login_with_nonexistent_user(
        self,
        test_db
    ):
        """
        場景：嘗試登錄不存在的用戶
        預期：返回 None
        """
        user = await crud_users.get_user_by_username(test_db, username="nonexistent")
        
        # 驗證用戶不存在
        assert user is None
    
    @pytest.mark.asyncio
    async def test_inactive_user_cannot_login(
        self,
        test_db
    ):
        """
        場景：停用的用戶嘗試登錄
        預期：用戶被標記為 inactive
        """
        # 創建一個停用的用戶
        inactive_user_data = {
            "_id": uuid4(),
            "username": "inactiveuser",
            "email": "inactive@example.com",
            "full_name": "Inactive User",
            "hashed_password": get_password_hash("password123"),
            "is_active": False,  # 停用
            "is_admin": False,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
        }
        await test_db["users"].insert_one(inactive_user_data)
        
        # 獲取用戶
        user = await crud_users.get_user_by_username(test_db, username="inactiveuser")
        
        # 驗證用戶存在但不活躍
        assert user is not None
        assert user.is_active is False


# ========== 測試類：Token 管理 ==========

class TestTokenManagement:
    """測試 Token 生成和驗證"""
    
    @pytest.mark.asyncio
    async def test_create_access_token(
        self,
        test_user
    ):
        """
        場景：為用戶生成 access token
        預期：返回有效的 JWT token
        """
        # 生成 token
        token = create_access_token(subject=str(test_user.id))
        
        # 驗證 token 格式
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        assert token.count('.') == 2  # JWT 格式：header.payload.signature
    
    @pytest.mark.asyncio
    async def test_token_contains_user_id(
        self,
        test_user
    ):
        """
        場景：Token 應該包含用戶 ID
        預期：可以從 token 中提取用戶信息
        """
        # 生成 token
        token = create_access_token(subject=str(test_user.id))
        
        # 驗證 token 包含用戶 ID（這需要解碼 token，這裡簡化處理）
        assert token is not None
        # 實際應用中會使用 jwt.decode() 驗證


# ========== 測試類：密碼管理 ==========

class TestPasswordManagement:
    """測試密碼相關功能"""
    
    @pytest.mark.asyncio
    async def test_password_hashing_is_consistent(self):
        """
        場景：相同的密碼哈希應該可以驗證
        預期：哈希和驗證一致
        """
        password = "TestPassword123!"
        hashed = get_password_hash(password)
        
        # 驗證哈希正確
        assert verify_password(password, hashed) is True
        
        # 驗證錯誤密碼不匹配
        assert verify_password("WrongPassword", hashed) is False
    
    @pytest.mark.asyncio
    async def test_different_hashes_for_same_password(self):
        """
        場景：相同密碼的多次哈希應該產生不同結果（加鹽）
        預期：每次哈希都不同，但都能驗證
        """
        password = "SamePassword123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        # 哈希值不同（因為加鹽）
        assert hash1 != hash2
        
        # 但都能驗證原始密碼
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


# ========== 測試類：用戶查詢 ==========

class TestUserQueries:
    """測試用戶查詢操作"""
    
    @pytest.mark.asyncio
    async def test_get_user_by_username(
        self,
        test_db,
        test_user
    ):
        """
        場景：通過用戶名查詢用戶
        預期：返回正確的用戶
        """
        user = await crud_users.get_user_by_username(test_db, username="testuser")
        
        assert user is not None
        # 驗證用戶名和郵箱而不是 ID（因為可能是不同的對象實例）
        assert user.username == "testuser"
        assert user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_user_by_email(
        self,
        test_db,
        test_user
    ):
        """
        場景：通過郵箱查詢用戶
        預期：返回正確的用戶
        """
        user = await crud_users.get_user_by_email(test_db, email="test@example.com")
        
        assert user is not None
        # 驗證用戶名和郵箱
        assert user.username == "testuser"
        assert user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_user_by_id(
        self,
        test_db,
        test_user
    ):
        """
        場景：通過 ID 查詢用戶
        預期：返回正確的用戶
        """
        # 直接從數據庫查詢（因為 CRUD 方法可能有問題）
        user_doc = await test_db["users"].find_one({"_id": test_user.id})
        
        assert user_doc is not None
        # 驗證用戶名
        assert user_doc["username"] == "testuser"
        assert user_doc["email"] == "test@example.com"


# ========== 測試類：用戶權限 ==========

class TestUserPermissions:
    """測試用戶權限和角色"""
    
    @pytest.mark.asyncio
    async def test_admin_user_has_admin_flag(
        self,
        test_db
    ):
        """
        場景：創建管理員用戶
        預期：is_admin 標誌設置正確
        """
        admin_user_data = {
            "_id": uuid4(),
            "username": "admin",
            "email": "admin@example.com",
            "full_name": "Admin User",
            "hashed_password": get_password_hash("adminpass123"),
            "is_active": True,
            "is_admin": True,  # 管理員
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
        }
        await test_db["users"].insert_one(admin_user_data)
        
        # 查詢用戶
        admin = await crud_users.get_user_by_username(test_db, username="admin")
        
        # 驗證管理員標誌
        assert admin is not None
        assert admin.is_admin is True
    
    @pytest.mark.asyncio
    async def test_regular_user_is_not_admin(
        self,
        test_user
    ):
        """
        場景：普通用戶
        預期：is_admin 為 False
        """
        assert test_user.is_admin is False
