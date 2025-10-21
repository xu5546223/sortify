from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID, uuid4

class ConversationMessage(BaseModel):
    """單條對話消息"""
    role: str = Field(..., description="消息角色：'user' 或 'assistant'")
    content: str = Field(..., description="消息內容")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="消息時間戳")
    tokens_used: Optional[int] = Field(None, description="該消息使用的 token 數量")
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "這是一個問題",
                "timestamp": "2024-01-01T12:00:00Z",
                "tokens_used": 100
            }
        }

class ConversationBase(BaseModel):
    """對話基礎模型"""
    title: str = Field(..., description="對話標題")
    user_id: UUID = Field(..., description="用戶ID")

class ConversationCreate(BaseModel):
    """創建對話請求"""
    first_question: str = Field(..., description="第一個問題，將用作對話標題")
    
    class Config:
        json_schema_extra = {
            "example": {
                "first_question": "如何使用這個系統？"
            }
        }

class ConversationUpdate(BaseModel):
    """更新對話請求"""
    title: Optional[str] = Field(None, description="更新對話標題")

class ConversationInDB(ConversationBase):
    """數據庫中的對話模型"""
    id: UUID = Field(default_factory=uuid4, description="對話唯一標識符")
    messages: List[ConversationMessage] = Field(default_factory=list, description="對話消息列表")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="創建時間")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="最後更新時間")
    message_count: int = Field(default=0, description="消息總數")
    total_tokens: int = Field(default=0, description="累計使用的 token 數量")
    
    # 對話級別的文檔緩存
    cached_documents: List[str] = Field(default_factory=list, description="對話中已查詢過的文檔ID列表")
    cached_document_data: Optional[dict] = Field(default=None, description="緩存的文檔詳細數據")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "如何使用這個系統？",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "messages": [],
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z",
                "message_count": 0,
                "total_tokens": 0
            }
        }

class Conversation(BaseModel):
    """API 返回的對話模型（不包含完整消息列表）"""
    id: UUID = Field(..., description="對話唯一標識符")
    title: str = Field(..., description="對話標題")
    user_id: UUID = Field(..., description="用戶ID")
    created_at: datetime = Field(..., description="創建時間")
    updated_at: datetime = Field(..., description="最後更新時間")
    message_count: int = Field(..., description="消息總數")
    total_tokens: int = Field(..., description="累計使用的 token 數量")
    cached_documents: List[str] = Field(default_factory=list, description="已緩存的文檔ID")
    
    class Config:
        from_attributes = True

class ConversationWithMessages(Conversation):
    """包含完整消息的對話模型"""
    messages: List[ConversationMessage] = Field(..., description="對話消息列表")
    
    class Config:
        from_attributes = True

class ConversationListResponse(BaseModel):
    """對話列表響應"""
    conversations: List[Conversation] = Field(..., description="對話列表")
    total: int = Field(..., description="總數量")

