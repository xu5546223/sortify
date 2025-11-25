"""
上下文管理統一配置

集中管理所有與上下文、歷史對話、文檔池相關的配置參數
"""
from pydantic_settings import BaseSettings


class ContextConfig(BaseSettings):
    """上下文管理配置"""
    
    # ==================== 歷史對話配置 ====================
    # 最大保留消息數（超過此數量會自動移除最舊的消息）
    MAX_MESSAGES_PER_CONVERSATION: int = 20
    
    # 載入上下文時的默認歷史消息數
    DEFAULT_HISTORY_LIMIT: int = 5
    
    # 意圖分類時載入的歷史消息數（需要更多上下文理解意圖）
    CLASSIFICATION_HISTORY_LIMIT: int = 10
    
    # ==================== 內容截斷配置 ====================
    # 意圖分類時的單條消息最大長度
    CLASSIFICATION_CONTENT_MAX_LENGTH: int = 500
    
    # 生成答案時的單條消息最大長度（保留更多信息）
    ANSWER_GEN_CONTENT_MAX_LENGTH: int = 3000
    
    # 澄清問題時的單條消息最大長度
    CLARIFICATION_CONTENT_MAX_LENGTH: int = 1500
    
    # 列表預覽/摘要顯示的最大長度
    PREVIEW_MAX_LENGTH: int = 200
    
    # 用戶問題最大長度（分類時）
    USER_QUESTION_MAX_LENGTH: int = 300
    
    # AI 回答最大長度（分類時，普通回答）
    AI_ANSWER_MAX_LENGTH: int = 800
    
    # AI 回答最大長度（分類時，包含文檔引用的回答）
    AI_ANSWER_WITH_CITATION_MAX_LENGTH: int = 600
    
    # chunk 摘要最大長度
    CHUNK_SUMMARY_MAX_LENGTH: int = 500
    
    # 文檔提取文本預覽長度
    EXTRACTED_TEXT_PREVIEW_LENGTH: int = 1000
    
    # ==================== 文檔池配置 ====================
    # 文檔池最大大小
    MAX_DOCUMENT_POOL_SIZE: int = 20
    
    # 最低相關性分數（低於此分數的文檔會被清理）
    MIN_RELEVANCE_SCORE: float = 0.35
    
    # 最大閒置輪次（超過此輪次未訪問的低分文檔會被清理）
    MAX_IDLE_ROUNDS: int = 5
    
    # 相關性衰減率（每輪衰減的分數）
    RELEVANCE_DECAY_RATE: float = 0.1
    
    class Config:
        env_prefix = "CONTEXT_"  # 環境變量前綴，如 CONTEXT_MAX_MESSAGES_PER_CONVERSATION


# 創建全局配置實例
context_config = ContextConfig()
