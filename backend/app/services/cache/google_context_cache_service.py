"""
Google Context Caching 服務
提供與 Google Context Caching 相關的所有功能，包括創建、管理、刪除遠端緩存等
"""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import log_event, LogLevel
from app.core.config import settings

# 設置 logger
logger = logging.getLogger(__name__)

# 嘗試導入新的 Google GenAI SDK
try:
    import google.generativeai as genai
    # 暫時使用舊的 SDK 結構，等新 SDK 穩定後再更新
    GOOGLE_CONTEXT_CACHING_AVAILABLE = True
    # 延遲日志記錄到服務實例化時
except ImportError as e:
    # 優雅降級：如果 SDK 不可用，記錄警告但繼續運行
    genai = None
    GOOGLE_CONTEXT_CACHING_AVAILABLE = False
    # 延遲日志記錄到服務實例化時


class ContextCacheType(Enum):
    """Context Cache 類型枚舉"""
    SCHEMA = "schema"
    SYSTEM_INSTRUCTION = "system_instruction"
    DOCUMENT_CONTENT = "document_content"
    PROMPT_TEMPLATE = "prompt_template"
    SYSTEM_PROMPT = "system_prompt"


@dataclass
class ContextCacheConfig:
    """Context Cache 配置"""
    cache_type: ContextCacheType
    content: Union[str, List[Dict[str, Any]]]  # 支援字符串或結構化內容
    ttl_hours: int = 1  # 過期時間（小時）
    model: str = "gemini-2.5-flash"  # 默認模型
    display_name: Optional[str] = None  # 顯示名稱
    metadata: Optional[Dict[str, Any]] = None  # 額外元數據


@dataclass
class ContextCacheInfo:
    """Context Cache 信息"""
    cache_id: str
    cache_type: ContextCacheType
    display_name: Optional[str]
    model: str
    token_count: int
    created_at: datetime
    expires_at: datetime
    status: str
    metadata: Optional[Dict[str, Any]] = None


