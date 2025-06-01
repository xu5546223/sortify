from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.results import UpdateResult, DeleteResult
from datetime import datetime
from uuid import UUID
from typing import Optional

from ..models.user_models import ConnectedDevice, UserCreate, UserInDB, User, UserUpdate
from ..core.logging_utils import log_event
from ..models.log_models import LogLevel
from ..core.password_utils import get_password_hash

# --- CRUD Operations for ConnectedDevice ---
DEVICE_COLLECTION_NAME = ConnectedDevice.model_config['collection_name']

async def create_or_update_device(db: AsyncIOMotorDatabase, device_data: ConnectedDevice) -> ConnectedDevice | None:
    """
    創建一個新的裝置記錄，或者如果裝置已存在，則更新其活動時間和狀態。
    """
    collection = db[DEVICE_COLLECTION_NAME]
    existing_device_doc = await collection.find_one({"device_id": device_data.device_id})

    if existing_device_doc:
        update_fields = {
            "last_active_at": datetime.utcnow(),
            "is_active": True,
            "ip_address": device_data.ip_address,
            "user_agent": device_data.user_agent,
            "device_name": device_data.device_name,
            "device_type": device_data.device_type,
            "user_id": device_data.user_id
        }
        update_payload = {k: v for k, v in update_fields.items() if v is not None}
        
        if not update_payload:
            return ConnectedDevice(**existing_device_doc)
            
        await collection.update_one(
            {"device_id": device_data.device_id},
            {"$set": update_payload}
        )
        device_doc_after_update = await collection.find_one({"device_id": device_data.device_id})
        if device_doc_after_update:
            # Log event for update
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="Device updated.",
                source="crud_devices.create_or_update_device", # Using actual function name
                details={
                    "device_id": device_data.device_id,
                    "user_id": str(device_data.user_id) if device_data.user_id else None,
                    "action_taken": "updated"
                }
            )
            return ConnectedDevice(**device_doc_after_update)
        return None # Should ideally not happen if update was successful
    else:
        # Creating new device
        device_dict = device_data.model_dump(exclude_unset=True)
        device_dict["first_connected_at"] = device_dict.get("first_connected_at", datetime.utcnow())
        device_dict["last_active_at"] = device_dict.get("last_active_at", datetime.utcnow())
        device_dict["is_active"] = device_dict.get("is_active", True)
        await collection.insert_one(device_dict)

        # Log event for creation
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="Device created.",
            source="crud_devices.create_or_update_device", # Using actual function name
            details={
                "device_id": device_data.device_id,
                "user_id": str(device_data.user_id) if device_data.user_id else None,
                "action_taken": "created"
            }
        )
        return ConnectedDevice(**device_dict)

async def get_device_by_id(db: AsyncIOMotorDatabase, device_id: str) -> ConnectedDevice | None:
    collection = db[DEVICE_COLLECTION_NAME]
    device = await collection.find_one({"device_id": device_id})
    return ConnectedDevice(**device) if device else None

async def get_all_devices(
    db: AsyncIOMotorDatabase, 
    skip: int = 0, 
    limit: int = 100, 
    active_only: bool = False,
    user_id: Optional[UUID] = None  # Add user_id parameter
) -> list[ConnectedDevice]:
    collection = db[DEVICE_COLLECTION_NAME]
    query: dict = {}
    if active_only:
        query["is_active"] = True
    if user_id:
        query["user_id"] = user_id  # Add user_id to the query
        
    devices_cursor = collection.find(query).skip(skip).limit(limit)
    devices = []
    async for device_doc in devices_cursor:
        devices.append(ConnectedDevice(**device_doc))
    return devices

async def update_device_activity(db: AsyncIOMotorDatabase, device_id: str) -> ConnectedDevice | None:
    collection = db[DEVICE_COLLECTION_NAME]
    result: UpdateResult = await collection.update_one(
        {"device_id": device_id},
        {"$set": {"last_active_at": datetime.utcnow(), "is_active": True}}
    )
    if result.matched_count > 0:
        return await get_device_by_id(db, device_id)
    return None

async def deactivate_device(db: AsyncIOMotorDatabase, device_id: str) -> ConnectedDevice | None:
    collection = db[DEVICE_COLLECTION_NAME]
    result: UpdateResult = await collection.update_one(
        {"device_id": device_id},
        {"$set": {"is_active": False, "last_active_at": datetime.utcnow()}}
    )
    if result.matched_count > 0:
        updated_device = await get_device_by_id(db, device_id)
        # Log event
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="Device deactivated.",
            source="crud_devices.deactivate_device", # Using actual function name
            details={"device_id": device_id}
        )
        return updated_device
    return None

async def remove_device(db: AsyncIOMotorDatabase, device_id: str) -> bool:
    collection = db[DEVICE_COLLECTION_NAME]
    result: DeleteResult = await collection.delete_one({"device_id": device_id})
    if result.deleted_count > 0:
        # Log event
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="Device removed.",
            source="crud_devices.remove_device", # Using actual function name
            details={"device_id": device_id}
        )
        return True
    return False

