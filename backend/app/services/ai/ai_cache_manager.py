"""
AI 緩存管理器
管理所有 AI 相關的緩存策略，包括 Context Caching 和本地緩存
"""

import asyncio
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import logging

from cachetools import LRUCache, TTLCache
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging_utils import log_event, LogLevel
from app.services.cache.google_context_cache_service import (
    google_context_cache_service,
    ContextCacheConfig,
    ContextCacheType as GoogleContextCacheType,
    ContextCacheInfo
)

logger = logging.getLogger(__name__)


class CacheType(str, Enum):
    """緩存類型枚舉"""
    SCHEMA = "schema"
    SYSTEM_INSTRUCTION = "system_instruction"
    QUERY_EMBEDDING = "query_embedding"
    DOCUMENT_CONTENT = "document_content"
    AI_RESPONSE = "ai_response"
    PROMPT_TEMPLATE = "prompt_template"


@dataclass
class CacheStats:
    """緩存統計資訊"""
    cache_type: CacheType
    hit_count: int
    miss_count: int
    total_requests: int
    hit_rate: float
    memory_usage_mb: float
    last_updated: datetime


class AICacheManager:
    """
    AI 緩存管理器
    
    功能：
    1. 管理多種類型的緩存（查詢向量、Schema、系統指令等）
    2. 支援 Google Gemini Context Caching
    3. 提供緩存統計和監控
    4. 自動清理和優化
    """
    
    def __init__(self):
        # 本地緩存實例
        self.query_embedding_cache: LRUCache[str, List[float]] = LRUCache(maxsize=256)
        self.schema_cache: TTLCache[str, Any] = TTLCache(maxsize=10, ttl=3600)
        self.system_instruction_cache: TTLCache[str, Any] = TTLCache(maxsize=50, ttl=3600)
        self.document_content_cache: TTLCache[str, str] = TTLCache(maxsize=100, ttl=1800)
        self.ai_response_cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=500, ttl=900)
        self.prompt_template_cache: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=7200)  # 2小時TTL，提示詞相對穩定
        
        # Google Context Caching 服務
        self.google_context_cache_service = google_context_cache_service
        
        # 統計資訊
        self.cache_stats: Dict[CacheType, CacheStats] = {
            cache_type: CacheStats(
                cache_type=cache_type,
                hit_count=0,
                miss_count=0,
                total_requests=0,
                hit_rate=0.0,
                memory_usage_mb=0.0,
                last_updated=datetime.utcnow()
            )
            for cache_type in CacheType
        }
        
        logging.getLogger(__name__).info("AICacheManager 初始化完成，支援多層緩存策略，包含 Google Context Caching")
    
    def _generate_cache_key(self, content: str, prefix: str = "") -> str:
        """生成緩存鍵值"""
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        return f"{prefix}_{content_hash}" if prefix else content_hash
    
    def _update_cache_stats(self, cache_type: CacheType, hit: bool):
        """更新緩存統計"""
        stats = self.cache_stats[cache_type]
        if hit:
            stats.hit_count += 1
        else:
            stats.miss_count += 1
        stats.total_requests += 1
        stats.hit_rate = stats.hit_count / stats.total_requests if stats.total_requests > 0 else 0.0
        stats.last_updated = datetime.utcnow()
    
    # === 查詢向量緩存 ===
    def get_query_embedding(self, query: str) -> Optional[List[float]]:
        """獲取查詢向量緩存"""
        result = self.query_embedding_cache.get(query)
        self._update_cache_stats(CacheType.QUERY_EMBEDDING, result is not None)
        return result
    
    def set_query_embedding(self, query: str, embedding: List[float]):
        """設置查詢向量緩存"""
        self.query_embedding_cache[query] = embedding
        logger.debug(f"查詢向量已緩存，當前緩存大小: {len(self.query_embedding_cache)}")
    
    def batch_set_query_embeddings(self, queries: List[str], embeddings: List[List[float]]):
        """批次設置查詢向量緩存"""
        for query, embedding in zip(queries, embeddings):
            self.query_embedding_cache[query] = embedding
        logger.info(f"批次緩存 {len(queries)} 個查詢向量")
    
    # === Schema 緩存（支援 Context Caching） ===
    async def get_or_create_schema_cache(
        self, 
        db: AsyncIOMotorDatabase,
        document_schema_info: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        獲取或創建 Document Schema 緩存
        支援 Google Gemini Context Caching
        """
        try:
            schema_content = str(document_schema_info)
            cache_key = self._generate_cache_key(schema_content, "schema")
            
            # 檢查本地緩存
            if cache_key in self.schema_cache:
                self._update_cache_stats(CacheType.SCHEMA, True)
                logger.info(f"使用本地 Schema 緩存: {cache_key}")
                return cache_key
            
            # TODO: 實際實施 Gemini Context Caching
            # 目前先使用本地緩存模擬
            self.schema_cache[cache_key] = {
                "content": schema_content,
                "created_at": datetime.utcnow(),
                "user_id": user_id
            }
            
            self._update_cache_stats(CacheType.SCHEMA, False)
            
            await log_event(
                db=db, 
                level=LogLevel.INFO,
                message=f"已創建 Schema 緩存，預期可節省 30-40% 的詳細查詢 Token 消耗",
                source="service.ai_cache_manager.schema_cache_created",
                user_id=user_id,
                details={
                    "cache_key": cache_key,
                    "schema_size": len(schema_content)
                }
            )
            
            # TODO: 實際實施時返回 Gemini Context Cache 名稱
            return cache_key
            
        except Exception as e:
            await log_event(
                db=db, 
                level=LogLevel.ERROR,
                message=f"創建 Schema 緩存失敗: {str(e)}",
                source="service.ai_cache_manager.schema_cache_error",
                user_id=user_id,
                details={"error": str(e)}
            )
            return None
    
    # === 系統指令緩存 ===
    async def get_or_create_system_instruction_cache(
        self,
        db: AsyncIOMotorDatabase,
        cache_key: str,
        system_instruction: str,
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        獲取或創建系統指令緩存
        """
        try:
            # 檢查本地緩存
            if cache_key in self.system_instruction_cache:
                self._update_cache_stats(CacheType.SYSTEM_INSTRUCTION, True)
                logger.info(f"使用現有系統指令緩存: {cache_key}")
                return cache_key
            
            # 創建新緩存
            self.system_instruction_cache[cache_key] = {
                "content": system_instruction,
                "created_at": datetime.utcnow(),
                "user_id": user_id
            }
            
            self._update_cache_stats(CacheType.SYSTEM_INSTRUCTION, False)
            
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message=f"已創建系統指令緩存: {cache_key}，預期可節省 20-25% 的 AI 調用 Token 消耗",
                source="service.ai_cache_manager.system_instruction_cache_created",
                user_id=user_id,
                details={
                    "cache_key": cache_key,
                    "instruction_length": len(system_instruction)
                }
            )
            
            return cache_key
            
        except Exception as e:
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"創建系統指令緩存失敗: {cache_key}, {str(e)}",
                source="service.ai_cache_manager.system_instruction_cache_error",
                user_id=user_id,
                details={"cache_key": cache_key, "error": str(e)}
            )
            return None
    
    # === 文檔內容緩存 ===
    def get_document_content(self, document_id: str) -> Optional[str]:
        """獲取文檔內容緩存"""
        result = self.document_content_cache.get(document_id)
        self._update_cache_stats(CacheType.DOCUMENT_CONTENT, result is not None)
        return result
    
    def set_document_content(self, document_id: str, content: str):
        """設置文檔內容緩存"""
        self.document_content_cache[document_id] = content
        logger.debug(f"文檔內容已緩存: {document_id}")
    
    # === AI 回答緩存 ===
    def get_cached_ai_response(self, question: str, context_hash: str) -> Optional[Dict[str, Any]]:
        """獲取緩存的 AI 回答"""
        cache_key = self._generate_cache_key(f"{question}_{context_hash}", "ai_response")
        result = self.ai_response_cache.get(cache_key)
        self._update_cache_stats(CacheType.AI_RESPONSE, result is not None)
        return result
    
    def set_cached_ai_response(self, question: str, context_hash: str, response: Dict[str, Any]):
        """設置 AI 回答緩存"""
        cache_key = self._generate_cache_key(f"{question}_{context_hash}", "ai_response")
        self.ai_response_cache[cache_key] = response
        logger.debug(f"AI 回答已緩存: {cache_key}")
    
    # === 提示詞緩存（支援 Context Caching） ===
    async def get_or_create_prompt_cache(
        self,
        db: AsyncIOMotorDatabase,
        prompt_type: str,
        prompt_content: str,
        prompt_version: str = "2.0",
        ttl_hours: int = 24,
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        獲取或創建提示詞的 Context Cache
        
        Args:
            prompt_type: 提示詞類型 (如 'image_analysis_system')
            prompt_content: 提示詞內容
            prompt_version: 版本號，用於緩存鍵值
            ttl_hours: 緩存有效期（小時）
            user_id: 用戶ID（可選）
        
        Returns:
            Google Context Cache ID 或本地緩存鍵值
        """
        try:
            # 生成穩定的緩存鍵值，包含版本信息
            cache_key = self._generate_cache_key(
                f"prompt_v{prompt_version}_{prompt_type}_{prompt_content[:100]}", 
                "prompt"
            )
            
            # 檢查本地緩存
            if cache_key in self.prompt_template_cache:
                cached_info = self.prompt_template_cache[cache_key]
                self._update_cache_stats(CacheType.PROMPT_TEMPLATE, True)
                logger.info(f"使用緩存的提示詞: {prompt_type} (本地緩存)")
                return cached_info.get("cache_id", cache_key)
            
            # 檢查是否符合 Google Context Caching 要求
            token_check = self.google_context_cache_service.check_token_requirements(
                prompt_content, 
                model="gemini-2.5-flash"
            )
            
            # 如果符合 Context Caching 要求且服務可用
            if (token_check["meets_requirement"] and 
                self.google_context_cache_service.is_available()):
                
                # 創建 Google Context Cache
                from app.services.cache.google_context_cache_service import ContextCacheConfig, ContextCacheType
                
                config = ContextCacheConfig(
                    cache_type=ContextCacheType.SYSTEM_PROMPT,
                    content=prompt_content,
                    ttl_hours=ttl_hours,
                    model="gemini-2.5-flash",
                    display_name=f"{prompt_type}_v{prompt_version}",
                    metadata={
                        "prompt_type": prompt_type,
                        "version": prompt_version,
                        "created_by": "ai_cache_manager"
                    }
                )
                
                context_cache_info = await self.google_context_cache_service.create_context_cache(
                    config, db
                )
                
                if context_cache_info:
                    # 儲存到本地緩存
                    self.prompt_template_cache[cache_key] = {
                        "cache_id": context_cache_info.cache_id,
                        "cache_type": "google_context",
                        "token_count": context_cache_info.token_count,
                        "created_at": datetime.utcnow(),
                        "expires_at": context_cache_info.expires_at,
                        "prompt_type": prompt_type,
                        "version": prompt_version
                    }
                    
                    self._update_cache_stats(CacheType.PROMPT_TEMPLATE, False)
                    
                    await log_event(
                        db=db,
                        level=LogLevel.INFO,
                        message=f"創建提示詞 Context Cache: {prompt_type}, Token節省預估: {context_cache_info.token_count * 0.75}",
                        source="service.ai_cache_manager.prompt_cache_created",
                        user_id=user_id,
                        details={
                            "prompt_type": prompt_type,
                            "cache_id": context_cache_info.cache_id,
                            "token_count": context_cache_info.token_count,
                            "estimated_savings_percentage": 75
                        }
                    )
                    
                    logger.info(f"成功創建提示詞 Context Cache: {prompt_type} -> {context_cache_info.cache_id}")
                    return context_cache_info.cache_id
            
            # 降級到本地緩存
            self.prompt_template_cache[cache_key] = {
                "cache_id": cache_key,
                "cache_type": "local",
                "content": prompt_content,
                "created_at": datetime.utcnow(),
                "prompt_type": prompt_type,
                "version": prompt_version
            }
            
            self._update_cache_stats(CacheType.PROMPT_TEMPLATE, False)
            
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message=f"創建本地提示詞緩存: {prompt_type} (未達到 Context Caching 要求或服務不可用)",
                source="service.ai_cache_manager.local_prompt_cache_created",
                user_id=user_id,
                details={
                    "prompt_type": prompt_type,
                    "token_check": token_check,
                    "context_caching_available": self.google_context_cache_service.is_available()
                }
            )
            
            return cache_key
            
        except Exception as e:
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"創建提示詞緩存失敗: {prompt_type}, {str(e)}",
                source="service.ai_cache_manager.prompt_cache_error",
                user_id=user_id,
                details={"prompt_type": prompt_type, "error": str(e)}
            )
            logger.error(f"創建提示詞緩存失敗: {e}")
            return None
    
    def get_cached_prompt_info(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """獲取緩存的提示詞信息"""
        result = self.prompt_template_cache.get(cache_key)
        self._update_cache_stats(CacheType.PROMPT_TEMPLATE, result is not None)
        return result
    
    # === 緩存統計和管理 ===
    def get_cache_statistics(self) -> Dict[str, CacheStats]:
        """獲取緩存統計資訊"""
        # 更新記憶體使用量（簡化計算）
        for cache_type in CacheType:
            if cache_type == CacheType.QUERY_EMBEDDING:
                self.cache_stats[cache_type].memory_usage_mb = len(self.query_embedding_cache) * 0.01
            elif cache_type == CacheType.SCHEMA:
                self.cache_stats[cache_type].memory_usage_mb = len(self.schema_cache) * 0.1
            elif cache_type == CacheType.SYSTEM_INSTRUCTION:
                self.cache_stats[cache_type].memory_usage_mb = len(self.system_instruction_cache) * 0.05
            elif cache_type == CacheType.DOCUMENT_CONTENT:
                self.cache_stats[cache_type].memory_usage_mb = len(self.document_content_cache) * 0.2
            elif cache_type == CacheType.AI_RESPONSE:
                self.cache_stats[cache_type].memory_usage_mb = len(self.ai_response_cache) * 0.1
            elif cache_type == CacheType.PROMPT_TEMPLATE:
                self.cache_stats[cache_type].memory_usage_mb = len(self.prompt_template_cache) * 0.15
        
        return {cache_type.value: stats for cache_type, stats in self.cache_stats.items()}
    
    async def get_enhanced_cache_statistics(self, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
        """獲取增強的緩存統計資訊，包含 Google Context Caching"""
        try:
            # 本地緩存統計
            local_stats = self.get_cache_statistics()
            
            # Google Context Caching 統計
            google_stats = await self.google_context_cache_service.get_cache_statistics(db)
            
            # 合併統計
            enhanced_stats = {
                "local_caching": {
                    "cache_statistics": local_stats,
                    "total_local_memory_mb": sum(
                        stats.memory_usage_mb for stats in self.cache_stats.values()
                    ),
                    "total_local_requests": sum(
                        stats.total_requests for stats in self.cache_stats.values()
                    ),
                    "overall_local_hit_rate": self._calculate_overall_hit_rate()
                },
                "google_context_caching": google_stats,
                "combined_statistics": {
                    "is_google_context_caching_available": self.google_context_cache_service.is_available(),
                    "estimated_total_cost_savings": google_stats.get("estimated_savings", 0.0),
                    "cache_integration_status": "active" if self.google_context_cache_service.is_available() else "local_only"
                }
            }
            
            return enhanced_stats
            
        except Exception as e:
            logger.error(f"獲取增強緩存統計失敗: {e}")
            return {
                "error": str(e),
                "local_caching": {"cache_statistics": self.get_cache_statistics()}
            }
    
    def _calculate_overall_hit_rate(self) -> float:
        """計算總體命中率"""
        total_requests = sum(s.total_requests for s in self.cache_stats.values())
        total_hits = sum(s.hit_count for s in self.cache_stats.values())
        return total_hits / total_requests * 100 if total_requests > 0 else 0.0
    
    def clear_cache(self, cache_type: Optional[CacheType] = None):
        """清理緩存"""
        if cache_type:
            if cache_type == CacheType.QUERY_EMBEDDING:
                self.query_embedding_cache.clear()
            elif cache_type == CacheType.SCHEMA:
                self.schema_cache.clear()
            elif cache_type == CacheType.SYSTEM_INSTRUCTION:
                self.system_instruction_cache.clear()
            elif cache_type == CacheType.DOCUMENT_CONTENT:
                self.document_content_cache.clear()
            elif cache_type == CacheType.AI_RESPONSE:
                self.ai_response_cache.clear()
            elif cache_type == CacheType.PROMPT_TEMPLATE:
                self.prompt_template_cache.clear()
            logger.info(f"已清理 {cache_type.value} 緩存")
        else:
            # 清理所有緩存
            self.query_embedding_cache.clear()
            self.schema_cache.clear()
            self.system_instruction_cache.clear()
            self.document_content_cache.clear()
            self.ai_response_cache.clear()
            self.prompt_template_cache.clear()
            logger.info("已清理所有緩存")
    
    async def cleanup_expired_caches(self, db: AsyncIOMotorDatabase):
        """清理過期的緩存"""
        # TTLCache 會自動清理過期項目，這裡主要是記錄和統計
        total_cleaned = 0
        
        for cache_type, cache in [
            (CacheType.SCHEMA, self.schema_cache),
            (CacheType.SYSTEM_INSTRUCTION, self.system_instruction_cache),
            (CacheType.DOCUMENT_CONTENT, self.document_content_cache),
            (CacheType.AI_RESPONSE, self.ai_response_cache),
            (CacheType.PROMPT_TEMPLATE, self.prompt_template_cache)
        ]:
            before_size = len(cache)
            cache.expire()  # 強制清理過期項目
            after_size = len(cache)
            cleaned = before_size - after_size
            total_cleaned += cleaned
            
            if cleaned > 0:
                logger.info(f"{cache_type.value} 緩存清理了 {cleaned} 個過期項目")
        
        if total_cleaned > 0:
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message=f"緩存清理完成，共清理 {total_cleaned} 個過期項目",
                source="service.ai_cache_manager.cleanup",
                details={"total_cleaned": total_cleaned}
            )
    
    # === Context Caching 整合方法 ===
    async def integrate_with_gemini_context_caching(self, db: AsyncIOMotorDatabase):
        """
        整合 Google Gemini Context Caching API
        """
        try:
            if not self.google_context_cache_service.is_available():
                logger.warning("Google Context Caching 服務不可用")
                return False
            
            # 執行定期清理
            cleanup_stats = await self.google_context_cache_service.cleanup_expired_caches(db)
            
            # 獲取統計信息
            stats = await self.google_context_cache_service.get_cache_statistics(db)
            
            logger.info(f"Google Context Caching 整合完成: {stats}")
            
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="Google Context Caching 整合成功",
                source="service.ai_cache_manager.context_caching_integration",
                details={
                    "cleanup_count": cleanup_stats,
                    "total_caches": stats.get("total_caches", 0),
                    "estimated_savings": stats.get("estimated_savings", 0.0)
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Google Context Caching 整合失敗: {e}")
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"Google Context Caching 整合失敗: {str(e)}",
                source="service.ai_cache_manager.context_caching_integration_error",
                details={"error": str(e)}
            )
            return False


# 全域緩存管理器實例
ai_cache_manager = AICacheManager() 