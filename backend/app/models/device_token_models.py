"""
Device Token 數據模型
用於管理手機端裝置的長效認證 Token
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4


class DeviceTokenBase(BaseModel):
    """Device Token 基礎模型"""
    device_name: str = Field(..., description="裝置名稱，例如：'iPhone 13'")
    device_fingerprint: str = Field(..., description="裝置指紋（基於 User-Agent、Screen Resolution 等）")


class DeviceTokenCreate(DeviceTokenBase):
    """創建 Device Token 的請求模型"""
    user_id: UUID = Field(..., description="用戶ID")


class DeviceTokenInDB(DeviceTokenBase):
    """數據庫中的 Device Token 模型"""
    id: UUID = Field(default_factory=uuid4, description="Device Token ID")
    device_id: str = Field(..., description="裝置唯一標識符")
    user_id: UUID = Field(..., description="用戶ID")
    refresh_token: str = Field(..., description="Refresh Token（用於更新 Access Token）")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="創建時間")
    last_used: datetime = Field(default_factory=datetime.utcnow, description="最後使用時間")
    expires_at: datetime = Field(..., description="過期時間")
    is_active: bool = Field(default=True, description="是否啟用")
    last_ip: Optional[str] = Field(None, description="最後使用的 IP 地址")
    
    class Config:
        from_attributes = True


class DeviceToken(BaseModel):
    """Device Token 響應模型（不包含敏感信息）"""
    id: UUID
    device_id: str
    device_name: str
    user_id: UUID
    created_at: datetime
    last_used: datetime
    expires_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True


class PairingTokenCreate(BaseModel):
    """生成配對 Token 的請求模型"""
    pass  # 不需要額外參數，從當前用戶獲取


class PairingTokenResponse(BaseModel):
    """配對 Token 響應模型"""
    pairing_token: str = Field(..., description="配對 Token（5分鐘有效）")
    qr_data: str = Field(..., description="QR Code 數據（包含配對 Token 和服務器信息）")
    expires_at: datetime = Field(..., description="過期時間")


class DevicePairRequest(BaseModel):
    """裝置配對請求模型"""
    pairing_token: str = Field(..., description="配對 Token")
    device_name: str = Field(..., description="裝置名稱")
    device_fingerprint: str = Field(..., description="裝置指紋")


class DevicePairResponse(BaseModel):
    """裝置配對響應模型"""
    device_token: str = Field(..., description="長效 Device Token（30天）")
    refresh_token: str = Field(..., description="Refresh Token（90天）")
    device_id: str = Field(..., description="裝置ID")
    expires_at: datetime = Field(..., description="Device Token 過期時間")


class RefreshTokenRequest(BaseModel):
    """刷新 Token 請求模型"""
    refresh_token: str = Field(..., description="Refresh Token")
    device_id: str = Field(..., description="裝置ID")


class RefreshTokenResponse(BaseModel):
    """刷新 Token 響應模型"""
    access_token: str = Field(..., description="新的 Access Token")
    token_type: str = Field(default="bearer", description="Token 類型")


class DeviceListResponse(BaseModel):
    """裝置列表響應模型"""
    devices: list[DeviceToken] = Field(..., description="裝置列表")
    total: int = Field(..., description="總數量")


class DeviceRevokeResponse(BaseModel):
    """撤銷裝置響應模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")

