# This directory will contain Pydantic models 

from .system_models import (
    SettingsDataResponse, 
    ConnectionInfo, 
    TunnelStatus, 
    UpdatableSettingsData,
    DBSettingsSchema, # Exporting the DB schema as well, in case it's needed elsewhere
    AIServiceSettingsInput,
    AIServiceSettingsStored,
    DatabaseSettings # Add DatabaseSettings here
)
from .user_models import User, UserCreate, UserUpdate, UserInDB, ConnectedDevice
from .document_models import Document, DocumentCreate, DocumentUpdate, DocumentStatus, DocumentAnalysis
from .log_models import LogEntryCreate, LogEntryDB, LogEntryPublic, LogLevel
from .token_models import Token, TokenData
from .dashboard_models import SystemStats, ActivityItem, RecentActivities
from .vector_models import (
    VectorDocumentStatus,
    SemanticSummary,
    VectorRecord,
    SemanticSearchRequest,
    SemanticSearchResult,
    AIQARequest,
    AIQAResponse,
    QueryRewriteResult
)
# 簡化版AI模型（現在是主要版本）
from .ai_models_simplified import (
    FlexibleKeyInformation,
    FlexibleIntermediateAnalysis,
    AITextAnalysisOutput,
    AIImageAnalysisOutput,
    AIPromptRequest,
    TokenUsage,
    AIClusterLabelOutput
)
# 聚類模型
from .clustering_models import (
    ClusterInfo,
    ClusteringJobStatus,
    ClusterSummary
)
# 響應模型
from .response_models import (
    MessageResponse,
    BasicResponse,
    SuccessResponse,
    PaginatedResponse,
    StatusResponse,
    HealthCheckResponse
)
# 錯誤模型
from .error_models import (
    ErrorDetail,
    ErrorResponse,
    ValidationErrorResponse,
    ServiceHealthError,
    BatchOperationError,
    APIErrorResponse,
    DocumentErrorResponse,
    AIServiceErrorResponse,
    AuthErrorResponse
)

__all__ = [
    # 系統設定模型
    "SettingsDataResponse",
    "UpdatableSettingsData",
    "DBSettingsSchema",
    "AIServiceSettingsInput",
    "AIServiceSettingsStored",
    "DatabaseSettings",
    "ConnectionInfo",
    "TunnelStatus",
    # 用戶模型
    "User",
    "UserCreate",
    "UserUpdate",
    "UserInDB",
    "ConnectedDevice",
    # 文檔模型
    "Document",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentStatus",
    "DocumentAnalysis",
    # 日誌模型
    "LogEntryCreate",
    "LogEntryDB",
    "LogEntryPublic",
    "LogLevel",
    # 認證模型
    "Token",
    "TokenData",
    # 儀表板模型
    "SystemStats",
    "ActivityItem",
    "RecentActivities",
    # 響應模型
    "MessageResponse",
    "BasicResponse",
    "SuccessResponse",
    "PaginatedResponse",
    "StatusResponse",
    "HealthCheckResponse",
    # 錯誤模型
    "ErrorDetail",
    "ErrorResponse",
    "ValidationErrorResponse",
    "ServiceHealthError",
    "BatchOperationError",
    "APIErrorResponse",
    "DocumentErrorResponse",
    "AIServiceErrorResponse",
    "AuthErrorResponse",
    # 向量模型相關
    "VectorDocumentStatus",
    "SemanticSummary",
    "VectorRecord",
    "SemanticSearchRequest",
    "SemanticSearchResult",
    "AIQARequest",
    "AIQAResponse",
    "QueryRewriteResult",
    # 簡化版AI模型（主要版本）
    "FlexibleKeyInformation",
    "FlexibleIntermediateAnalysis",
    "AITextAnalysisOutput",
    "AIImageAnalysisOutput",
    "AIPromptRequest",
    "TokenUsage",
    "AIClusterLabelOutput",
    # 聚類模型
    "ClusterInfo",
    "ClusteringJobStatus",
    "ClusterSummary",
] 