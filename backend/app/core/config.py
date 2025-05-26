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

    # Cloudflare Tunnel (如果在此處管理)
    CLOUDFLARE_TUNNEL_URL: str | None = None

    # 新增上傳目錄配置
    UPLOAD_DIR: str = "uploaded_files"

    # JWT 相關設定
    # !!! 請務必替換為一個安全的隨機字串，例如通過 `openssl rand -hex 32` 生成 !!!
    SECRET_KEY: str = "your-super-secret-and-long-random-string-generated-safely" # 請替換此預設值
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 # 例如 60 分鐘

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

settings = Settings() 