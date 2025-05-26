from pydantic import BaseModel, Field
from typing import Optional, Union
# from pydantic_settings import BaseSettings # No longer needed here if not defining BaseSettings itself

# 新增：AI 服務設定的 Pydantic 模型
class AIServiceSettingsInput(BaseModel):
    """AI 服務設定 - 用於API輸入，可能包含API Key"""
    provider: Optional[str] = Field("google", description="AI 提供商，目前僅支援 'google'")
    model: Optional[str] = Field(None, description="AI 模型名稱，例如：gemini-1.5-flash")
    # apiKey is received here but will be stored in .env, not directly in DB model if this input model is part of UpdatableSettingsData.
    api_key: Optional[str] = Field(None, alias="apiKey", title="AI 服務 API 金鑰") 
    temperature: Optional[float] = Field(None, title="AI 模型 Temperature", ge=0, le=1, description="控制模型輸出的隨機性，0-1 之間")
    force_stable_model: Optional[bool] = Field(None, alias="forceStableModel", title="強制使用穩定模型")
    ensure_chinese_output: Optional[bool] = Field(None, alias="ensureChineseOutput", title="確保中文輸出")
    max_output_tokens: Optional[int] = Field(None, alias="maxOutputTokens", title="最大輸出Token數量", ge=1)

    class Config:
        populate_by_name = True

class AIServiceSettingsStored(BaseModel):
    """AI 服務設定 - 用於資料庫儲存和API GET回應 (不含API Key)"""
    provider: Optional[str] = Field("google", description="AI 提供商")
    model: Optional[str] = Field(None, description="AI 模型名稱")
    temperature: Optional[float] = Field(None, title="AI 模型 Temperature", ge=0, le=1)
    is_api_key_configured: bool = Field(False, description="指示 AI API Key 是否已在環境變數中設定")
    force_stable_model: Optional[bool] = Field(default=False, title="強制使用穩定模型")
    ensure_chinese_output: Optional[bool] = Field(default=False, title="確保中文輸出")
    max_output_tokens: Optional[int] = Field(None, title="最大輸出Token數量", ge=1)

# 新增：資料庫設定的 Pydantic 模型
class DatabaseSettings(BaseModel):
    uri: Optional[str] = Field(None, alias="uri", title="資料庫連接 URI")
    db_name: Optional[str] = Field(None, alias="dbName", title="資料庫名稱")

    class Config:
        populate_by_name = True

# 修改：SettingsData 以包含巢狀模型和新欄位
class SettingsDataResponse(BaseModel):
    """系統設定 - 用於 API GET 回應 (不含敏感資訊如 API Key)"""
    ai_service: AIServiceSettingsStored = Field(default_factory=AIServiceSettingsStored, alias="aiService")
    database: DatabaseSettings = Field(default_factory=DatabaseSettings, alias="database")
    auto_connect: Optional[bool] = Field(None, alias="autoConnect", title="自動連線到後端服務")
    auto_sync: Optional[bool] = Field(None, alias="autoSync", title="自動同步檔案")
    is_database_connected: bool = Field(True, alias="isDatabaseConnected", title="資料庫是否已連接")

    class Config:
        populate_by_name = True

# 修改：UpdatableSettingsData 以反映巢狀結構且所有欄位可選
class UpdatableSettingsData(BaseModel):
    """允許使用者透過 API 更新的設定項目 (POST/PUT)"""
    # For updates, client sends AIServiceSettingsInput which might include the apiKey
    ai_service: Optional[AIServiceSettingsInput] = Field(None, alias="aiService") 
    database: Optional[DatabaseSettings] = Field(None, alias="database")
    auto_connect: Optional[bool] = Field(None, alias="autoConnect")
    auto_sync: Optional[bool] = Field(None, alias="autoSync")

    class Config:
        populate_by_name = True

# The existing SettingsData in the file seems to be the one stored in the DB.
# Let's define what is actually stored in the DB for settings.
# It will contain AIServiceSettingsStored (or parts of it like model, provider, temperature)
# For simplicity, we'll assume the CRUD operations will adapt AIServiceSettingsInput 
# to a storable format (without API key) and construct SettingsDataResponse.

# Let's redefine the main SettingsData to be what's stored in DB.
# It should not contain the api_key directly or the is_api_key_configured flag (that's for response).
class StoredAISettings(BaseModel):
    provider: Optional[str] = Field("google")
    model: Optional[str] = None
    temperature: Optional[float] = None
    force_stable_model: Optional[bool] = Field(default=False, title="強制使用穩定模型")
    ensure_chinese_output: Optional[bool] = Field(default=False, title="確保中文輸出")
    max_output_tokens: Optional[int] = Field(None, title="最大輸出Token數量", ge=1)

class DBSettingsSchema(BaseModel): # This is what's actually stored in the 'settings' collection in MongoDB
    # Using a fixed ID for the single global settings document
    # id: str = Field("global_settings", alias="_id") 
    ai_service: StoredAISettings = Field(default_factory=StoredAISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings) # Storing DB connection URI in DB is unusual, usually from .env
    auto_connect: Optional[bool] = None
    auto_sync: Optional[bool] = None

    class Config:
        populate_by_name = True


class ConnectionInfo(BaseModel):
    """手機配對連線資訊"""
    qr_code_image: Optional[str] = Field(None, title="QR Code 圖像")
    pairing_code: Optional[str] = Field(None, title="配對碼")
    server_url: Optional[str] = Field(None, title="伺服器連接 URL")

class TunnelStatus(BaseModel):
    """Cloudflare Tunnel 狀態"""
    is_active: bool = Field(False, title="是否啟用")
    url: Optional[str] = Field(None, title="公開存取 URL")

# 新增：測試資料庫連線的模型
class TestDBConnectionRequest(BaseModel):
    uri: str = Field(..., title="MongoDB 連線 URI")
    db_name: str = Field(..., title="MongoDB 資料庫名稱")

class TestDBConnectionResponse(BaseModel):
    success: bool = Field(..., title="連線測試是否成功")
    message: str = Field(..., title="連線測試結果訊息")
    error_details: Optional[str] = Field(None, title="詳細錯誤訊息 (如果失敗)") 