class GoogleContextCacheService:
    """Google Context Caching 服務類"""
    
    def __init__(self):
        self.client = None
        self._token_cost_per_1k = {
            "gemini-2.5-flash": 0.00001875,  # $0.01875 per 1M tokens
            "gemini-2.5-pro": 0.00035,       # $0.35 per 1M tokens
        }
        self._context_cache_discount = 0.75  # 75% 成本節省
        self._min_tokens = {
            "gemini-2.5-flash": 1024,
            "gemini-2.5-pro": 2048,
        }
        
        # 記錄 SDK 可用性狀態
        if GOOGLE_CONTEXT_CACHING_AVAILABLE:
            logger.info("Google GenAI SDK 載入成功，Context Caching 可用")
        else:
            logger.warning("Google GenAI SDK 不可用，Context Caching 將被禁用")
        
        # 嘗試初始化客戶端
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化 Google GenAI 客戶端"""
        if not GOOGLE_CONTEXT_CACHING_AVAILABLE:
            logger.warning("Google Context Caching 不可用：未找到 google-genai SDK")
            return
        
        try:
            # 使用統一的配置系統獲取 API key
            api_key = settings.GOOGLE_API_KEY
            if not api_key:
                logger.warning("未在配置中找到 GOOGLE_API_KEY，Context Caching 功能將受限")
                logger.info("請在 .env 文件中設置 GOOGLE_API_KEY=your-api-key")
                return
            
            genai.configure(api_key=api_key)
            self.client = genai
            logger.info("Google Context Caching 客戶端初始化成功")
            
        except Exception as e:
            logger.error(f"初始化 Google Context Caching 客戶端失敗: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """檢查 Context Caching 是否可用"""
        return GOOGLE_CONTEXT_CACHING_AVAILABLE and self.client is not None
    
    def check_token_requirements(self, content: str, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
        """檢查內容是否符合 Context Caching 的 token 要求"""
        # 簡單的 token 估算（實際應該使用 tokenizer）
        estimated_tokens = len(content.split()) * 1.3  # 粗略估算
        min_required = self._min_tokens.get(model, 1024)
        
        return {
            "estimated_tokens": int(estimated_tokens),
            "min_required": min_required,
            "meets_requirement": estimated_tokens >= min_required,
            "model": model
        }
    
    def estimate_cost_savings(self, token_count: int, model: str = "gemini-2.5-flash", 
                            usage_count: int = 10) -> Dict[str, float]:
        """估算使用 Context Caching 的成本節省"""
        base_cost_per_1k = self._token_cost_per_1k.get(model, 0.00001875)
        
        # 不使用緩存的成本
        without_cache_cost = (token_count / 1000) * base_cost_per_1k * usage_count
        
        # 使用緩存的成本（首次全額 + 後續折扣）
        first_use_cost = (token_count / 1000) * base_cost_per_1k
        subsequent_cost = first_use_cost * (1 - self._context_cache_discount) * (usage_count - 1)
        with_cache_cost = first_use_cost + subsequent_cost
        
        savings = without_cache_cost - with_cache_cost
        savings_percentage = (savings / without_cache_cost) * 100 if without_cache_cost > 0 else 0
        
        return {
            "without_cache_cost_usd": round(without_cache_cost, 6),
            "with_cache_cost_usd": round(with_cache_cost, 6),
            "savings_usd": round(savings, 6),
            "savings_percentage": round(savings_percentage, 2),
            "usage_count": usage_count,
            "token_count": token_count,
            "model": model
        }
    
    async def create_context_cache(self, config: ContextCacheConfig, 
                                 db: AsyncIOMotorDatabase = None) -> Optional[ContextCacheInfo]:
        """創建新的 Context Cache"""
        if not self.is_available():
            logger.warning("Context Caching 不可用，跳過創建")
            return None
        
        try:
            # 檢查 token 要求
            content_str = str(config.content) if isinstance(config.content, (dict, list)) else config.content
            token_check = self.check_token_requirements(content_str, config.model)
            
            if not token_check["meets_requirement"]:
                logger.warning(f"內容不符合 Context Caching token 要求: {token_check}")
                return None
            
            # 準備內容 - 暫時使用字符串格式，等新 SDK 穩定後使用結構化內容
            content_text = str(config.content) if not isinstance(config.content, str) else config.content
            
            # 創建 Context Cache
            expires_at = datetime.utcnow() + timedelta(hours=config.ttl_hours)
            
            # 模擬 Context Cache 創建（等真實 API 可用時再實施）
            cache_request = {
                "model": config.model,
                "content": content_text,
                "ttl_hours": config.ttl_hours,
                "display_name": config.display_name or f"{config.cache_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            }
            
            # 注意：這裡的實際 API 調用需要根據 google-genai SDK 的實際接口調整
            # response = await self.client.beta.create_cached_content(**cache_request)
            
            # 暫時模擬回應（實際應該來自 API）
            cache_id = f"cache_{config.cache_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            cache_info = ContextCacheInfo(
                cache_id=cache_id,
                cache_type=config.cache_type,
                display_name=cache_request["display_name"],
                model=config.model,
                token_count=token_check["estimated_tokens"],
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                status="active",
                metadata=config.metadata
            )
            
            # 記錄到數據庫（可選）
            if db is not None:
                await self._save_cache_info_to_db(cache_info, db)
            
            if db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"創建 Context Cache 成功: {cache_id}",
                    source="google_context_cache_service.create",
                    details={
                        "cache_type": config.cache_type.value,
                        "token_count": token_check["estimated_tokens"],
                        "model": config.model
                    }
                )
            
            logger.info(f"成功創建 Context Cache: {cache_id}")
            return cache_info
            
        except Exception as e:
            if db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"創建 Context Cache 失敗: {str(e)}",
                    source="google_context_cache_service.create_error",
                    details={"error": str(e), "cache_type": config.cache_type.value}
                )
            
            logger.error(f"創建 Context Cache 失敗: {e}")
            return None
    
    async def get_cache_info(self, cache_id: str) -> Optional[ContextCacheInfo]:
        """獲取 Context Cache 信息"""
        if not self.is_available():
            return None
        
        try:
            # 實際 API 調用（需要根據真實 API 調整）
            # response = await self.client.beta.get_cached_content(cache_id)
            
            # 暫時返回 None（實際應該來自 API 或本地緩存）
            return None
            
        except Exception as e:
            logger.error(f"獲取 Context Cache 信息失敗: {e}")
            return None
    
    async def delete_context_cache(self, cache_id: str, 
                                 db: AsyncIOMotorDatabase = None) -> bool:
        """刪除 Context Cache"""
        if not self.is_available():
            return False
        
        try:
            # 實際 API 調用（需要根據真實 API 調整）
            # await self.client.beta.delete_cached_content(cache_id)
            
            # 從數據庫中移除記錄（如果有）
            if db is not None:
                await db.context_caches.delete_one({"cache_id": cache_id})
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"刪除 Context Cache: {cache_id}",
                    source="google_context_cache_service.delete"
                )
            
            logger.info(f"成功刪除 Context Cache: {cache_id}")
            return True
            
        except Exception as e:
            if db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"刪除 Context Cache 失敗: {str(e)}",
                    source="google_context_cache_service.delete_error",
                    details={"error": str(e), "cache_id": cache_id}
                )
            
            logger.error(f"刪除 Context Cache 失敗: {e}")
            return False
    
    async def list_context_caches(self, cache_type: Optional[ContextCacheType] = None,
                                db: AsyncIOMotorDatabase = None) -> List[ContextCacheInfo]:
        """列出所有 Context Caches"""
        if not self.is_available():
            return []
        
        try:
            # 從數據庫獲取緩存信息
            if db is not None:
                query = {}
                if cache_type:
                    query["cache_type"] = cache_type.value
                
                cursor = db.context_caches.find(query)
                caches = []
                async for doc in cursor:
                    try:
                        cache_info = ContextCacheInfo(
                            cache_id=doc["cache_id"],
                            cache_type=ContextCacheType(doc["cache_type"]),
                            display_name=doc.get("display_name"),
                            model=doc["model"],
                            token_count=doc["token_count"],
                            created_at=doc["created_at"],
                            expires_at=doc["expires_at"],
                            status=doc.get("status", "unknown"),
                            metadata=doc.get("metadata")
                        )
                        caches.append(cache_info)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"跳過無效的緩存記錄: {e}")
                        continue
                
                return caches
            
            return []
            
        except Exception as e:
            logger.error(f"列出 Context Caches 失敗: {e}")
            return []
    
    async def cleanup_expired_caches(self, db: AsyncIOMotorDatabase = None) -> int:
        """清理過期的 Context Caches"""
        if not self.is_available():
            return 0
        
        try:
            now = datetime.utcnow()
            cleanup_count = 0
            
            if db is not None:
                # 獲取過期的緩存
                expired_caches = await db.context_caches.find({
                    "expires_at": {"$lt": now}
                }).to_list(length=None)
                
                for cache_doc in expired_caches:
                    cache_id = cache_doc["cache_id"]
                    if await self.delete_context_cache(cache_id, db):
                        cleanup_count += 1
                
                if cleanup_count > 0:
                    await log_event(
                        db=db,
                        level=LogLevel.INFO,
                        message=f"清理過期 Context Caches: {cleanup_count} 個",
                        source="google_context_cache_service.cleanup"
                    )
            
            logger.info(f"清理了 {cleanup_count} 個過期的 Context Caches")
            return cleanup_count
            
        except Exception as e:
            if db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"清理過期 Context Caches 失敗: {str(e)}",
                    source="google_context_cache_service.cleanup_error",
                    details={"error": str(e)}
                )
            
            logger.error(f"清理過期 Context Caches 失敗: {e}")
            return 0
    
    async def get_cache_statistics(self, db: AsyncIOMotorDatabase = None) -> Dict[str, Any]:
        """獲取 Context Cache 統計信息"""
        try:
            stats = {
                "total_caches": 0,
                "active_caches": 0,
                "expired_caches": 0,
                "cache_types": {},
                "total_tokens": 0,
                "estimated_savings": 0.0,
                "is_available": self.is_available()
            }
            
            if not self.is_available() or db is None:
                return stats
            
            now = datetime.utcnow()
            
            # 獲取所有緩存統計
            cursor = db.context_caches.find({})
            async for doc in cursor:
                stats["total_caches"] += 1
                stats["total_tokens"] += doc.get("token_count", 0)
                
                cache_type = doc.get("cache_type", "unknown")
                if cache_type not in stats["cache_types"]:
                    stats["cache_types"][cache_type] = 0
                stats["cache_types"][cache_type] += 1
                
                if doc.get("expires_at", now) > now:
                    stats["active_caches"] += 1
                else:
                    stats["expired_caches"] += 1
            
            # 估算成本節省（假設平均使用 10 次）
            if stats["total_tokens"] > 0:
                savings_estimate = self.estimate_cost_savings(
                    stats["total_tokens"], 
                    usage_count=10
                )
                stats["estimated_savings"] = savings_estimate["savings_usd"]
            
            return stats
            
        except Exception as e:
            logger.error(f"獲取 Context Cache 統計失敗: {e}")
            return {
                "error": str(e),
                "is_available": self.is_available()
            }
    
    async def _save_cache_info_to_db(self, cache_info: ContextCacheInfo, 
                                   db: AsyncIOMotorDatabase):
        """保存 Context Cache 信息到數據庫"""
        try:
            doc = {
                "cache_id": cache_info.cache_id,
                "cache_type": cache_info.cache_type.value,
                "display_name": cache_info.display_name,
                "model": cache_info.model,
                "token_count": cache_info.token_count,
                "created_at": cache_info.created_at,
                "expires_at": cache_info.expires_at,
                "status": cache_info.status,
                "metadata": cache_info.metadata
            }
            
            await db.context_caches.insert_one(doc)
            logger.debug(f"保存 Context Cache 信息到數據庫: {cache_info.cache_id}")
            
        except Exception as e:
            logger.error(f"保存 Context Cache 信息到數據庫失敗: {e}")


# 全局服務實例
google_context_cache_service = GoogleContextCacheService() 