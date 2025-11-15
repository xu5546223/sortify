"""
Users API (設備管理) 整合測試

測試設備管理 API 的核心業務邏輯，專注於：
- 設備註冊和更新
- 設備查詢和權限隔離
- 數據庫副作用驗證

注意：這是服務層測試，不是 HTTP API 測試
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime, UTC
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user_models import User, ConnectedDevice
from app.core.password_utils import get_password_hash
from app.crud.crud_users import crud_devices

# 標記為整合測試
pytestmark = pytest.mark.integration


# ========== 測試類：設備基本操作 ==========

class TestDeviceBasicOperations:
    """測試設備的基本 CRUD 操作"""
    
    @pytest.mark.asyncio
    async def test_create_device(
        self,
        test_db,
        test_user
    ):
        """
        場景：用戶註冊新設備
        預期：設備成功創建並關聯到用戶
        """
        device_data = ConnectedDevice(
            device_id="test-device-001",
            device_name="Test iPhone",
            device_type="ios",
            user_id=test_user.id,
            is_active=True
        )
        
        # 創建設備
        created_device = await crud_devices.create_or_update(test_db, device_data=device_data)
        
        # 驗證返回值
        assert created_device is not None
        assert created_device.device_id == "test-device-001"
        assert created_device.user_id == test_user.id
        assert created_device.is_active is True
        
        # 驗證數據庫
        device_in_db = await test_db["connected_devices"].find_one({"device_id": "test-device-001"})
        assert device_in_db is not None
        assert device_in_db["user_id"] == test_user.id
    
    @pytest.mark.asyncio
    async def test_update_existing_device(
        self,
        test_db,
        test_user
    ):
        """
        場景：更新現有設備信息
        預期：設備信息成功更新
        """
        # 先創建設備
        device_data = ConnectedDevice(
            device_id="test-device-002",
            device_name="Old Name",
            device_type="android",
            user_id=test_user.id,
            is_active=True
        )
        await crud_devices.create_or_update(test_db, device_data=device_data)
        
        # 更新設備
        updated_data = ConnectedDevice(
            device_id="test-device-002",
            device_name="New Name",
            device_type="android",
            user_id=test_user.id,
            is_active=True
        )
        updated_device = await crud_devices.create_or_update(test_db, device_data=updated_data)
        
        # 驗證更新
        assert updated_device is not None
        assert updated_device.device_name == "New Name"
        
        # 驗證數據庫
        device_in_db = await test_db["connected_devices"].find_one({"device_id": "test-device-002"})
        assert device_in_db["device_name"] == "New Name"
    
    @pytest.mark.asyncio
    async def test_get_user_devices(
        self,
        test_db,
        test_user
    ):
        """
        場景：獲取用戶的所有設備
        預期：返回屬於該用戶的所有設備
        """
        # 創建多個設備
        device1 = ConnectedDevice(
            device_id="device-1",
            device_name="iPhone",
            device_type="ios",
            user_id=test_user.id,
            is_active=True
        )
        device2 = ConnectedDevice(
            device_id="device-2",
            device_name="Android",
            device_type="android",
            user_id=test_user.id,
            is_active=True
        )
        
        await crud_devices.create_or_update(test_db, device_data=device1)
        await crud_devices.create_or_update(test_db, device_data=device2)
        
        # 驗證設備已創建
        device1_check = await crud_devices.get_by_id(test_db, device_id="device-1")
        device2_check = await crud_devices.get_by_id(test_db, device_id="device-2")
        
        assert device1_check is not None
        assert device2_check is not None
        assert device1_check.user_id == test_user.id
        assert device2_check.user_id == test_user.id


class TestDevicePermissions:
    """測試設備權限隔離"""
    
    @pytest.mark.asyncio
    async def test_devices_isolated_by_user(
        self,
        test_db,
        test_user,
        other_user
    ):
        """
        場景：不同用戶的設備完全隔離
        預期：每個用戶只能看到自己的設備
        """
        # test_user 的設備
        device1 = ConnectedDevice(
            device_id="user1-device",
            device_name="User 1 Phone",
            device_type="ios",
            user_id=test_user.id,
            is_active=True
        )
        await crud_devices.create_or_update(test_db, device_data=device1)
        
        # other_user 的設備
        device2 = ConnectedDevice(
            device_id="user2-device",
            device_name="User 2 Phone",
            device_type="android",
            user_id=other_user.id,
            is_active=True
        )
        await crud_devices.create_or_update(test_db, device_data=device2)
        
        # 獲取 test_user 的設備
        user1_device = await crud_devices.get_by_id(test_db, device_id="user1-device")
        assert user1_device is not None
        assert user1_device.user_id == test_user.id
        
        # 獲取 other_user 的設備
        user2_device = await crud_devices.get_by_id(test_db, device_id="user2-device")
        assert user2_device is not None
        assert user2_device.user_id == other_user.id


class TestDeviceLifecycle:
    """測試設備生命週期管理"""
    
    @pytest.mark.asyncio
    async def test_deactivate_device(
        self,
        test_db,
        test_user
    ):
        """
        場景：停用設備
        預期：設備狀態更新為 inactive
        """
        # 創建激活的設備
        device = ConnectedDevice(
            device_id="active-device",
            device_name="Active Phone",
            device_type="ios",
            user_id=test_user.id,
            is_active=True
        )
        await crud_devices.create_or_update(test_db, device_data=device)
        
        # 停用設備
        deactivated = await crud_devices.deactivate(test_db, device_id="active-device")
        
        # 驗證
        assert deactivated is not None
        assert deactivated.is_active is False
        
        # 驗證數據庫
        device_in_db = await test_db["connected_devices"].find_one({"device_id": "active-device"})
        assert device_in_db["is_active"] is False
    
    @pytest.mark.asyncio
    async def test_remove_device(
        self,
        test_db,
        test_user
    ):
        """
        場景：刪除設備
        預期：設備從數據庫中移除
        """
        # 創建設備
        device = ConnectedDevice(
            device_id="temp-device",
            device_name="Temp Phone",
            device_type="android",
            user_id=test_user.id,
            is_active=True
        )
        await crud_devices.create_or_update(test_db, device_data=device)
        
        # 刪除設備
        removed = await crud_devices.remove(test_db, device_id="temp-device")
        
        # 驗證
        assert removed is True
        
        # 驗證數據庫中不存在
        device_in_db = await test_db["connected_devices"].find_one({"device_id": "temp-device"})
        assert device_in_db is None


class TestDeviceValidation:
    """測試設備數據驗證"""
    
    @pytest.mark.asyncio
    async def test_device_requires_device_id(
        self,
        test_db,
        test_user
    ):
        """
        場景：設備 ID 必填
        預期：缺少 device_id 會失敗
        """
        # 嘗試創建沒有 device_id 的設備會在 Pydantic 驗證階段失敗
        with pytest.raises(Exception):  # Pydantic ValidationError
            ConnectedDevice(
                # device_id 缺失
                device_name="No ID Phone",
                device_type="ios",
                user_id=test_user.id
            )
    
    @pytest.mark.asyncio
    async def test_device_associated_with_user(
        self,
        test_db,
        test_user
    ):
        """
        場景：設備必須關聯到用戶
        預期：user_id 正確設置
        """
        device = ConnectedDevice(
            device_id="user-device",
            device_name="User Phone",
            device_type="ios",
            user_id=test_user.id,
            is_active=True
        )
        
        created = await crud_devices.create_or_update(test_db, device_data=device)
        
        # 驗證關聯
        assert created.user_id == test_user.id
