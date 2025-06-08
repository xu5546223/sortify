from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.services.vector_db_service import vector_db_service
from app.services.embedding_service import embedding_service
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import SemanticSearchResult
from app.core.config import settings
import logging
import asyncio
import math
import uuid

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class EnhancedSearchService:
    """
    兩階段混合檢索搜索服務 (Two-Stage Hybrid Retrieval Search Service)
    
    實現策略：
    1. 第一階段 (粗篩選): 在摘要向量中快速找出相關文檔
    2. 第二階段 (精排序): 在候選文檔的內容塊向量中精確匹配
    3. RRF融合檢索 (終極策略): 並行執行摘要和內容塊搜索，使用倒數排名融合
    """
    
    def __init__(self):
        self.stage1_top_k = getattr(settings, 'VECTOR_SEARCH_STAGE1_TOP_K', 10)  # 第一階段返回候選文檔數
        self.stage2_top_k = getattr(settings, 'VECTOR_SEARCH_TOP_K', 5)  # 第二階段最終結果數
        self.similarity_threshold = getattr(settings, 'VECTOR_SIMILARITY_THRESHOLD', 0.4)
        # RRF 參數
        self.rrf_k = getattr(settings, 'RRF_K_CONSTANT', 60)  # RRF 常數 k，降低高排名影響力
        self.rrf_weights = getattr(settings, 'RRF_WEIGHTS', {"summary": 0.4, "chunks": 0.6})  # 搜索權重
    
    async def two_stage_hybrid_search(
        self,
        db: AsyncIOMotorDatabase,
        query: str,
        user_id: Any,
        search_type: str = "hybrid",
        stage1_top_k: Optional[int] = None,
        stage2_top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        # 新增：RRF 動態權重配置
        rrf_weights: Optional[Dict[str, float]] = None,
        rrf_k_constant: Optional[int] = None
    ) -> List[SemanticSearchResult]:
        """
        執行兩階段混合檢索搜索
        
        Args:
            db: 資料庫連接
            query: 搜索查詢
            user_id: 用戶ID
            search_type: 搜索類型 ("hybrid", "summary_only", "chunks_only", "rrf_fusion")
            stage1_top_k: 第一階段候選文檔數量
            stage2_top_k: 第二階段最終結果數量
            similarity_threshold: 相似度閾值
            
        Returns:
            排序後的搜索結果列表
        """
        # 為了ChromaDB的相容性，如果user_id是UUID物件，則將其轉換為字串
        if isinstance(user_id, uuid.UUID):
            user_id = str(user_id)
            
        # 使用參數或預設值
        stage1_k = stage1_top_k or self.stage1_top_k
        stage2_k = stage2_top_k or self.stage2_top_k
        sim_threshold = similarity_threshold or self.similarity_threshold
        
        log_details = {
            "user_id": user_id, 
            "query": query[:100],  # 限制查詢長度以節省日誌空間
            "search_type": search_type,
            "stage1_top_k": stage1_k,
            "stage2_top_k": stage2_k,
            "similarity_threshold": sim_threshold
        }
        
        logger.info(f"開始兩階段混合檢索搜索: {query[:50]}...")
        await log_event(db, LogLevel.INFO, "開始兩階段混合檢索搜索", 
                       "service.enhanced_search.two_stage_search_start", details=log_details)
        
        try:
            # 向量化查詢
            query_vector = embedding_service.encode_text(query)
            if not query_vector:
                logger.error("查詢向量化失敗")
                await log_event(db, LogLevel.ERROR, "查詢向量化失敗", 
                               "service.enhanced_search.query_vectorization_failed", details=log_details)
                return []
            
            # 根據搜索類型選擇策略
            if search_type == "summary_only":
                return await self._search_summary_vectors_only(
                    db, query_vector, user_id, stage2_k, sim_threshold, log_details
                )
            elif search_type == "chunks_only":
                return await self._search_chunk_vectors_only(
                    db, query_vector, user_id, stage2_k, sim_threshold, log_details
                )
            elif search_type == "rrf_fusion":
                # 🚀 新增：RRF 融合檢索策略
                return await self._execute_rrf_fusion_search(
                    db, query_vector, user_id, stage2_k, sim_threshold, log_details,
                    rrf_weights, rrf_k_constant
                )
            else:  # "hybrid" 預設
                return await self._execute_two_stage_search(
                    db, query_vector, user_id, stage1_k, stage2_k, sim_threshold, log_details
                )
                
        except ValueError as ve:
            logger.error(f"查詢處理失敗: {str(ve)}", exc_info=True)
            await log_event(db, LogLevel.WARNING, f"查詢處理失敗: {str(ve)}", 
                           "service.enhanced_search.query_processing_error", 
                           details={**log_details, "error": str(ve)})
            return []
        except Exception as e:
            logger.error(f"兩階段混合檢索搜索失敗: {str(e)}", exc_info=True)
            await log_event(db, LogLevel.ERROR, f"兩階段混合檢索搜索失敗: {str(e)}", 
                           "service.enhanced_search.two_stage_search_error", 
                           details={**log_details, "error": str(e)})
            return []
    
    async def _execute_two_stage_search(
        self,
        db: AsyncIOMotorDatabase,
        query_vector: List[float],
        user_id: str,
        stage1_k: int,
        stage2_k: int,
        sim_threshold: float,
        log_details: Dict[str, Any]
    ) -> List[SemanticSearchResult]:
        """執行完整的兩階段混合檢索"""
        
        # ===== 第一階段：粗篩選 (在摘要向量中搜索) =====
        logger.info(f"第一階段：在摘要向量中搜索，目標 {stage1_k} 個候選文檔")
        
        stage1_results = vector_db_service.search_similar_vectors(
            query_vector=query_vector,
            top_k=stage1_k,
            owner_id_filter=user_id,
            similarity_threshold=sim_threshold,
            metadata_filter={"type": "summary"}  # 只搜索摘要向量
        )
        
        if not stage1_results:
            logger.warning("第一階段未找到相關的摘要向量")
            await log_event(db, LogLevel.WARNING, "第一階段未找到相關摘要向量", 
                           "service.enhanced_search.stage1_no_results", details=log_details)
            return []
        
        # 提取候選文檔IDs
        candidate_doc_ids = [result.document_id for result in stage1_results]
        stage1_details = {
            **log_details,
            "stage1_candidates": len(candidate_doc_ids),
            "stage1_doc_ids": candidate_doc_ids[:5]  # 只記錄前5個以節省空間
        }
        
        logger.info(f"第一階段完成：找到 {len(candidate_doc_ids)} 個候選文檔")
        await log_event(db, LogLevel.INFO, f"第一階段完成：{len(candidate_doc_ids)} 個候選文檔", 
                       "service.enhanced_search.stage1_completed", details=stage1_details)
        
        # ===== 第二階段：精排序 (在候選文檔的內容塊中搜索) =====
        logger.info(f"第二階段：在候選文檔的內容塊中精確搜索，目標 {stage2_k} 個結果")
        
        stage2_results = vector_db_service.search_similar_vectors(
            query_vector=query_vector,
            top_k=stage2_k * 2,  # 搜索更多結果以便後續過濾和排序
            owner_id_filter=user_id,
            similarity_threshold=sim_threshold,
            metadata_filter={
                "type": "chunk",
                "document_id": {"$in": candidate_doc_ids}  # 限制在候選文檔的塊中搜索
            }
        )
        
        if not stage2_results:
            logger.warning("第二階段未找到相關的內容塊，降級使用第一階段結果")
            await log_event(db, LogLevel.WARNING, "第二階段無結果，降級使用第一階段結果", 
                           "service.enhanced_search.stage2_fallback", details=stage1_details)
            # 降級策略：返回第一階段的摘要結果
            return stage1_results[:stage2_k]
        
        # 對第二階段結果進行重排序和去重
        final_results = await self._rerank_and_deduplicate_results(
            stage2_results, stage1_results, stage2_k
        )
        
        final_details = {
            **stage1_details,
            "stage2_raw_results": len(stage2_results),
            "final_results": len(final_results)
        }
        
        logger.info(f"兩階段混合檢索完成：最終返回 {len(final_results)} 個精確結果")
        await log_event(db, LogLevel.INFO, f"兩階段混合檢索完成：{len(final_results)} 個結果", 
                       "service.enhanced_search.two_stage_completed", details=final_details)
        
        return final_results
    
    async def _search_summary_vectors_only(
        self,
        db: AsyncIOMotorDatabase,
        query_vector: List[float],
        user_id: str,
        top_k: int,
        sim_threshold: float,
        log_details: Dict[str, Any]
    ) -> List[SemanticSearchResult]:
        """僅在摘要向量中搜索（快速文檔級別搜索）"""
        
        logger.info("執行摘要向量專用搜索")
        
        results = vector_db_service.search_similar_vectors(
            query_vector=query_vector,
            top_k=top_k,
            owner_id_filter=user_id,
            similarity_threshold=sim_threshold,
            metadata_filter={"type": "summary"}
        )
        
        await log_event(db, LogLevel.INFO, f"摘要向量搜索完成：{len(results)} 個結果", 
                       "service.enhanced_search.summary_only_completed", 
                       details={**log_details, "results_count": len(results)})
        
        return results
    
    async def _search_chunk_vectors_only(
        self,
        db: AsyncIOMotorDatabase,
        query_vector: List[float],
        user_id: str,
        top_k: int,
        sim_threshold: float,
        log_details: Dict[str, Any]
    ) -> List[SemanticSearchResult]:
        """僅在內容塊向量中搜索（精確內容級別搜索）"""
        
        logger.info("執行內容塊向量專用搜索")
        
        results = vector_db_service.search_similar_vectors(
            query_vector=query_vector,
            top_k=top_k,
            owner_id_filter=user_id,
            similarity_threshold=sim_threshold,
            metadata_filter={"type": "chunk"}
        )
        
        await log_event(db, LogLevel.INFO, f"內容塊搜索完成：{len(results)} 個結果", 
                       "service.enhanced_search.chunks_only_completed", 
                       details={**log_details, "results_count": len(results)})
        
        return results
    
    async def _execute_rrf_fusion_search(
        self,
        db: AsyncIOMotorDatabase,
        query_vector: List[float],
        user_id: str,
        top_k: int,
        sim_threshold: float,
        log_details: Dict[str, Any],
        rrf_weights: Optional[Dict[str, float]] = None,
        rrf_k_constant: Optional[int] = None
    ) -> List[SemanticSearchResult]:
        """
        🚀 執行 RRF (Reciprocal Rank Fusion) 融合檢索
        
        並行執行兩種搜索：
        1. 搜索 A: 摘要向量搜索 (Summary Search)
        2. 搜索 B: 內容塊搜索 (Chunks Search)
        3. 使用 RRF 算法融合兩個排名列表
        
        RRF 公式: score(d) = Σ(w_i / (k + rank_i(d)))
        其中：
        - w_i: 搜索 i 的權重
        - k: RRF 常數 (通常為 60)
        - rank_i(d): 文檔 d 在搜索 i 中的排名
        """
        
        # 使用動態權重或預設權重
        effective_rrf_weights = rrf_weights or self.rrf_weights
        effective_rrf_k = rrf_k_constant or self.rrf_k
        
        logger.info(f"🚀 開始執行 RRF 融合檢索，目標 {top_k} 個結果")
        logger.info(f"🎯 RRF 參數：權重 {effective_rrf_weights}, k常數 {effective_rrf_k}")
        
        # 並行執行兩種搜索
        search_tasks = [
            # 搜索 A: 摘要向量搜索
            self._parallel_search_summary_vectors(query_vector, user_id, top_k * 2, sim_threshold),
            # 搜索 B: 內容塊搜索
            self._parallel_search_chunk_vectors(query_vector, user_id, top_k * 2, sim_threshold)
        ]
        
        try:
            summary_results, chunk_results = await asyncio.gather(*search_tasks)
            
            parallel_search_details = {
                **log_details,
                "summary_results_count": len(summary_results),
                "chunk_results_count": len(chunk_results)
            }
            
            logger.info(f"並行搜索完成：摘要 {len(summary_results)} 個，內容塊 {len(chunk_results)} 個")
            await log_event(db, LogLevel.INFO, "RRF 並行搜索完成", 
                           "service.enhanced_search.rrf_parallel_completed", details=parallel_search_details)
            
            if not summary_results and not chunk_results:
                logger.warning("RRF 融合檢索：兩種搜索都沒有找到結果")
                await log_event(db, LogLevel.WARNING, "RRF 融合檢索無結果", 
                               "service.enhanced_search.rrf_no_results", details=log_details)
                return []
            
            # 🎯 應用 RRF 算法進行排名融合
            fused_results = await self._apply_rrf_algorithm(
                summary_results, chunk_results, top_k, log_details,
                effective_rrf_weights, effective_rrf_k
            )
            
            final_details = {
                **parallel_search_details,
                "fused_results_count": len(fused_results),
                "rrf_k": effective_rrf_k,
                "rrf_weights": effective_rrf_weights
            }
            
            logger.info(f"🎯 RRF 融合檢索完成：最終返回 {len(fused_results)} 個結果")
            await log_event(db, LogLevel.INFO, f"RRF 融合檢索完成：{len(fused_results)} 個結果", 
                           "service.enhanced_search.rrf_fusion_completed", details=final_details)
            
            return fused_results
            
        except Exception as e:
            logger.error(f"RRF 融合檢索失敗: {str(e)}", exc_info=True)
            await log_event(db, LogLevel.ERROR, f"RRF 融合檢索失敗: {str(e)}", 
                           "service.enhanced_search.rrf_fusion_error", 
                           details={**log_details, "error": str(e)})
            return []
    
    async def _parallel_search_summary_vectors(
        self,
        query_vector: List[float],
        user_id: str,
        top_k: int,
        sim_threshold: float
    ) -> List[SemanticSearchResult]:
        """並行執行摘要向量搜索"""
        
        return vector_db_service.search_similar_vectors(
            query_vector=query_vector,
            top_k=top_k,
            owner_id_filter=user_id,
            similarity_threshold=sim_threshold,
            metadata_filter={"type": "summary"}
        )
    
    async def _parallel_search_chunk_vectors(
        self,
        query_vector: List[float],
        user_id: str,
        top_k: int,
        sim_threshold: float
    ) -> List[SemanticSearchResult]:
        """並行執行內容塊向量搜索"""
        
        return vector_db_service.search_similar_vectors(
            query_vector=query_vector,
            top_k=top_k,
            owner_id_filter=user_id,
            similarity_threshold=sim_threshold,
            metadata_filter={"type": "chunk"}
        )
    
    async def _apply_rrf_algorithm(
        self,
        summary_results: List[SemanticSearchResult],
        chunk_results: List[SemanticSearchResult],
        target_count: int,
        log_details: Dict[str, Any],
        rrf_weights: Dict[str, float],
        rrf_k_constant: int
    ) -> List[SemanticSearchResult]:
        """
        🎯 應用 RRF (Reciprocal Rank Fusion) 算法
        
        RRF 公式：
        score(document_d) = w_summary / (k + rank_summary(d)) + w_chunks / (k + rank_chunks(d))
        
        其中：
        - w_summary, w_chunks: 摘要和內容塊搜索的權重
        - k: RRF 常數 (預設 60)
        - rank_*(d): 文檔 d 在相應搜索中的排名 (從 1 開始)
        """
        
        logger.info("🎯 開始應用 RRF 算法進行排名融合")
        
        # 建立文檔排名映射
        summary_ranks = {result.document_id: idx + 1 for idx, result in enumerate(summary_results)}
        chunk_ranks = {}
        
        # 對於內容塊結果，需要按文檔分組並取最高分數的塊作為該文檔的代表
        chunk_doc_best = {}
        for idx, result in enumerate(chunk_results):
            doc_id = result.document_id
            if doc_id not in chunk_doc_best or result.similarity_score > chunk_doc_best[doc_id]["score"]:
                chunk_doc_best[doc_id] = {
                    "result": result,
                    "rank": idx + 1,
                    "score": result.similarity_score
                }
        
        # 建立內容塊文檔排名 (按最高分數重新排序)
        sorted_chunk_docs = sorted(chunk_doc_best.items(), key=lambda x: x[1]["score"], reverse=True)
        chunk_ranks = {doc_id: idx + 1 for idx, (doc_id, _) in enumerate(sorted_chunk_docs)}
        
        # 收集所有參與融合的文檔
        all_documents = set(summary_ranks.keys()) | set(chunk_ranks.keys())
        
        # 計算每個文檔的 RRF 分數
        rrf_scores = {}
        detailed_scores = {}  # 用於日誌記錄
        
        for doc_id in all_documents:
            rrf_score = 0.0
            score_details = {"doc_id": doc_id, "components": []}
            
            # 摘要搜索貢獻
            if doc_id in summary_ranks:
                summary_contribution = rrf_weights["summary"] / (rrf_k_constant + summary_ranks[doc_id])
                rrf_score += summary_contribution
                score_details["components"].append({
                    "type": "summary",
                    "rank": summary_ranks[doc_id],
                    "weight": rrf_weights["summary"],
                    "contribution": summary_contribution
                })
            
            # 內容塊搜索貢獻
            if doc_id in chunk_ranks:
                chunk_contribution = rrf_weights["chunks"] / (rrf_k_constant + chunk_ranks[doc_id])
                rrf_score += chunk_contribution
                score_details["components"].append({
                    "type": "chunks",
                    "rank": chunk_ranks[doc_id],
                    "weight": rrf_weights["chunks"],
                    "contribution": chunk_contribution
                })
            
            rrf_scores[doc_id] = rrf_score
            score_details["final_rrf_score"] = rrf_score
            detailed_scores[doc_id] = score_details
        
        # 按 RRF 分數排序
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 構建最終結果
        final_results = []
        for doc_id, rrf_score in sorted_docs[:target_count]:
            # 優先使用內容塊結果（更精確），如果沒有則使用摘要結果
            if doc_id in chunk_doc_best:
                result = chunk_doc_best[doc_id]["result"]
            else:
                # 在摘要結果中找到該文檔
                result = next((r for r in summary_results if r.document_id == doc_id), None)
                if not result:
                    continue
            
            # 創建新的結果對象，使用 RRF 分數替換原始相似度分數
            fused_result = SemanticSearchResult(
                document_id=result.document_id,
                similarity_score=rrf_score,  # 使用 RRF 分數
                summary_text=result.summary_text,
                metadata={
                    **(result.metadata or {}),
                    "rrf_score": rrf_score,
                    "original_similarity": result.similarity_score,
                    "fusion_method": "rrf",
                    "rrf_details": detailed_scores.get(doc_id, {}),
                    "search_strategy": "rrf_fusion"
                }
            )
            
            final_results.append(fused_result)
        
        # 記錄詳細的融合統計
        fusion_stats = {
            "total_candidates": len(all_documents),
            "summary_only": len(summary_ranks - chunk_ranks.keys()),
            "chunks_only": len(chunk_ranks.keys() - summary_ranks),
            "both_rankings": len(summary_ranks.keys() & chunk_ranks.keys()),
            "final_count": len(final_results),
            "rrf_k": rrf_k_constant,
            "weights": rrf_weights,
            "top_scores": [{"doc_id": r.document_id, "rrf_score": r.similarity_score} 
                          for r in final_results[:3]]  # 前3個結果的分數
        }
        
        logger.info(f"RRF 算法完成：{len(all_documents)} 個候選文檔 → {len(final_results)} 個融合結果")
        logger.debug(f"RRF 融合統計：{fusion_stats}")
        
        return final_results
    
    async def _rerank_and_deduplicate_results(
        self,
        stage2_results: List[SemanticSearchResult],
        stage1_results: List[SemanticSearchResult],
        target_count: int
    ) -> List[SemanticSearchResult]:
        """
        重排序和去重第二階段結果
        
        策略：
        1. 按相似度分數排序
        2. 按文檔去重（每個文檔只保留最高分的塊）
        3. 如果第二階段結果不足，用第一階段結果補充
        """
        
        # 按相似度分數排序
        stage2_results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # 按文檔去重，每個文檔只保留相似度最高的塊
        seen_documents = set()
        deduplicated_results = []
        
        for result in stage2_results:
            if result.document_id not in seen_documents:
                seen_documents.add(result.document_id)
                deduplicated_results.append(result)
                
                if len(deduplicated_results) >= target_count:
                    break
        
        # 如果第二階段結果不足，用第一階段結果補充
        if len(deduplicated_results) < target_count:
            for stage1_result in stage1_results:
                if (stage1_result.document_id not in seen_documents and 
                    len(deduplicated_results) < target_count):
                    deduplicated_results.append(stage1_result)
                    seen_documents.add(stage1_result.document_id)
        
        logger.info(f"重排序完成：{len(stage2_results)} → {len(deduplicated_results)} 個去重結果")
        
        return deduplicated_results[:target_count]

# 創建全局實例
enhanced_search_service = EnhancedSearchService() 