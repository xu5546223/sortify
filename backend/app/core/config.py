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

    # 向量資料庫相關設定 (使用 ChromaDB)
    VECTOR_DB_PATH: str = "./data/chromadb"
    EMBEDDING_MODEL: str = "paraphrase-multilingual-mpnet-base-v2"  # 預設使用多語言模型
    EMBEDDING_MAX_LENGTH: int = 512  # Embedding最大輸入長度
    VECTOR_SEARCH_TOP_K: int = 10  # 預設向量搜索返回結果數量
    VECTOR_SIMILARITY_THRESHOLD: float = 0.5  # 預設相似度閾值
    
    # 文本分塊策略設定
    VECTOR_CHUNK_SIZE: int = 512  # 每個文本塊的字符數
    VECTOR_CHUNK_OVERLAP: int = 50  # 文本塊之間的重疊字符數
    
    # 兩階段混合檢索設定
    VECTOR_SEARCH_STAGE1_TOP_K: int = 10  # 第一階段（粗篩選）返回的候選文檔數
    VECTOR_SEARCH_STAGE2_TOP_K: int = 5   # 第二階段（精排序）最終返回的結果數
    
    # RRF 融合檢索設定
    RRF_K_CONSTANT: int = 60  # RRF 常數 k，降低高排名影響力（標準值為60）
    RRF_WEIGHTS: dict = {"summary": 2.0, "chunks": 1.0}  # 摘要和內容塊搜索的權重配置

    # Cloudflare Tunnel (如果在此處管理)
    CLOUDFLARE_TUNNEL_URL: str | None = None

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