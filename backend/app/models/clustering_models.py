"""
聚類相關的數據模型
用於動態文檔分類系統
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


class ClusterInfo(BaseModel):
    """聚類信息模型 - 儲存在MongoDB的clusters集合中"""
    cluster_id: str = Field(..., description="聚類ID,格式: cluster_{owner_id}_{序號}")
    cluster_name: str = Field(..., description="AI生成的聚類名稱")
    owner_id: uuid.UUID = Field(..., description="所屬用戶ID")
    document_count: int = Field(0, description="包含的文檔數量")
    representative_documents: List[str] = Field(default_factory=list, description="代表性文檔ID列表(最多10個)")
    keywords: List[str] = Field(default_factory=list, description="聚類關鍵詞")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="創建時間")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="最後更新時間")
    clustering_version: str = Field("v1.0", description="聚類算法版本")
    
    # 階層結構相關 (用於兩級聚類)
    parent_cluster_id: Optional[str] = Field(None, description="父聚類ID(用於階層結構)")
    level: int = Field(0, description="聚類層級(0=根層級/大類,1=子層級/細分類)")
    subclusters: List[str] = Field(default_factory=list, description="子聚類ID列表")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            uuid.UUID: lambda v: str(v)
        }


class ClusteringJobStatus(BaseModel):
    """聚類任務狀態 - 用於追蹤聚類任務執行情況"""
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="任務ID")
    owner_id: uuid.UUID = Field(..., description="用戶ID")
    status: str = Field("pending", description="任務狀態: pending/running/completed/failed")
    total_documents: int = Field(0, description="總文檔數")
    processed_documents: int = Field(0, description="已處理文檔數")
    clusters_created: int = Field(0, description="創建的聚類數量")
    started_at: Optional[datetime] = Field(None, description="開始時間")
    completed_at: Optional[datetime] = Field(None, description="完成時間")
    error_message: Optional[str] = Field(None, description="錯誤信息")
    progress_percentage: float = Field(0.0, description="進度百分比")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            uuid.UUID: lambda v: str(v)
        }
    
    def update_progress(self):
        """更新進度百分比"""
        if self.total_documents > 0:
            self.progress_percentage = (self.processed_documents / self.total_documents) * 100


class ClusterSummary(BaseModel):
    """聚類摘要 - 用於API響應,提供簡化的聚類信息"""
    cluster_id: str = Field(..., description="聚類ID")
    cluster_name: str = Field(..., description="聚類名稱")
    document_count: int = Field(0, description="文檔數量")
    keywords: List[str] = Field(default_factory=list, description="關鍵詞列表")
    created_at: Optional[datetime] = Field(None, description="創建時間")
    updated_at: Optional[datetime] = Field(None, description="更新時間")
    
    # 階層結構相關
    parent_cluster_id: Optional[str] = Field(None, description="父聚類ID")
    level: int = Field(0, description="聚類層級")
    subclusters: List[str] = Field(default_factory=list, description="子聚類ID列表")
    subcluster_summaries: Optional[List['ClusterSummary']] = Field(None, description="子聚類摘要(遞歸結構)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# 更新模型以支持遞歸引用
ClusterSummary.model_rebuild()

