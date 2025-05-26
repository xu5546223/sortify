from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class SystemStats(BaseModel):
    total_documents: int = Field(0, description="系統中的文件總數")
    processed_documents: int = Field(0, description="已成功處理/分析的文件數量")
    pending_documents: int = Field(0, description="等待處理的文件數量")
    total_registered_devices: int = Field(0, description="已註冊的裝置總數")
    active_connections: int = Field(0, description="當前活動的裝置連線數")
    total_storage_used_mb: float = Field(0.0, description="所有文件佔用的總儲存空間 (MB)")
    error_logs_last_24h: int = Field(0, description="過去24小時內的錯誤日誌數量")
    # Future stats can be added here, e.g.:
    # ai_analyses_triggered: int = Field(0, description="AI 分析觸發次數")
    # ai_tokens_consumed_total: int = Field(0, description="AI 服務消耗的總 Token 數")

    class Config:
        json_schema_extra = {
            "example": {
                "total_documents": 150,
                "processed_documents": 120,
                "pending_documents": 30,
                "total_registered_devices": 10,
                "active_connections": 3,
                "total_storage_used_mb": 512.75,
                "error_logs_last_24h": 5
            }
        }

class ActivityItem(BaseModel):
    id: UUID = Field(..., description="活動條目的唯一ID (通常來自日誌條目的ID)")
    timestamp: datetime = Field(..., description="活動發生的時間戳記")
    activity_type: str = Field(..., description="活動類型 (例如: 'documents_api', 'user_login', 'system_event')")
    summary: str = Field(..., description="活動的簡短描述或日誌訊息")
    user_id: Optional[str] = Field(None, description="與此活動相關的使用者ID (如果適用)")
    device_id: Optional[str] = Field(None, description="與此活動相關的裝置ID (如果適用)")
    related_item_id: Optional[str] = Field(None, description="與此活動相關的項目ID (例如文件ID, 使用者ID)")
    details: Optional[Dict[str, Any]] = Field(None, description="包含有關活動的額外結構化數據")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "timestamp": "2023-10-26T10:30:00Z",
                "activity_type": "document_uploaded",
                "summary": "用戶 'john.doe' 上傳了文件 'report.pdf'",
                "user_id": "user_abc_123",
                "device_id": "device_xyz_789",
                "related_item_id": "doc_def_456",
                "details": {"filename": "report.pdf", "size_bytes": 102400}
            }
        }

class RecentActivities(BaseModel):
    activities: List[ActivityItem] = Field(..., description="最近活動的列表")
    total_count: int = Field(..., description="符合查詢條件的活動總數 (用於分頁)")
    limit: int = Field(..., description="本次查詢返回的活動數量上限")
    skip: int = Field(..., description="本次查詢跳過的活動數量")

    class Config:
        json_schema_extra = {
            "example": {
                "activities": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "timestamp": "2023-10-26T10:30:00Z",
                        "activity_type": "document_uploaded",
                        "summary": "用戶 'john.doe' 上傳了文件 'report.pdf'",
                        "user_id": "user_abc_123"
                    }
                ],
                "total_count": 100,
                "limit": 20,
                "skip": 0
            }
        } 