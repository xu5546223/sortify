"""
Device Token CRUD 操作
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import Binary

from ..models.device_token_models import DeviceTokenCreate, DeviceTokenInDB
from ..core.device_security import generate_device_id, generate_refresh_token


class CRUDDeviceTokens:
    """Device Token CRUD 操作類"""
    
    def __init__(self, collection_name: str = "device_tokens"):
        self.collection_name = collection_name
    
    async def create_device_token(
        self,
        db: AsyncIOMotorDatabase,
        user_id: UUID,
        device_name: str,
        device_fingerprint: str,
        expires_at: datetime,
        last_ip: Optional[str] = None
    ) -> DeviceTokenInDB:
        """
        創建新的 Device Token
        
        Args:
            db: 數據庫實例
            user_id: 用戶 ID
            device_name: 裝置名稱
            device_fingerprint: 裝置指紋
            expires_at: 過期時間
            last_ip: 最後使用的 IP
            
        Returns:
            創建的 Device Token
        """
        collection = db[self.collection_name]
        
        # 生成唯一的裝置 ID、UUID 和 Refresh Token
        from uuid import uuid4
        device_id = generate_device_id(user_id, device_fingerprint)
        record_id = uuid4()  # 生成 UUID 作為記錄 ID
        refresh_token = generate_refresh_token()
        
        device_token_data = {
            "id": Binary.from_uuid(record_id),  # 使用 UUID 而不是 ObjectId
            "device_id": device_id,
            "user_id": Binary.from_uuid(user_id),
            "device_name": device_name,
            "device_fingerprint": device_fingerprint,
            "refresh_token": refresh_token,
            "created_at": datetime.now(timezone.utc),
            "last_used": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "is_active": True,
            "last_ip": last_ip
        }
        
        result = await collection.insert_one(device_token_data)
        
        # 返回時使用 UUID 對象
        device_token_data["id"] = record_id
        device_token_data["user_id"] = user_id
        
        return DeviceTokenInDB(**device_token_data)
    
    async def get_device_token_by_device_id(
        self,
        db: AsyncIOMotorDatabase,
        device_id: str
    ) -> Optional[DeviceTokenInDB]:
        """
        根據 Device ID 獲取 Device Token
        
        Args:
            db: 數據庫實例
            device_id: 裝置 ID
            
        Returns:
            Device Token（如果存在）
        """
        collection = db[self.collection_name]
        
        device_token_data = await collection.find_one({"device_id": device_id})
        
        if not device_token_data:
            return None
        
        # 從 MongoDB 文檔轉換為 Pydantic 模型
        device_token_data.pop("_id", None)  # 移除 MongoDB 的 _id
        
        # 將 Binary UUID 轉換為 UUID 對象（檢查類型）
        if isinstance(device_token_data.get("id"), Binary):
            device_token_data["id"] = UUID(bytes=device_token_data["id"])
        elif not isinstance(device_token_data.get("id"), UUID):
            # 如果既不是 Binary 也不是 UUID，嘗試從字符串轉換
            device_token_data["id"] = UUID(device_token_data["id"])
            
        if isinstance(device_token_data.get("user_id"), Binary):
            device_token_data["user_id"] = UUID(bytes=device_token_data["user_id"])
        elif not isinstance(device_token_data.get("user_id"), UUID):
            device_token_data["user_id"] = UUID(device_token_data["user_id"])
        
        return DeviceTokenInDB(**device_token_data)
    
    async def get_device_token_by_refresh_token(
        self,
        db: AsyncIOMotorDatabase,
        refresh_token: str
    ) -> Optional[DeviceTokenInDB]:
        """
        根據 Refresh Token 獲取 Device Token
        
        Args:
            db: 數據庫實例
            refresh_token: Refresh Token
            
        Returns:
            Device Token（如果存在）
        """
        collection = db[self.collection_name]
        
        device_token_data = await collection.find_one({"refresh_token": refresh_token})
        
        if not device_token_data:
            return None
        
        # 從 MongoDB 文檔轉換為 Pydantic 模型
        device_token_data.pop("_id", None)  # 移除 MongoDB 的 _id
        
        # 將 Binary UUID 轉換為 UUID 對象（檢查類型）
        if isinstance(device_token_data.get("id"), Binary):
            device_token_data["id"] = UUID(bytes=device_token_data["id"])
        elif not isinstance(device_token_data.get("id"), UUID):
            device_token_data["id"] = UUID(device_token_data["id"])
            
        if isinstance(device_token_data.get("user_id"), Binary):
            device_token_data["user_id"] = UUID(bytes=device_token_data["user_id"])
        elif not isinstance(device_token_data.get("user_id"), UUID):
            device_token_data["user_id"] = UUID(device_token_data["user_id"])
        
        return DeviceTokenInDB(**device_token_data)
    
    async def get_user_devices(
        self,
        db: AsyncIOMotorDatabase,
        user_id: UUID,
        include_inactive: bool = False
    ) -> List[DeviceTokenInDB]:
        """
        獲取用戶的所有裝置
        
        Args:
            db: 數據庫實例
            user_id: 用戶 ID
            include_inactive: 是否包含已停用的裝置
            
        Returns:
            Device Token 列表
        """
        collection = db[self.collection_name]
        
        query = {"user_id": Binary.from_uuid(user_id)}
        if not include_inactive:
            query["is_active"] = True
        
        cursor = collection.find(query).sort("last_used", -1)
        
        devices = []
        async for device_data in cursor:
            # 從 MongoDB 文檔轉換為 Pydantic 模型
            device_data.pop("_id", None)  # 移除 MongoDB 的 _id
            
            # 將 Binary UUID 轉換為 UUID 對象（檢查類型）
            if isinstance(device_data.get("id"), Binary):
                device_data["id"] = UUID(bytes=device_data["id"])
            elif not isinstance(device_data.get("id"), UUID):
                # 如果既不是 Binary 也不是 UUID，跳過這條記錄
                print(f"⚠️  跳過無效記錄：id 類型為 {type(device_data.get('id'))}")
                continue
                
            if isinstance(device_data.get("user_id"), Binary):
                device_data["user_id"] = UUID(bytes=device_data["user_id"])
            elif not isinstance(device_data.get("user_id"), UUID):
                print(f"⚠️  跳過無效記錄：user_id 類型為 {type(device_data.get('user_id'))}")
                continue
                
            devices.append(DeviceTokenInDB(**device_data))
        
        return devices
    
    async def update_last_used(
        self,
        db: AsyncIOMotorDatabase,
        device_id: str,
        last_ip: Optional[str] = None
    ) -> bool:
        """
        更新裝置的最後使用時間
        
        Args:
            db: 數據庫實例
            device_id: 裝置 ID
            last_ip: 最後使用的 IP
            
        Returns:
            是否更新成功
        """
        collection = db[self.collection_name]
        
        update_data = {
            "last_used": datetime.now(timezone.utc)
        }
        
        if last_ip:
            update_data["last_ip"] = last_ip
        
        result = await collection.update_one(
            {"device_id": device_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    async def revoke_device(
        self,
        db: AsyncIOMotorDatabase,
        device_id: str,
        user_id: UUID
    ) -> bool:
        """
        撤銷（停用）裝置
        
        Args:
            db: 數據庫實例
            device_id: 裝置 ID
            user_id: 用戶 ID（用於驗證所有權）
            
        Returns:
            是否撤銷成功
        """
        collection = db[self.collection_name]
        
        result = await collection.update_one(
            {
                "device_id": device_id,
                "user_id": Binary.from_uuid(user_id)
            },
            {"$set": {"is_active": False}}
        )
        
        return result.modified_count > 0
    
    async def delete_device(
        self,
        db: AsyncIOMotorDatabase,
        device_id: str,
        user_id: UUID
    ) -> bool:
        """
        刪除裝置記錄
        
        Args:
            db: 數據庫實例
            device_id: 裝置 ID
            user_id: 用戶 ID（用於驗證所有權）
            
        Returns:
            是否刪除成功
        """
        collection = db[self.collection_name]
        
        result = await collection.delete_one(
            {
                "device_id": device_id,
                "user_id": Binary.from_uuid(user_id)
            }
        )
        
        return result.deleted_count > 0
    
    async def cleanup_expired_tokens(
        self,
        db: AsyncIOMotorDatabase,
        days_threshold: int = 90
    ) -> int:
        """
        清理過期的 Token
        
        Args:
            db: 數據庫實例
            days_threshold: 過期多少天後才刪除（默認90天）
            
        Returns:
            清理的數量
        """
        collection = db[self.collection_name]
        
        # 計算閾值時間
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        
        result = await collection.delete_many({
            "expires_at": {"$lt": threshold_date}
        })
        
        return result.deleted_count
    
    async def cleanup_revoked_devices(
        self,
        db: AsyncIOMotorDatabase,
        days_threshold: int = 30
    ) -> int:
        """
        清理長期未使用的已撤銷設備
        
        Args:
            db: 數據庫實例
            days_threshold: 撤銷多少天後才刪除（默認30天）
            
        Returns:
            清理的數量
        """
        collection = db[self.collection_name]
        
        # 計算閾值時間
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        
        result = await collection.delete_many({
            "is_active": False,
            "last_used": {"$lt": threshold_date}
        })
        
        return result.deleted_count
    
    async def create_indexes(self, db: AsyncIOMotorDatabase):
        """創建必要的索引"""
        collection = db[self.collection_name]
        
        # 複合索引：user_id + device_id
        await collection.create_index([("user_id", 1), ("device_id", 1)], unique=True)
        
        # 唯一索引：refresh_token
        await collection.create_index("refresh_token", unique=True)
        
        # 索引：expires_at（用於清理過期 Token）
        await collection.create_index("expires_at")
        
        # 索引：user_id（用於查詢用戶裝置）
        await collection.create_index("user_id")


# 單例實例
crud_device_tokens = CRUDDeviceTokens()

