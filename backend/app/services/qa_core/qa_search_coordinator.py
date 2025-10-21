"""
QA搜索協調器

統一協調各種搜索策略,避免重複代碼
完全依賴 enhanced_search_service,不重複實現搜索邏輯
"""
import logging
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.models.vector_models import SemanticSearchResult, QueryRewriteResult
from app.services.vector.enhanced_search_service import enhanced_search_service
from app.services.vector.embedding_service import embedding_service
from app.services.vector.vector_db_service import vector_db_service
import asyncio

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class QASearchCoordinator:
    """
    QA搜索協調器
    
    職責: 協調不同的搜索策略,統一調用 enhanced_search_service
    不重複實現搜索邏輯!
    """
    
    def __init__(self):
        logger.info("QA搜索協調器初始化完成")
    
    async def coordinate_search(
        self,
        db: AsyncIOMotorDatabase,
        query: str,
        user_id: Optional[str],
        search_strategy: str = "hybrid",
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        document_ids: Optional[List[str]] = None
    ) -> List[SemanticSearchResult]:
        """
        協調搜索請求,根據策略調用 enhanced_search_service
        
        Args:
            db: 數據庫連接
            query: 搜索查詢
            user_id: 用戶ID
            search_strategy: 搜索策略 (hybrid, summary_only, rrf_fusion, traditional)
            top_k: 返回結果數
            similarity_threshold: 相似度閾值
            document_ids: 限制搜索的文檔ID列表
            
        Returns:
            List[SemanticSearchResult]: 搜索結果
        """
        logger.info(f"協調搜索: strategy={search_strategy}, query='{query[:50]}...'")
        
        try:
            # 根據策略選擇搜索類型
            if search_strategy == "summary_only":
                # 只搜索摘要
                return await enhanced_search_service.two_stage_hybrid_search(
                    db=db,
                    query=query,
                    user_id=str(user_id) if user_id else None,
                    search_type="summary_only",
                    stage2_top_k=top_k,
                    similarity_threshold=similarity_threshold
                )
            
            elif search_strategy == "rrf_fusion":
                # RRF融合搜索
                return await enhanced_search_service.two_stage_hybrid_search(
                    db=db,
                    query=query,
                    user_id=str(user_id) if user_id else None,
                    search_type="rrf_fusion",
                    stage1_top_k=min(top_k * 2, 15),
                    stage2_top_k=top_k,
                    similarity_threshold=similarity_threshold
                )
            
            elif search_strategy == "traditional":
                # 傳統單階段搜索(摘要+文本片段)
                return await self._traditional_single_stage_search(
                    db=db,
                    query=query,
                    user_id=user_id,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    document_ids=document_ids
                )
            
            else:  # "hybrid" 或其他
                # 默認使用兩階段混合檢索
                return await enhanced_search_service.two_stage_hybrid_search(
                    db=db,
                    query=query,
                    user_id=str(user_id) if user_id else None,
                    search_type="hybrid",
                    stage1_top_k=min(top_k * 2, 10),
                    stage2_top_k=top_k,
                    similarity_threshold=similarity_threshold
                )
        
        except Exception as e:
            logger.error(f"搜索協調失敗: {e}", exc_info=True)
            # 回退到最基礎的搜索
            return await self._basic_fallback_search(
                query=query,
                user_id=user_id,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            )
    
    async def _traditional_single_stage_search(
        self,
        db: AsyncIOMotorDatabase,
        query: str,
        user_id: Optional[str],
        top_k: int,
        similarity_threshold: float,
        document_ids: Optional[List[str]] = None
    ) -> List[SemanticSearchResult]:
        """
        傳統單階段搜索 - 同時搜索摘要和文本片段
        
        注意: 這個方法保留是為了完全兼容舊邏輯
        """
        logger.info(f"執行傳統單階段搜索: '{query[:50]}...'")
        
        # 生成查詢向量
        query_embedding = embedding_service.encode_text(query)
        if not query_embedding or not any(query_embedding):
            logger.error("無法生成查詢向量")
            return []
        
        # 準備過濾器
        summary_filter = {"type": "summary"}
        chunks_filter = {"type": "chunk"}
        
        if document_ids:
            summary_filter["document_id"] = {"$in": document_ids}
            chunks_filter["document_id"] = {"$in": document_ids}
        
        # 並行搜索摘要和文本片段
        summary_task = asyncio.to_thread(
            vector_db_service.search_similar_vectors,
            query_vector=query_embedding,
            top_k=top_k,
            owner_id_filter=user_id,
            metadata_filter=summary_filter,
            similarity_threshold=similarity_threshold
        )
        
        chunks_task = asyncio.to_thread(
            vector_db_service.search_similar_vectors,
            query_vector=query_embedding,
            top_k=top_k,
            owner_id_filter=user_id,
            metadata_filter=chunks_filter,
            similarity_threshold=similarity_threshold
        )
        
        summary_results, chunks_results = await asyncio.gather(summary_task, chunks_task)
        
        # 合併並去重(每個文檔只保留最高分)
        all_results = {}
        for result in summary_results + chunks_results:
            doc_id = result.document_id
            if doc_id not in all_results or result.similarity_score > all_results[doc_id].similarity_score:
                all_results[doc_id] = result
        
        # 排序
        final_results = sorted(all_results.values(), key=lambda r: r.similarity_score, reverse=True)
        
        logger.info(f"傳統單階段搜索完成,找到 {len(final_results)} 個文檔")
        return final_results[:top_k]
    
    async def _basic_fallback_search(
        self,
        query: str,
        user_id: Optional[str],
        top_k: int,
        similarity_threshold: float
    ) -> List[SemanticSearchResult]:
        """最基礎的回退搜索"""
        try:
            query_embedding = embedding_service.encode_text(query)
            if not query_embedding or not any(query_embedding):
                return []
            
            results = vector_db_service.search_similar_vectors(
                query_vector=query_embedding,
                top_k=top_k,
                owner_id_filter=user_id,
                metadata_filter=None,
                similarity_threshold=similarity_threshold * 0.7
            )
            
            logger.info(f"基礎回退搜索找到 {len(results)} 個結果")
            return results
            
        except Exception as e:
            logger.error(f"基礎回退搜索失敗: {e}")
            return []
    
    def extract_search_strategy(self, query_rewrite_result: Optional[QueryRewriteResult]) -> str:
        """
        從查詢重寫結果中提取建議的搜索策略
        
        Args:
            query_rewrite_result: 查詢重寫結果
            
        Returns:
            str: 搜索策略名稱
        """
        if not query_rewrite_result:
            return "hybrid"
        
        suggested = getattr(query_rewrite_result, 'search_strategy_suggestion', None)
        granularity = getattr(query_rewrite_result, 'query_granularity', None)
        
        # 策略映射
        if granularity == "thematic":
            return "summary_only"
        elif granularity in ["detailed", "unknown"]:
            return "rrf_fusion"
        
        strategy_map = {
            "summary_only": "summary_only",
            "rrf_fusion": "rrf_fusion",
            "keyword_enhanced_rrf": "rrf_fusion"
        }
        
        return strategy_map.get(suggested, "hybrid")


# 創建全局實例
qa_search_coordinator = QASearchCoordinator()

