from datetime import datetime, timezone # Import timezone
from enum import Enum
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# Use UTC now function
def utc_now():
    """Returns the current time in UTC."""
    return datetime.now(timezone.utc)

class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"
    CRITICAL = "CRITICAL"

class LogEntryBase(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)  # Use UTC time
    level: LogLevel = LogLevel.INFO
    message: str
    source: Optional[str] = None  # 例如: "documents_api", "system_service"
    module: Optional[str] = None # 例如: "crud_documents", "main"
    function: Optional[str] = None # 例如: "create_document", "startup_event"
    user_id: Optional[str] = None # 或 UUID
    device_id: Optional[str] = None # 或 UUID
    request_id: Optional[str] = None # 用於追蹤單個請求的日誌鏈
    details: Optional[Dict[str, Any]] = None # 用於額外的結構化數據

class LogEntryCreate(LogEntryBase):
    pass

class LogEntryDB(LogEntryBase):
    id: UUID = Field(default_factory=uuid4)

    model_config = {
        "from_attributes": True
    }
    # 如果直接使用 MongoDB _id，可以這樣配置，但 Pydantic v2 推薦 Field(alias="_id")
    # from pydantic import Field
    # id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class LogEntryPublic(LogEntryBase):
    id: UUID
    timestamp: datetime
    level: LogLevel
    message: str
    source: Optional[str] = None
    module: Optional[str] = None
    function: Optional[str] = None
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None 