from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class EmailSource(str, Enum):
    """郵件來源"""
    GMAIL = "gmail"
    CUSTOM = "custom"


class EmailMessage(BaseModel):
    """Gmail 郵件模型"""
    email_id: str = Field(..., description="Gmail 郵件 ID")
    message_id: str = Field(..., description="RFC 2822 消息 ID")
    thread_id: str = Field(..., description="Gmail 線程 ID")
    subject: str = Field(..., description="郵件主題")
    from_address: str = Field(..., description="發件人郵箱")
    to_addresses: List[str] = Field(default_factory=list, description="收件人郵箱列表")
    cc_addresses: Optional[List[str]] = Field(default_factory=list, description="抄送地址")
    bcc_addresses: Optional[List[str]] = Field(default_factory=list, description="密件抄送地址")
    date: datetime = Field(..., description="郵件日期")
    body: str = Field(..., description="郵件正文")
    snippet: str = Field(..., description="郵件摘要 (preview)")
    attachments: Optional[List[Dict[str, str]]] = Field(default_factory=list, description="附件列表")
    labels: Optional[List[str]] = Field(default_factory=list, description="Gmail 標籤")
    is_unread: bool = Field(False, description="是否未讀")
    is_starred: bool = Field(False, description="是否標星")

    class Config:
        json_schema_extra = {
            "example": {
                "email_id": "18c2e26e09451234",
                "message_id": "<CAK8g8zW=something@mail.gmail.com>",
                "thread_id": "18c2e26e09451234",
                "subject": "Meeting Tomorrow",
                "from_address": "john@example.com",
                "to_addresses": ["jane@example.com"],
                "date": "2024-01-15T10:30:00Z",
                "body": "Hi Jane, let's meet tomorrow...",
                "snippet": "Hi Jane, let's meet tomorrow...",
                "labels": ["INBOX", "IMPORTANT"]
            }
        }


class GmailMessagePreview(BaseModel):
    """Gmail 郵件預覽 (用於列表顯示)"""
    email_id: str
    subject: str
    from_address: str
    snippet: str
    date: datetime
    size: int
    is_unread: bool
    is_starred: bool


class BatchEmailImportRequest(BaseModel):
    """批量導入郵件請求"""
    email_ids: List[str] = Field(..., description="要導入的郵件 ID 列表")
    tags: Optional[List[str]] = Field(default_factory=list, description="為導入的郵件添加的標籤")
    trigger_analysis: bool = Field(False, description="是否立即觸發 AI 分析")


class EmailImportResponse(BaseModel):
    """郵件導入響應"""
    email_id: str
    document_id: Optional[uuid.UUID] = None
    status: str  # "success" | "already_imported" | "error"
    message: Optional[str] = None


class BatchEmailImportResponse(BaseModel):
    """批量導入響應"""
    total: int
    successful: int
    skipped: int
    failed: int
    details: List[EmailImportResponse]
