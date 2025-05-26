from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

# --- User Models ---
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="使用者名稱")
    email: Optional[EmailStr] = Field(None, description="使用者電子郵件 (可選)")
    full_name: Optional[str] = Field(None, max_length=100, description="使用者全名 (可選)")
    is_active: bool = Field(True, description="帳戶是否啟用")

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="使用者密碼 (明文)")

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    # 密碼更新應通過特定端點處理

class UserInDBBase(UserBase):
    id: UUID = Field(default_factory=uuid4)
    hashed_password: str = Field(..., description="哈希後的密碼")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "from_attributes": True, # Pydantic v2 (舊版 orm_mode)
        "collection_name": "users"
    }

class User(UserBase):
    """ 用於 API 回應的模型 (不包含密碼) """
    id: UUID
    created_at: datetime
    updated_at: datetime
    # is_active 已經在 UserBase 中，所以這裡不需要重複

    class Config:
        from_attributes = True # Pydantic v2

class UserInDB(UserInDBBase):
    """ 用於資料庫操作的模型 (包含密碼) """
    pass

class PasswordUpdateIn(BaseModel):
    current_password: str = Field(..., description="目前密碼")
    new_password: str = Field(..., min_length=8, description="新密碼，至少8個字符")

# --- ConnectedDevice Model (existing) ---
class ConnectedDevice(BaseModel):
    device_id: str = Field(..., description="裝置的唯一識別碼")
    device_name: str | None = Field(None, description="裝置的名稱")
    device_type: str | None = Field(None, description="裝置類型 (例如: android, ios, web)")
    ip_address: str | None = Field(None, description="裝置的 IP 位址")
    user_agent: str | None = Field(None, description="裝置的 User-Agent")
    first_connected_at: datetime = Field(default_factory=datetime.utcnow, description="首次連線時間")
    last_active_at: datetime = Field(default_factory=datetime.utcnow, description="最後活動時間")
    is_active: bool = Field(True, description="裝置是否處於活動狀態")
    user_id: UUID = Field(..., description="關聯的使用者ID，綁定後為必填")

    model_config = {
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "collection_name": "connected_devices",
        "json_schema_extra": {
            "example": {
                "device_id": "unique_device_identifier_123",
                "device_name": "My Android Phone",
                "device_type": "android",
                "ip_address": "192.168.1.100",
                "user_agent": "SortifyApp/1.0 Android/11",
                "first_connected_at": "2023-05-20T10:00:00Z",
                "last_active_at": "2023-05-20T12:30:00Z",
                "is_active": True,
                "user_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef"
            }
        }
    } 