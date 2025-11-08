"""
後台任務模型
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    """任務狀態"""
    PENDING = "pending"  # 等待中
    RUNNING = "running"  # 執行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失敗


class TaskType(str, Enum):
    """任務類型"""
    QUESTION_GENERATION = "question_generation"  # 問題生成


class BackgroundTask(BaseModel):
    """後台任務"""
    task_id: str = Field(..., description="任務ID")
    task_type: TaskType = Field(..., description="任務類型")
    user_id: str = Field(..., description="用戶ID")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任務狀態")
    progress: int = Field(0, description="進度百分比 (0-100)")
    current_step: str = Field("", description="當前步驟描述")
    total_items: int = Field(0, description="總項目數")
    completed_items: int = Field(0, description="已完成項目數")
    result: Optional[Dict[str, Any]] = Field(None, description="任務結果")
    error_message: Optional[str] = Field(None, description="錯誤信息")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="創建時間")
    started_at: Optional[datetime] = Field(None, description="開始時間")
    completed_at: Optional[datetime] = Field(None, description="完成時間")


class TaskProgressUpdate(BaseModel):
    """任務進度更新"""
    progress: int = Field(..., description="進度百分比")
    current_step: str = Field(..., description="當前步驟")
    completed_items: int = Field(..., description="已完成項目數")


class TaskStatusResponse(BaseModel):
    """任務狀態響應"""
    task_id: str
    status: TaskStatus
    progress: int
    current_step: str
    total_items: int
    completed_items: int
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

