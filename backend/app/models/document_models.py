from pydantic import BaseModel, Field, HttpUrl, root_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"  # 文件已上傳，等待處理
    PENDING_EXTRACTION = "pending_extraction"  # 等待文本提取
    TEXT_EXTRACTED = "text_extracted"  # 文本已提取
    EXTRACTION_FAILED = "extraction_failed"  # 提取失敗
    PENDING_ANALYSIS = "pending_analysis"  # 等待 AI 分析
    ANALYZING = "analyzing"  # 分析中
    ANALYSIS_COMPLETED = "analysis_completed"  # AI 分析完成
    ANALYSIS_FAILED = "analysis_failed"  # 分析失敗
    PROCESSING_ERROR = "processing_error"  # 處理過程中發生錯誤
    COMPLETED = "completed"  # 所有處理完成 (可能包括分析或僅文本提取)

class VectorStatus(str, Enum):
    NOT_VECTORIZED = "not_vectorized"
    PROCESSING = "processing"
    VECTORIZED = "vectorized"
    FAILED = "vectorization_failed"

class DocumentBase(BaseModel):
    filename: str = Field(..., description="原始文件名")
    file_type: Optional[str] = Field(None, description="文件MIME類型")
    size: Optional[int] = Field(None, description="文件大小 (bytes)")
    uploader_device_id: Optional[str] = Field(None, description="上傳設備的ID")
    owner_id: uuid.UUID = Field(..., description="文件擁有者的用戶ID")
    
    tags: Optional[List[str]] = Field(default_factory=list, description="用戶定義的標籤")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="其他元數據，例如圖片的EXIF信息")

class DocumentCreate(DocumentBase):
    # 在創建時，status 通常是 UPLOADED
    # vector_status 預設為 NOT_VECTORIZED
    # extracted_text, analysis_result 等欄位在後續處理中填充
    pass

class DocumentAnalysis(BaseModel):
    tokens_used: Optional[int] = Field(None, description="本次分析消耗的Token數量")
    analysis_started_at: Optional[datetime] = None
    analysis_completed_at: Optional[datetime] = None
    error_message: Optional[str] = Field(None, description="AI分析過程中的錯誤信息 (來自AI服務或處理流程)")

    ai_analysis_output: Optional[Dict[str, Any]] = Field(None, description="AI服務返回的完整結構化分析結果 (JSON)")
    analysis_model_used: Optional[str] = Field(None, description="用於本次分析的AI模型")

