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
    TokenUsage
)

__all__ = [
    "SettingsDataResponse",
    "UpdatableSettingsData",
    "DBSettingsSchema",
    "AIServiceSettingsInput",
    "AIServiceSettingsStored",
    "DatabaseSettings", # Add DatabaseSettings to __all__
    "ConnectionInfo",
    "TunnelStatus",
    "User",
    "UserCreate",
    "UserUpdate",
    "UserInDB",
    "ConnectedDevice",
    "Document",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentStatus",
    "DocumentAnalysis",
    "LogEntryCreate",
    "LogEntryDB",
    "LogEntryPublic",
    "LogLevel",
    "Token",
    "TokenData",
    "SystemStats",
    "ActivityItem",
    "RecentActivities",
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
] 