class CRUDDevice:
    async def create_or_update(self, db: AsyncIOMotorDatabase, device_data: ConnectedDevice) -> ConnectedDevice | None:
        return await create_or_update_device(db, device_data)

    async def get_by_id(self, db: AsyncIOMotorDatabase, device_id: str) -> ConnectedDevice | None:
        return await get_device_by_id(db, device_id)

    async def get_all(
        self, 
        db: AsyncIOMotorDatabase, 
        skip: int = 0, 
        limit: int = 100, 
        active_only: bool = False,
        user_id: Optional[UUID] = None  # Add user_id parameter
    ) -> list[ConnectedDevice]:
        return await get_all_devices(db, skip, limit, active_only, user_id=user_id)

    async def update_activity(self, db: AsyncIOMotorDatabase, device_id: str) -> ConnectedDevice | None:
        return await update_device_activity(db, device_id)

    async def deactivate(self, db: AsyncIOMotorDatabase, device_id: str) -> ConnectedDevice | None:
        return await deactivate_device(db, device_id)

    async def remove(self, db: AsyncIOMotorDatabase, device_id: str) -> bool:
        return await remove_device(db, device_id)

crud_devices = CRUDDevice()

# --- CRUD Operations for User ---
USER_COLLECTION_NAME = UserInDB.model_config['collection_name']

class CRUDUser:
    async def get_user_by_id(self, db: AsyncIOMotorDatabase, user_id: UUID) -> UserInDB | None:
        user_doc = await db[USER_COLLECTION_NAME].find_one({"id": user_id})
        return UserInDB(**user_doc) if user_doc else None

    async def get_user_by_username(self, db: AsyncIOMotorDatabase, username: str) -> UserInDB | None:
        user_doc = await db[USER_COLLECTION_NAME].find_one({"username": username})
        return UserInDB(**user_doc) if user_doc else None

    async def get_user_by_email(self, db: AsyncIOMotorDatabase, email: str) -> UserInDB | None:
        user_doc = await db[USER_COLLECTION_NAME].find_one({"email": email})
        return UserInDB(**user_doc) if user_doc else None

    async def create_user(self, db: AsyncIOMotorDatabase, user_in: UserCreate) -> UserInDB:
        hashed_password = get_password_hash(user_in.password)
        user_db_object = UserInDB(
            username=user_in.username,
            email=user_in.email,
            full_name=user_in.full_name,
            is_active=user_in.is_active,
            hashed_password=hashed_password
        )
        user_to_insert = user_db_object.model_dump()
        
        await db[USER_COLLECTION_NAME].insert_one(user_to_insert)

        # Log event
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="User created successfully.",
            source="crud_users.create_user",
            details={
                "user_id": str(user_db_object.id),
                "username": user_db_object.username,
                "email": user_db_object.email
            }
        )
        return user_db_object

    async def update_user(
        self, db: AsyncIOMotorDatabase, user_id: UUID, user_in: UserUpdate
    ) -> UserInDB | None:
        update_data = user_in.model_dump(exclude_unset=True)
        if not update_data: # 如果沒有提供任何更新數據
            return await self.get_user_by_id(db, user_id)

        # Email 衝突檢查已移至 API 層
        # if "email" in update_data and update_data["email"] is not None:
        #     existing_user_with_email = await self.get_user_by_email(db, email=update_data["email"])
        #     if existing_user_with_email and existing_user_with_email.id != user_id:
        #         print(f"Error: Email {update_data['email']} is already in use by another user.")
        #         return None # 表示更新失敗
        
        update_data["updated_at"] = datetime.utcnow()

        result = await db[USER_COLLECTION_NAME].update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        if result.matched_count > 0:
            # Log event
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="User updated successfully.",
                source="crud_users.update_user",
                details={
                    "user_id": str(user_id),
                    "updated_fields": list(update_data.keys()) # Logs field names, not values
                }
            )
            return await self.get_user_by_id(db, user_id)
        return None

    async def update_password(
        self, db: AsyncIOMotorDatabase, user_id: UUID, new_password: str
    ) -> bool:
        hashed_password = get_password_hash(new_password)
        update_data = {
            "hashed_password": hashed_password,
            "updated_at": datetime.utcnow()
        }
        result = await db[USER_COLLECTION_NAME].update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        if result.modified_count > 0:
            # Log event
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="User password updated successfully.",
                source="crud_users.update_password",
                details={"user_id": str(user_id)}
            )
            return True
        return False

    async def delete_user(self, db: AsyncIOMotorDatabase, user_id: UUID) -> bool:
        result = await db[USER_COLLECTION_NAME].delete_one({"id": user_id})
        if result.deleted_count > 0:
            # Log event
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="User deleted successfully.",
                source="crud_users.delete_user",
                details={"user_id": str(user_id)}
            )
            return True
        return False

crud_users = CRUDUser() 