class DocumentInDBBase(DocumentBase):
    id: uuid.UUID = Field(description="文件唯一ID")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="文件記錄創建時間")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="文件記錄最後更新時間")
    
    status: DocumentStatus = Field(DocumentStatus.UPLOADED, description="文件處理狀態")
    vector_status: VectorStatus = Field(VectorStatus.NOT_VECTORIZED, description="文檔的向量化狀態")
    
    # 儲存路徑相關，可以是相對於某個基準目錄的路徑，或完整的路徑/URI
    # 具體儲存策略待定，例如可以是 file_path 或 storage_uri
    file_path: Optional[str] = Field(None, description="文件在伺服器上的儲存路徑")

    extracted_text: Optional[str] = Field(None, description="從文件中提取的文本內容")
    text_extraction_completed_at: Optional[datetime] = None

    # 行號映射 (用於 AI 邏輯分塊的座標系統)
    line_mapping: Optional[Dict[str, Any]] = Field(None, description="行號到字符位置的映射")
    # line_mapping 結構:
    # {
    #   "L001": {
    #     "local_index": 0,
    #     "global_line": 1,
    #     "char_start": 0,
    #     "char_end": 45,
    #     "length": 45,
    #     "content_preview": "第一行內容..."
    #   },
    #   "L002": {...}
    # }

    analysis: Optional[DocumentAnalysis] = Field(None, description="AI分析結果")
    
    error_details: Optional[str] = Field(None, description="處理過程中的詳細錯誤信息")

    # 新增 Gmail 相關字段
    email_source: Optional[str] = Field(None, description="郵件來源 (gmail, custom)")
    email_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Gmail 郵件元數據 (email_id, thread_id, from, to, 等)"
    )
    email_synced_at: Optional[datetime] = Field(None, description="郵件同步時間")
    
    # Stage 2: Enriched data (語義豐富化數據)
    # 注意: raw_text 使用現有的 extracted_text 欄位
    enriched_data: Optional[Dict[str, Any]] = Field(None, description="語義豐富化數據")
    # enriched_data 結構:
    # {
    #   "title": str,  # AI生成的標題
    #   "summary": str,  # 1-2句話摘要
    #   "entities": {
    #     "vendor": str,  # 店家/機構
    #     "people": List[str],  # 人物
    #     "locations": List[str],  # 地點
    #     "organizations": List[str],  # 機構
    #     "items": List[str],  # 品項清單
    #     "amounts": List[Dict],  # [{"value": 80, "currency": "TWD"}]
    #     "dates": List[str]  # ISO格式日期
    #   },
    #   "keywords": List[str],  # 5-7個關鍵詞
    #   "embedding_generated": bool  # 是否已生成embedding
    # }
    
    # Stage 4: Dynamic clustering (動態聚類)
    cluster_info: Optional[Dict[str, Any]] = Field(None, description="聚類信息")
    # cluster_info 結構:
    # {
    #   "cluster_id": str,  # 如 "cluster_user123_0"
    #   "cluster_name": str,  # AI生成的分類名稱
    #   "cluster_confidence": float,  # 0.0-1.0
    #   "clustered_at": datetime,
    #   "clustering_version": str  # 如 "v1.0"
    # }
    
    clustering_status: str = Field("pending", description="聚類狀態: pending/clustered/excluded")

    @root_validator(pre=True)
    @classmethod
    def _set_id_from_underscore_id(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        underscore_id = values.pop("_id", None)
        object_id = values.pop("id", None)

        target_id_value = None
        if underscore_id is not None:
            target_id_value = underscore_id
        elif object_id is not None:
            target_id_value = object_id
        
        if target_id_value is not None:
            if isinstance(target_id_value, uuid.UUID):
                values["id"] = target_id_value
            elif isinstance(target_id_value, str):
                try:
                    values["id"] = uuid.UUID(target_id_value)
                except ValueError:
                    raise ValueError(f"ID field '{target_id_value}' is a string but not a valid UUID.")
            else:
                try:
                    values["id"] = uuid.UUID(str(target_id_value))
                except ValueError:
                    raise ValueError(f"ID field '{target_id_value}' (type: {type(target_id_value)}) could not be converted to UUID.")
        
        if values.get("id") is None and underscore_id is None and object_id is None:
            pass
        return values

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            uuid.UUID: lambda v: str(v)
        }

class Document(DocumentInDBBase):
    """用於API響應的模型"""
    pass

class PaginatedDocumentResponse(BaseModel):
    items: List[Document]
    total: int

# 新增用於批量刪除的請求模型
class BatchDeleteRequest(BaseModel):
    document_ids: List[uuid.UUID]

# 新增用於批量刪除的回應模型
class BatchDeleteResponseDetail(BaseModel):
    id: uuid.UUID
    status: str  # 例如 "deleted", "not_found", "forbidden", "error"
    message: Optional[str] = None

class BatchDeleteDocumentsResponse(BaseModel):
    success: bool
    message: str
    processed_count: int
    success_count: int
    details: List[BatchDeleteResponseDetail]

class DocumentPreviewInfo(BaseModel):
    """用於API響應的模型"""
    pass

class DocumentUpdate(BaseModel):
    """用於更新文件信息的模型，只包含允許客戶端修改的字段"""
    filename: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    # status 和 vector_status 通常由後端服務更新
    # status: Optional[DocumentStatus] = None 
    # vector_status: Optional[VectorStatus] = None 
    
    trigger_content_processing: Optional[bool] = Field(None, description="設為true以觸發文件內容處理(文本提取或AI圖片分析)")

    ai_ensure_chinese_output: Optional[bool] = Field(None, description="是否確保AI使用中文輸出")
    ai_model_preference: Optional[str] = Field(None, description="AI模型偏好")
    ai_max_output_tokens: Optional[int] = Field(None, description="AI最大輸出Token數")

    updated_at: datetime = Field(default_factory=datetime.utcnow) 