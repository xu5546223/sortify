from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "Sortify AI Assistant Backend"
    DEBUG: bool = False
    # AI 服務相關設定
    GOOGLE_API_KEY: Optional[str] = None
    DEFAULT_AI_MODEL: str = "gemini-1.5-flash"
    AI_TEMPERATURE: float = 0.7
    AI_TOP_P: float = 1.0
    AI_TOP_K: int = 40
    AI_MAX_OUTPUT_TOKENS: int = 10000
    AI_MAX_OUTPUT_TOKENS_IMAGE: int = 4096
    AI_MAX_INPUT_CHARS_TEXT_ANALYSIS: int = 100000 # 新增：文本分析最大輸入字符數 (例如約 250k tokens for Gemini 1.5 Pro)

    # MongoDB 相關設定
    MONGODB_URL: str
    DB_NAME: str # 原為 MONGODB_DATABASE，更名以保持一致性
    
    # Redis 相關設定（用於對話緩存）
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_CONVERSATION_TTL: int = 3600  # 對話緩存 TTL（秒），預設 1 小時
    REDIS_ENABLED: bool = True  # 是否啟用 Redis 緩存

    # 向量資料庫相關設定 (使用 ChromaDB)
    VECTOR_DB_PATH: str = "./data/chromadb"
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"  # 多語言 Embedding 模型（100+ 語言）
    EMBEDDING_MAX_LENGTH: int = 512  # Embedding最大輸入長度
    VECTOR_SEARCH_TOP_K: int = 10  # 預設向量搜索返回結果數量
    VECTOR_SIMILARITY_THRESHOLD: float = 0.5  # 預設相似度閾值
    
    # Cross-Encoder Reranker 設定
    RERANKER_ENABLED: bool = True  # 是否啟用 Cross-Encoder 重排序
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"  # 多語言 Reranker 模型
    RERANKER_TOP_K: int = 20  # 對 top-k 結果進行重排序
    
    # 文本分塊策略設定
    VECTOR_CHUNK_SIZE: int = 512  # 每個文本塊的字符數
    VECTOR_CHUNK_OVERLAP: int = 50  # 文本塊之間的重疊字符數

    # AI 邏輯分塊向量化策略設定 (Phase 3)
    CHUNK_HYBRID_THRESHOLD: int = 350      # 低於此長度使用混合增強 (summary + content)
    CHUNK_SAFE_LENGTH: int = 480           # 單向量最大原文長度 (低於 512 留 buffer)
    SUB_CHUNK_OVERLAP: int = 50            # 子分塊重疊字符數
    USE_AI_LOGICAL_CHUNKS: bool = True     # 是否使用 AI 邏輯分塊 (False 則使用固定分塊)
    
    # 兩階段混合檢索設定
    VECTOR_SEARCH_STAGE1_TOP_K: int = 10  # 第一階段（粗篩選）返回的候選文檔數
    VECTOR_SEARCH_STAGE2_TOP_K: int = 5   # 第二階段（精排序）最終返回的結果數

    # AI 上下文文檔數量限制
    MAX_CONTEXT_DOCUMENTS: int = 20  # 傳遞給 AI 生成答案時的最大文檔數量（預設 10，建議 5-15）

    # 詳細查詢專用配置（更寬鬆的上下文限制）
    DETAIL_QUERY_MAX_CONTEXT_LENGTH: int = 80000  # 詳細查詢總上下文限制（80k 字符 ≈ 20k tokens）
    DETAIL_QUERY_MAX_CHARS_PER_DOC: int = 30000   # 詳細查詢單文檔字符限制（30k 字符）
    DETAIL_QUERY_ENABLE_SMART_TRUNCATION: bool = True  # 是否啟用智能截斷（False = 完整提供）

    # RRF 融合檢索設定
    RRF_K_CONSTANT: int = 20  # RRF 常數 k（優化後：原60→20）
    RRF_WEIGHTS: dict = {"summary": 2.5, "chunks": 1.0}  # 摘要和內容塊搜索的權重配置
    
    # 問題分類器設定
    QUESTION_CLASSIFIER_ENABLED: bool = True  # 是否啟用問題分類器
    QUESTION_CLASSIFIER_MODEL: str = "gemini-2.0-flash-exp"  # 分類器使用的模型
    QUESTION_CLASSIFIER_CONFIDENCE_THRESHOLD: float = 0.7  # 分類置信度閾值
    
    # 智能工作流設定
    ENABLE_INTELLIGENT_ROUTING: bool = True  # 啟用智能路由
    AUTO_APPROVE_SIMPLE_QUERIES: bool = True  # 自動批准簡單查詢
    ENABLE_GREETING_SHORTCUT: bool = True  # 啟用寒暄快速通道
    ENABLE_CHITCHAT_SHORTCUT: bool = True  # 啟用閒聊快速通道

    # 新增上傳目錄配置
    UPLOAD_DIR: str = "uploaded_files"

    # JWT 相關設定
    # !!! 請務必替換為一個安全的隨機字串，例如通過 `openssl rand -hex 32` 生成 !!!
    # !!! 例如: openssl rand -hex 32                                      !!!
    # !!! 將生成的金鑰儲存在您的 .env 檔案中，例如：                         !!!
    # !!! SECRET_KEY="your_generated_strong_random_hex_string"            !!!
    SECRET_KEY: str = "your-super-secret-and-long-random-string-generated-safely" # 請替換此預設值
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 # 例如 60 分鐘

    # Google OAuth 相關設定 (Gmail 集成)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/gmail-callback"
    
    # Gmail API 相關設定
    GMAIL_SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
    GMAIL_API_QUOTA_PER_USER: int = 250  # Gmail API 每個用戶的每日配額

    # CORS 相關設定
    # 在生產環境中，應明確指定您的前端域名，例如: ["https://your-frontend.com", "http://localhost:3000"]
    # 若要允許所有來源 (通常僅用於開發)，可以使用 ["*"]，但請謹慎使用。
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"] # 開發時常用的前端地址

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

settings = Settings() 