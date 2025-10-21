from typing import List, Optional, Dict, Any, Tuple
import time
import json
import uuid
import traceback
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError
import logging
import asyncio


from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.services.ai_cache_manager import ai_cache_manager
from app.services.unified_ai_service_simplified import unified_ai_service_simplified, AIResponse as UnifiedAIResponse
from app.services.embedding_service import embedding_service
from app.services.vector_db_service import vector_db_service
from app.models.vector_models import (
    AIQARequest, AIQAResponse, QueryRewriteResult, LLMContextDocument,
    SemanticSearchResult, SemanticContextDocument
)
from app.models.ai_models_simplified import (
    AIQueryRewriteOutput,
    AIMongoDBQueryDetailOutput,
    AIDocumentAnalysisOutputDetail,
    AIGeneratedAnswerOutput,
    AIDocumentSelectionOutput
)
from app.models.document_models import Document
from app.crud.crud_documents import get_documents_by_ids
from app.services.vector_db_service import vector_db_service
from app.services.enhanced_search_service import enhanced_search_service

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class SearchWeightConfig:
    """搜索權重配置類 - 統一管理所有權重相關邏輯"""
    
    QUERY_TYPE_WEIGHTS = {
        0: 1.3,  # 類型A：自然語言摘要風格 - 最高權重
        1: 1.1,  # 類型B：關鍵詞密集查詢 - 中等權重  
        2: 1.0   # 類型C：領域專業查詢 - 標準權重
    }
    
    @classmethod
    def apply_query_weights(cls, results: List[SemanticSearchResult], query_index: int) -> List[SemanticSearchResult]:
        """應用查詢權重到搜索結果"""
        weight = cls.QUERY_TYPE_WEIGHTS.get(query_index, 1.0)
        for result in results:
            result.similarity_score *= weight
        return results
    
    @classmethod
    def get_query_weight(cls, query_index: int) -> float:
        """獲取特定查詢索引的權重"""
        return cls.QUERY_TYPE_WEIGHTS.get(query_index, 1.0)
    
    @classmethod
    def merge_weighted_results(cls, all_results_map: Dict[str, SemanticSearchResult], new_results: List[SemanticSearchResult], query_index: int) -> None:
        """合併加權結果到總結果集"""
        weight = cls.get_query_weight(query_index)
        
        for result in new_results:
            weighted_score = result.similarity_score * weight
            
            if result.document_id not in all_results_map:
                # 創建新結果
                all_results_map[result.document_id] = SemanticSearchResult(
                    document_id=result.document_id,
                    similarity_score=weighted_score,
                    summary_text=result.summary_text,
                    metadata=result.metadata
                )
            else:
                # 已存在的文檔，取最高分數
                if weighted_score > all_results_map[result.document_id].similarity_score:
                    all_results_map[result.document_id].similarity_score = weighted_score
                    all_results_map[result.document_id].summary_text = result.summary_text


def remove_projection_path_collisions(projection: dict) -> dict:
    """
    移除 MongoDB projection 中的父子欄位衝突，只保留最底層欄位。
    """
    if not projection or not isinstance(projection, dict):
        return projection
    keys = list(projection.keys())
    keys_to_remove = set()
    for k in keys:
        for other in keys:
            if k == other:
                continue
            # k 是 other 的子欄位，則移除父欄位 other
            if k.startswith(other + "."):
                keys_to_remove.add(other)
            # other 是 k 的子欄位，則移除父欄位 k
            elif other.startswith(k + "."):
                keys_to_remove.add(k)
    for k in keys_to_remove:
        projection.pop(k, None)
    return projection


class EnhancedAIQAService:
    """增強的AI問答服務 - 使用統一AI管理架構和專門的緩存管理器"""
    
    def __init__(self):
        # 使用專門的緩存管理器
        self.cache_manager = ai_cache_manager
        
        # 配置選項：是否為AIQA啟用兩階段混合檢索
        # 設為 True 以獲得更高準確度，設為 False 保持向後兼容
        self.enable_hybrid_search_for_aiqa = True
        
        logger.info("EnhancedAIQAService 初始化完成，使用專門的 AI 緩存管理器")
    
    async def _get_query_vectors(self, queries: List[str]) -> Dict[str, List[float]]:
        """統一向量獲取接口 - 通過緩存管理器統一處理"""
        vectors = {}
        uncached_queries = [q for q in queries if self.cache_manager.get_query_embedding(q) is None]
        
        # 批次處理未緩存的查詢
        if uncached_queries:
            try:
                query_vectors = embedding_service.encode_batch(uncached_queries)
                self.cache_manager.batch_set_query_embeddings(uncached_queries, query_vectors)
                logger.debug(f"批次生成並緩存了 {len(uncached_queries)} 個查詢的向量")
            except Exception as e:
                logger.error(f"批次向量生成失敗: {str(e)}")
                # 回退到單個處理
                for query in uncached_queries:
                    try:
                        single_vector = embedding_service.encode_text(query)
                        if single_vector:
                            self.cache_manager.set_query_embedding(query, single_vector)
                    except Exception as single_e:
                        logger.error(f"單個查詢向量生成失敗 '{query[:30]}...': {str(single_e)}")
        
        # 收集所有向量
        for query in queries:
            vector = self.cache_manager.get_query_embedding(query)
            if vector:
                vectors[query] = vector
            else:
                logger.warning(f"無法獲取查詢向量: '{query[:30]}...'")
        
        return vectors

    def _extract_search_strategy(self, query_rewrite_result: Optional[QueryRewriteResult]) -> str:
        """提取搜索策略 - 統一策略決策邏輯"""
        if not query_rewrite_result:
            return "hybrid"
        
        suggested = getattr(query_rewrite_result, 'search_strategy_suggestion', None)
        granularity = getattr(query_rewrite_result, 'query_granularity', None)
        
        # 策略映射邏輯
        strategy_map = {
            "summary_only": "summary_only",
            "rrf_fusion": "rrf_fusion", 
            "keyword_enhanced_rrf": "rrf_fusion"
        }
        
        # 根據粒度自動選擇
        if granularity == "thematic":
            return "summary_only"
        elif granularity in ["detailed", "unknown"]:
            return "rrf_fusion"
        
        return strategy_map.get(suggested, "hybrid")

    async def _unified_search(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        search_strategy: str,
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        similarity_threshold: float,
        **kwargs
    ) -> List[SemanticSearchResult]:
        """統一搜索接口 - 調用 enhanced_search_service 或回退到基礎搜索"""
        
        if not queries:
            return []
        
        primary_query = queries[0]
        
        try:
            if search_strategy == "summary_only":
                # 摘要專用搜索策略
                return await self._summary_only_search_optimized(
                    db, queries, top_k, user_id, request_id, similarity_threshold, **kwargs
                )
            elif search_strategy in ["rrf_fusion", "hybrid"]:
                # 使用兩階段混合檢索
                if self.enable_hybrid_search_for_aiqa:
                    return await self._hybrid_search_optimized(
                        db, queries, top_k, user_id, request_id, similarity_threshold, **kwargs
                    )
                else:
                    # 回退到傳統搜索
                    return await self._legacy_search_optimized(
                        db, queries, top_k, user_id, request_id, similarity_threshold, **kwargs
                    )
            else:
                # 未知策略，使用混合搜索
                logger.warning(f"未知搜索策略 '{search_strategy}'，回退到混合搜索")
                return await self._hybrid_search_optimized(
                    db, queries, top_k, user_id, request_id, similarity_threshold, **kwargs
                )
                
        except Exception as e:
            logger.error(f"統一搜索失敗，使用基礎回退搜索: {str(e)}")
            # 最終回退到最基礎的搜索
            return await self._basic_fallback_search(
                db, primary_query, top_k, user_id, similarity_threshold
            )

    async def _summary_only_search_optimized(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        similarity_threshold: float,
        **kwargs
    ) -> List[SemanticSearchResult]:
        """優化的摘要專用搜索"""
        logger.info(f"🎯 執行摘要專用搜索，查詢數量: {len(queries)}")
        
        # 獲取查詢向量
        query_vectors = await self._get_query_vectors(queries)
        all_results_map: Dict[str, SemanticSearchResult] = {}
        
        for i, query in enumerate(queries):
            if query not in query_vectors:
                logger.warning(f"跳過無向量的查詢: {query[:30]}...")
                continue
            
            query_embedding = query_vectors[query]
            
            # 準備摘要搜索的過濾器
            summary_metadata_filter = {"type": "summary"}
            document_ids = kwargs.get('document_ids')
            if document_ids:
                summary_metadata_filter["document_id"] = {"$in": document_ids}
            
            # 執行摘要向量搜索
            summary_results = await asyncio.to_thread(
                vector_db_service.search_similar_vectors,
                query_vector=query_embedding,
                top_k=top_k * 2,  # 多取一些候選
                owner_id_filter=user_id,
                metadata_filter=summary_metadata_filter,
                similarity_threshold=similarity_threshold * 0.9  # 稍微降低閾值
            )
            
            # 應用查詢權重並合併結果
            SearchWeightConfig.merge_weighted_results(all_results_map, summary_results, i)
        
        # 排序並返回結果
        final_results = list(all_results_map.values())
        final_results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        logger.info(f"摘要專用搜索完成，找到 {len(final_results)} 個結果")
        return final_results[:top_k]

    async def _hybrid_search_optimized(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        similarity_threshold: float,
        **kwargs
    ) -> List[SemanticSearchResult]:
        """優化的混合搜索 - 使用 enhanced_search_service"""
        
        try:
            all_results_map: Dict[str, SemanticSearchResult] = {}
            
            # 為每個重寫查詢執行兩階段搜索
            for i, query in enumerate(queries):
                logger.debug(f"執行第 {i+1}/{len(queries)} 個查詢的混合搜索: {query[:50]}...")
                
                # 執行 RRF 融合搜索
                stage_results = await enhanced_search_service.two_stage_hybrid_search(
                    db=db,
                    query=query,
                    user_id=user_id,
                    search_type="rrf_fusion",
                    stage1_top_k=min(top_k * 2, 15),
                    stage2_top_k=top_k,
                    similarity_threshold=similarity_threshold * 0.8
                )
                
                # 應用查詢權重並合併結果
                SearchWeightConfig.merge_weighted_results(all_results_map, stage_results, i)
                
                logger.debug(f"查詢 {i+1} 完成，本次找到 {len(stage_results)} 個結果")
            
            # 最終結果排序和多樣性優化
            final_results = list(all_results_map.values())
            final_results.sort(key=lambda x: x.similarity_score, reverse=True)
            
            # 多樣性優化
            if len(final_results) > top_k:
                final_results = self._apply_diversity_optimization(final_results, top_k)
            
            result_list = final_results[:top_k]
            
            logger.info(f"混合搜索完成: {len(queries)} 個查詢 → {len(result_list)} 個最終結果")
            
            return result_list
            
        except Exception as e:
            logger.error(f"混合搜索失敗，回退到傳統搜索: {str(e)}", exc_info=True)
            return await self._legacy_search_optimized(
                db, queries, top_k, user_id, request_id, similarity_threshold, **kwargs
            )

    async def _legacy_search_optimized(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        similarity_threshold: float,
        **kwargs
    ) -> List[SemanticSearchResult]:
        """優化的傳統搜索"""
        
        # 獲取查詢向量
        query_vectors = await self._get_query_vectors(queries)
        all_results_map: Dict[str, SemanticSearchResult] = {}
        
        # 準備元數據過濾器
        chroma_metadata_filter: Dict[str, Any] = {}
        # 這裡可以根據 kwargs 添加更多過濾邏輯
        
        for i, query in enumerate(queries):
            if query not in query_vectors:
                continue
                
            query_vector = query_vectors[query]
            adjusted_top_k = min(top_k * 2, 20) if len(queries) > 1 else top_k
            
            # 執行向量搜索
            results = vector_db_service.search_similar_vectors(
                query_vector=query_vector, 
                top_k=adjusted_top_k, 
                owner_id_filter=user_id, 
                metadata_filter=chroma_metadata_filter,
                similarity_threshold=similarity_threshold * 0.8
            )
            
            # 如果帶過濾條件的搜索沒有結果，嘗試回退搜索
            if not results and chroma_metadata_filter:
                logger.warning(f"帶 metadata_filter 的搜索沒有結果，嘗試回退搜索")
                results = vector_db_service.search_similar_vectors(
                    query_vector=query_vector, 
                    top_k=adjusted_top_k, 
                    owner_id_filter=user_id, 
                    metadata_filter=None,
                    similarity_threshold=similarity_threshold * 0.8
                )
            
            # 應用查詢權重並合併結果
            SearchWeightConfig.merge_weighted_results(all_results_map, results, i)
        
        # 排序和多樣性優化
        final_results = list(all_results_map.values())
        final_results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        if len(final_results) > top_k:
            final_results = self._apply_diversity_optimization(final_results, top_k)
        
        # 最終過濾
        final_threshold = similarity_threshold
        final_results = [r for r in final_results if r.similarity_score >= final_threshold]
        
        return final_results[:top_k]

    async def _basic_fallback_search(
        self,
        db: AsyncIOMotorDatabase,
        query: str,
        top_k: int,
        user_id: Optional[str],
        similarity_threshold: float
    ) -> List[SemanticSearchResult]:
        """最基礎的回退搜索"""
        try:
            query_embedding = embedding_service.encode_text(query)
            if not query_embedding or not any(query_embedding):
                logger.error("無法生成查詢的嵌入向量")
                return []
            
            results = vector_db_service.search_similar_vectors(
                query_vector=query_embedding,
                top_k=top_k,
                owner_id_filter=user_id,
                metadata_filter=None,
                similarity_threshold=similarity_threshold * 0.7  # 更寬鬆的閾值
            )
            
            logger.info(f"基礎回退搜索找到 {len(results)} 個結果")
            return results
            
        except Exception as e:
            logger.error(f"基礎回退搜索也失敗: {str(e)}")
            return []

    def _apply_diversity_optimization(self, results: List[SemanticSearchResult], top_k: int) -> List[SemanticSearchResult]:
        """應用多樣性優化算法"""
        diversified_results = []
        seen_summary_keywords = set()
        
        for result in results:
            # 提取摘要的關鍵詞進行去重判斷
            summary_words = set(result.summary_text.lower().split()[:10])
            overlap = len(summary_words.intersection(seen_summary_keywords))
            
            # 如果重疊度不高，或者還沒有足夠的結果，則加入
            if overlap < 5 or len(diversified_results) < max(3, top_k // 2):
                diversified_results.append(result)
                seen_summary_keywords.update(summary_words)
                
                if len(diversified_results) >= top_k:
                    break
        
        return diversified_results

    async def process_qa_request(
        self, 
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        處理AI問答請求的主要流程 - 支持用戶認證
        """
        user_id_str = str(user_id) if user_id else None
        start_time = time.time()
        total_tokens = 0
        detailed_document_data: Optional[List[Dict[str, Any]]] = None
        ai_generated_query_reasoning: Optional[str] = None
        
        log_details_initial = {
            "question_length": len(request.question) if request.question else 0,
            "document_ids_count": len(request.document_ids) if request.document_ids else 0,
            "model_preference": request.model_preference,
            "use_structured_filter": request.use_structured_filter,
            "use_semantic_search": request.use_semantic_search,
            "session_id": request.session_id
        }
        await log_event(db=db, level=LogLevel.INFO,
                        message="Enhanced AI QA request received.",
                        source="service.enhanced_ai_qa.request", user_id=user_id_str, request_id=request_id,
                        details=log_details_initial)

        query_rewrite_result: Optional[QueryRewriteResult] = None
        semantic_contexts_for_response: List[SemanticContextDocument] = []
        conversation_history_context = ""

        try:
            # === 對話記憶和文檔緩存處理 ===
            cached_doc_ids = []
            cached_doc_data = None
            
            if request.conversation_id and user_id:
                try:
                    from uuid import UUID
                    from app.services.conversation_cache_service import conversation_cache_service
                    from app.crud import crud_conversations
                    
                    conversation_uuid = UUID(request.conversation_id)
                    # 處理 user_id 可能是 UUID 或字符串
                    if isinstance(user_id, UUID):
                        user_uuid = user_id
                    else:
                        user_uuid = UUID(str(user_id)) if user_id else None
                    
                    if user_uuid:
                        # 先嘗試從 Redis 緩存獲取最近消息
                        recent_messages = await conversation_cache_service.get_recent_messages(
                            user_id=user_uuid,
                            conversation_id=conversation_uuid,
                            limit=5
                        )
                        
                        # 如果緩存未命中，從 MongoDB 獲取
                        if not recent_messages:
                            recent_messages = await crud_conversations.get_recent_messages(
                                db=db,
                                conversation_id=conversation_uuid,
                                user_id=user_uuid,
                                limit=5
                            )
                        
                        # 獲取已緩存的文檔ID和數據
                        cached_doc_ids, cached_doc_data = await crud_conversations.get_cached_documents(
                            db=db,
                            conversation_id=conversation_uuid,
                            user_id=user_uuid
                        )
                        
                        if cached_doc_ids:
                            logger.info(f"對話已緩存 {len(cached_doc_ids)} 個文檔，將優先使用")
                        
                        # 格式化對話歷史為上下文
                        if recent_messages and len(recent_messages) > 0:
                            conversation_history_context = "\n\n=== 對話歷史（最近 5 條）===\n"
                            for msg in recent_messages:
                                role_name = "用戶" if msg.role == "user" else "助手"
                                conversation_history_context += f"{role_name}: {msg.content[:200]}...\n" if len(msg.content) > 200 else f"{role_name}: {msg.content}\n"
                            conversation_history_context += "=== 當前問題 ===\n"
                            
                            logger.info(f"已載入 {len(recent_messages)} 條歷史消息作為上下文")
                            await log_event(db=db, level=LogLevel.INFO,
                                          message=f"載入對話記憶: {len(recent_messages)} 條歷史消息, 緩存文檔: {len(cached_doc_ids)}",
                                          source="service.enhanced_ai_qa.conversation_memory",
                                          user_id=user_id_str, request_id=request_id,
                                          details={"conversation_id": request.conversation_id, "messages_count": len(recent_messages), "cached_docs_count": len(cached_doc_ids)})
                except Exception as e:
                    logger.warning(f"載入對話歷史失敗，將繼續處理: {e}")
                    await log_event(db=db, level=LogLevel.WARNING,
                                  message=f"載入對話歷史失敗: {str(e)}",
                                  source="service.enhanced_ai_qa.conversation_memory_error",
                                  user_id=user_id_str, request_id=request_id)
            
            # === 智能觸發流程：基於傳統單階段搜索的真實相似度分數 ===
            # 根據實驗數據，傳統單階段搜索（摘要+文本片段）效果最好，我們將其作為第一道防線。
            confidence_threshold = 0.75  # 可調超參數

            # 第一步：執行傳統單階段搜索 (Traditional Single-Stage Search)
            logger.info(f"🔬 智能觸發 - 步驟 1: 執行傳統單階段搜索 (門檻: {confidence_threshold})")
            initial_search_results = await self._perform_traditional_single_stage_search(
                db, 
                original_query=request.question, 
                top_k=getattr(request, 'max_documents_for_selection', request.context_limit),
                user_id=user_id_str, 
                request_id=request_id,
                similarity_threshold=0.3, # 初始搜索的閾值可以寬鬆一些
                document_ids=request.document_ids
            )

            # 第二步：智能觸發決策
            use_full_rewrite_flow = True
            top_initial_score = 0.0
            
            if initial_search_results:
                top_initial_score = initial_search_results[0].similarity_score
                logger.info(f"傳統單階段搜索最高分 (raw similarity): {top_initial_score:.4f}")
                
                if top_initial_score > confidence_threshold:
                    use_full_rewrite_flow = False
                    logger.info(f"✅ 置信度足夠 ({top_initial_score:.4f} > {confidence_threshold})，跳過AI重寫和RRF，直接使用初始搜索結果。")
                else:
                    logger.info(f"🔄 置信度不足 ({top_initial_score:.4f} <= {confidence_threshold})，觸發完整AI查詢重寫和RRF融合流程。")
            else:
                logger.info("初始搜索無結果，觸發完整AI查詢重寫和RRF融合流程。")
            
            # 第三步：根據決策執行相應流程
            if use_full_rewrite_flow:
                # ELSE (top_initial_score <= confidence_threshold) -> Trigger full flow
                logger.info("智能觸發 - 步驟 2: 執行完整優化流程 (AI重寫 + RRF檢索)")
                await log_event(db=db, level=LogLevel.INFO,
                                message=f"智能觸發：執行AI重寫和RRF (初始分數: {top_initial_score:.4f})",
                                source="service.enhanced_ai_qa.smart_trigger_full_flow",
                                user_id=user_id_str, request_id=request_id,
                                details={"initial_score": top_initial_score, "confidence_threshold": confidence_threshold, "decision": "TRIGGER_FULL_FLOW"})
                
                query_rewrite_result, rewrite_tokens = await self._rewrite_query_unified(
                    db, request.question, user_id_str, request_id, 
                    query_rewrite_count=getattr(request, 'query_rewrite_count', 3)
                )
                total_tokens += rewrite_tokens
                
                # 使用重寫查詢進行優化檢索 (RRF)
                semantic_results_raw = await self._perform_optimized_search_direct(
                    db, query_rewrite_result.rewritten_queries if query_rewrite_result.rewritten_queries else [request.question],
                    getattr(request, 'max_documents_for_selection', request.context_limit),
                    user_id_str, request_id, query_rewrite_result,
                    getattr(request, 'similarity_threshold', 0.3),
                    getattr(request, 'enable_query_expansion', True)
                )
            else:
                # IF top_initial_score > confidence_threshold -> Skip full flow, use initial search results
                logger.info("智能觸發 - 步驟 2: 跳過完整優化流程，直接使用初始搜索結果")
                await log_event(db=db, level=LogLevel.INFO,
                                message=f"智能觸發：跳過AI重寫和RRF (初始分數: {top_initial_score:.4f})",
                                source="service.enhanced_ai_qa.smart_trigger_probe_skip",
                                user_id=user_id_str, request_id=request_id,
                                details={"initial_score": top_initial_score, "confidence_threshold": confidence_threshold, "decision": "SKIP_FULL_FLOW", "cost_saving": "YES"})
                
                # 創建一個簡單的查詢重寫結果以保持兼容性
                query_rewrite_result = QueryRewriteResult(
                    original_query=request.question,
                    rewritten_queries=[request.question],
                    extracted_parameters={},
                    intent_analysis="智能觸發跳過重寫，使用傳統單階段搜索結果"
                )
                semantic_results_raw = initial_search_results
                document_ids = []

            if semantic_results_raw:
                for res in semantic_results_raw:
                    semantic_contexts_for_response.append(
                        SemanticContextDocument(
                            document_id=res.document_id,
                            summary_or_chunk_text=res.summary_text,
                            similarity_score=res.similarity_score,
                            metadata=res.metadata
                        )
                    )
            
            if not semantic_results_raw:
                logger.warning("向量搜索未找到相關文檔")
                return AIQAResponse(
                    answer="抱歉，我在您的文檔庫中沒有找到與您問題相關的內容。",
                    source_documents=[],
                    confidence_score=0.0,
                    tokens_used=total_tokens,
                    processing_time=time.time() - start_time,
                    query_rewrite_result=query_rewrite_result,
                    semantic_search_contexts=semantic_contexts_for_response,
                    session_id=request.session_id
                )
            
            document_ids = [result.document_id for result in semantic_results_raw]
            
            # 優先使用對話中已緩存的文檔
            if cached_doc_ids and len(cached_doc_ids) > 0:
                # 合併緩存的文檔ID和新搜索到的文檔ID
                all_doc_ids = list(set(cached_doc_ids + document_ids))
                logger.info(f"合併緩存文檔 ({len(cached_doc_ids)}) 和新搜索文檔 ({len(document_ids)})，總計 {len(all_doc_ids)} 個文檔")
                document_ids = all_doc_ids
            
            if not isinstance(document_ids, list):
                logger.error(f"Before get_documents_by_ids, document_ids is not a list, but {type(document_ids)}. Defaulting to empty list.")
                document_ids = []

            full_documents = await get_documents_by_ids(db, document_ids)
            
            if user_id:
                full_documents = await self._filter_accessible_documents(db, full_documents, user_id_str, request_id)
            
            if not full_documents:
                logger.warning("用戶無權限訪問相關文檔或獲取文檔內容失敗")
                return AIQAResponse(
                    answer="找到了相關文檔，但您可能沒有訪問權限，或獲取詳細內容時出現問題。",
                    source_documents=[],
                    confidence_score=0.3,
                    tokens_used=total_tokens,
                    processing_time=time.time() - start_time,
                    query_rewrite_result=query_rewrite_result,
                    semantic_search_contexts=semantic_contexts_for_response,
                    session_id=request.session_id,
                    ai_generated_query_reasoning=ai_generated_query_reasoning,
                    detailed_document_data_from_ai_query=detailed_document_data
                )

            # --- Refactored: Two-Stage Smart Context Generation ---
            all_detailed_data: List[Dict[str, Any]] = []
            if full_documents:
                # Stage 1: AI 智慧篩選最佳文件（使用用戶設定的參數）
                selected_doc_ids_for_detail = await self._select_documents_for_detailed_query(
                    db, request.question, semantic_contexts_for_response, 
                    user_id_str, request_id,
                    ai_selection_limit=getattr(request, 'ai_selection_limit', 3),
                    similarity_threshold=getattr(request, 'similarity_threshold', 0.3)
                )

                logger.info(f"AI 選擇了 {len(selected_doc_ids_for_detail)} 個文件進行詳細查詢: {selected_doc_ids_for_detail}")

                if selected_doc_ids_for_detail:
                    full_documents_map = {str(doc.id): doc for doc in full_documents}
                    
                    document_schema_info = {
                        "description": "這是儲存在 MongoDB 中的單一文件 Schema。您的查詢將針對 'Target Document ID' 所指定的單一文件進行操作。",
                        "fields": {
                            "id": "UUID (字串), 文件的唯一標識符。這個 ID 已經被用來定位文件，您的查詢不需要再過濾 `_id`。",
                            "filename": "字串, 原始文件名。",
                            "file_type": "字串, 文件的 MIME 類型。",
                            "content_type_human_readable": "字串, 人類可讀的文件類型，例如 'PDF document', 'Word document', 'Email'。",
                            "extracted_text": "字串, 從文件中提取的完整文字內容。可能非常長，如有需要，請使用正則表達式進行部分匹配。",
                            "analysis": {
                                "type": "object",
                                "description": "包含對文件進行 AI 分析後產生的結果。",
                                "properties": {
                                    "ai_analysis_output": {
                                        "type": "object",
                                        "description": "這是先前 AI 分析任務（基於 AITextAnalysisOutput 或 AIImageAnalysisOutput 模型）產生的核心結構化輸出。這是最詳細、最有價值的資料來源。",
                                        "properties": {
                                            "initial_summary": "字串, 對文件的初步摘要。",
                                            "content_type": "字串, AI 識別的內容類型。",
                                            "key_information": {
                                                "type": "object",
                                                "description": "這是基於 `FlexibleKeyInformation` 模型提取的最重要的結構化資訊。詳細查詢應優先針對此對象。",
                                                "properties": {
                                                    "content_summary": "字串, 約 2-3 句話的內容摘要，非常適合回答總結性問題。",
                                                    "semantic_tags": "字串列表, 用於語義搜索的標籤。",
                                                    "main_topics": "字串列表, 文件討論的主要主題。",
                                                    "key_concepts": "字串列表, 提到的核心概念。",
                                                    "action_items": "字串列表, 文件中提到的待辦事項。",
                                                    "dates_mentioned": "字串列表, 提及的日期。",
                                                    "dynamic_fields": {
                                                        "type": "object",
                                                        "description": "由 AI 根據文件內容動態生成的欄位字典。如果用戶的問題暗示了特定的資訊（例如『專案經理是誰？』），您可以嘗試查詢這裡的鍵，例如 `analysis.ai_analysis_output.key_information.dynamic_fields.project_manager`。"
                                                    }
                                                }
                                            }
                                        }
                                    },
                                    "summary": "字串, 一個較舊的或由用戶提供的摘要。",
                                    "key_terms": "字串列表, 從文件中提取的關鍵術語。"
                                }
                            },
                            "tags": "字串列表, 用戶自定義的標籤。",
                            "metadata": "物件, 其他元數據（例如，來源 URL、作者）。結構可能不同。",
                            "created_at": "日期時間字串 (ISO 格式), 文件記錄的創建時間。",
                            "updated_at": "日期時間字串 (ISO 格式), 文件記錄的最後更新時間。"
                        },
                        "query_notes": "您的目標是生成 'projection' 來選擇特定欄位，和/或 'sub_filter' 來對文件內的欄位施加條件。例如，在 'extracted_text' 上使用正則表達式，或匹配 'analysis.ai_analysis_output.key_information.semantic_tags' 陣列中的元素。不要為 `_id` 生成過濾器，因為這已經處理好了。"
                    }

                    # Stage 2: 對每個被選中的文件執行詳細查詢
                    for doc_id in selected_doc_ids_for_detail:
                        if doc_id in full_documents_map:
                            target_document: Document = full_documents_map[doc_id]
                            logger.info(f"對文件 {doc_id} ({target_document.filename if hasattr(target_document, 'filename') else 'Unknown'}) 執行詳細查詢")
                            
                            ai_query_response = await unified_ai_service_simplified.generate_mongodb_detail_query(
                                user_question=request.question,
                                document_id=str(target_document.id),
                                document_schema_info=document_schema_info,
                                db=db,
                                model_preference=request.model_preference,
                                user_id=user_id_str,
                                session_id=request.session_id
                            )

                            if ai_query_response.success and ai_query_response.output_data and isinstance(ai_query_response.output_data, AIMongoDBQueryDetailOutput):
                                query_components = ai_query_response.output_data
                                if not ai_generated_query_reasoning:  # 取第一個文件的推理作為示例
                                    ai_generated_query_reasoning = query_components.reasoning

                                mongo_filter = {"_id": target_document.id}
                                mongo_projection = query_components.projection

                                if query_components.sub_filter:
                                    mongo_filter.update(query_components.sub_filter)

                                if mongo_projection or query_components.sub_filter:
                                    # 嘗試 AI 生成的詳細查詢
                                    logger.debug(f"執行AI查詢 - Filter: {mongo_filter}, Projection: {mongo_projection}")
                                    safe_projection = remove_projection_path_collisions(mongo_projection) if mongo_projection else None
                                    fetched_data = await db.documents.find_one(mongo_filter, projection=safe_projection)
                                    
                                    if fetched_data:
                                        def sanitize(data: Any) -> Any:
                                            if isinstance(data, dict): return {k: sanitize(v) for k, v in data.items()}
                                            if isinstance(data, list): return [sanitize(i) for i in data]
                                            if isinstance(data, uuid.UUID): return str(data)
                                            return data
                                        all_detailed_data.append(sanitize(fetched_data))
                                        logger.info(f"成功獲取文件 {doc_id} 的詳細資料")
                                    else:
                                        # 回退策略：使用基本查詢
                                        logger.warning(f"文件 {doc_id} 的AI詳細查詢沒有返回資料，嘗試回退查詢")
                                        fallback_filter = {"_id": target_document.id}
                                        fallback_projection = {
                                            "_id": 1,
                                            "filename": 1,
                                            "extracted_text": 1,
                                            "analysis.ai_analysis_output.key_information.content_summary": 1,
                                            "analysis.ai_analysis_output.key_information.semantic_tags": 1,
                                            "analysis.ai_analysis_output.key_information.key_concepts": 1
                                        }
                                        safe_fallback_projection = remove_projection_path_collisions(fallback_projection)
                                        fallback_data = await db.documents.find_one(fallback_filter, projection=safe_fallback_projection)
                                        if fallback_data:
                                            def sanitize(data: Any) -> Any:
                                                if isinstance(data, dict): return {k: sanitize(v) for k, v in data.items()}
                                                if isinstance(data, list): return [sanitize(i) for i in data]
                                                if isinstance(data, uuid.UUID): return str(data)
                                                return data
                                            all_detailed_data.append(sanitize(fallback_data))
                                            logger.info(f"回退查詢成功獲取文件 {doc_id} 的基本資料")
                                        else:
                                            logger.error(f"文件 {doc_id} 連基本查詢都失敗，可能文件不存在或權限問題")
                                else:
                                    logger.info(f"文件 {doc_id} 的查詢組件為空，跳過詳細查詢")
                            elif ai_query_response.error_message:
                                logger.error(f"文件 {doc_id} 的 AI 詳細查詢失敗: {ai_query_response.error_message}")
                        else:
                            logger.warning(f"選擇的文件 ID {doc_id} 在可訪問文件中未找到")
                else:
                    logger.info("AI 沒有選擇任何文件進行詳細查詢，將使用通用上下文")
            
            detailed_document_data = all_detailed_data if all_detailed_data else None
            logger.info(f"總共獲得 {len(all_detailed_data) if all_detailed_data else 0} 個文件的詳細資料")
            # --- End of Smart Context Generation ---

            answer, answer_tokens, confidence, actual_contexts_for_llm = await self._generate_answer_unified(
                db,
                request.question,
                full_documents,
                query_rewrite_result,
                detailed_document_data, # Pass the list of detailed data
                ai_generated_query_reasoning,
                user_id_str,
                request_id,
                request.model_preference,
                ensure_chinese_output=getattr(request, 'ensure_chinese_output', None),
                detailed_text_max_length=getattr(request, 'detailed_text_max_length', 8000),  # 傳遞用戶設定的文本長度限制
                max_chars_per_doc=getattr(request, 'max_chars_per_doc', None),  # 傳遞用戶設定的單文檔限制
                conversation_history=conversation_history_context  # 傳遞對話歷史上下文
            )
            total_tokens += answer_tokens
            
            processing_time = time.time() - start_time
            
            # === 保存問答對到對話中 ===
            if request.conversation_id and user_id:
                try:
                    from uuid import UUID
                    from app.crud import crud_conversations
                    from app.services.conversation_cache_service import conversation_cache_service
                    
                    logger.info(f"開始保存對話: conversation_id={request.conversation_id}, user_id={user_id}")
                    
                    conversation_uuid = UUID(request.conversation_id)
                    # user_id 可能已經是 UUID 對象
                    if isinstance(user_id, UUID):
                        user_uuid = user_id
                    else:
                        user_uuid = UUID(str(user_id)) if user_id else None
                    
                    logger.info(f"UUID 轉換成功: conversation_uuid={conversation_uuid}, user_uuid={user_uuid}")
                    
                    if user_uuid:
                        # 添加用戶問題
                        logger.info(f"準備添加用戶問題: {request.question[:50]}...")
                        result1 = await crud_conversations.add_message_to_conversation(
                            db=db,
                            conversation_id=conversation_uuid,
                            user_id=user_uuid,
                            role="user",
                            content=request.question,
                            tokens_used=None
                        )
                        logger.info(f"用戶問題添加結果: {result1}")
                        
                        # 添加 AI 回答
                        logger.info(f"準備添加 AI 回答: {answer[:50]}...")
                        result2 = await crud_conversations.add_message_to_conversation(
                            db=db,
                            conversation_id=conversation_uuid,
                            user_id=user_uuid,
                            role="assistant",
                            content=answer,
                            tokens_used=answer_tokens
                        )
                        logger.info(f"AI 回答添加結果: {result2}")
                        
                        # 更新對話的文檔緩存
                        if full_documents:
                            new_doc_ids = [str(doc.id) for doc in full_documents]
                            logger.info(f"準備更新文檔緩存: {len(new_doc_ids)} 個文檔，IDs: {new_doc_ids}")
                            cache_result = await crud_conversations.update_cached_documents(
                                db=db,
                                conversation_id=conversation_uuid,
                                user_id=user_uuid,
                                document_ids=new_doc_ids,
                                document_data=None
                            )
                            logger.info(f"文檔緩存更新結果: {cache_result}")
                        else:
                            logger.warning("沒有 full_documents 可以緩存")
                        
                        # 使緩存失效，下次會從 MongoDB 重新載入
                        await conversation_cache_service.invalidate_conversation(
                            user_id=user_uuid,
                            conversation_id=conversation_uuid
                        )
                        
                        logger.info(f"✅ 成功保存問答對到對話 {request.conversation_id}")
                    else:
                        logger.error(f"user_uuid 為 None，無法保存對話")
                except Exception as e:
                    import traceback
                    logger.error(f"❌ 保存對話失敗: {e}")
                    logger.error(f"錯誤詳情: {traceback.format_exc()}")
                    # 不影響主流程，繼續返回結果
            else:
                logger.warning(f"跳過保存對話: conversation_id={request.conversation_id}, user_id={user_id}")
            
            logger.info(f"AI問答處理完成，耗時: {processing_time:.2f}秒，Token: {total_tokens} (用戶: {user_id})")
            
            return AIQAResponse(
                answer=answer,
                source_documents=[str(doc.id) for doc in full_documents],
                confidence_score=confidence,
                tokens_used=total_tokens,
                processing_time=processing_time,
                query_rewrite_result=query_rewrite_result,
                semantic_search_contexts=semantic_contexts_for_response,
                session_id=request.session_id,
                llm_context_documents=actual_contexts_for_llm,
                ai_generated_query_reasoning=ai_generated_query_reasoning,
                detailed_document_data_from_ai_query=detailed_document_data
            )
            
        except Exception as e:
            processing_time_on_error = time.time() - start_time
            error_trace = traceback.format_exc()
            await log_event(db=db, level=LogLevel.ERROR, message=f"Enhanced AI QA failed: {str(e)}",
                            source="service.enhanced_ai_qa.process_request_error", user_id=user_id_str, request_id=request_id,
                            details={"error": str(e), "error_type": type(e).__name__, "traceback": error_trace, **log_details_initial})
            
            current_total_tokens = total_tokens if isinstance(total_tokens, int) else 0
            current_qrr = query_rewrite_result if isinstance(query_rewrite_result, QueryRewriteResult) else QueryRewriteResult(original_query=request.question, rewritten_queries=[request.question], extracted_parameters={}, intent_analysis="Error before QRR.")
            current_semantic_contexts = semantic_contexts_for_response if isinstance(semantic_contexts_for_response, list) else []

            return AIQAResponse(
                answer=f"An error occurred: {str(e)}", source_documents=[], confidence_score=0.0, tokens_used=current_total_tokens,
                processing_time=processing_time_on_error, query_rewrite_result=current_qrr,
                semantic_search_contexts=current_semantic_contexts, session_id=request.session_id,
                llm_context_documents=[], ai_generated_query_reasoning=ai_generated_query_reasoning,
                detailed_document_data_from_ai_query=detailed_document_data, error_message=str(e) 
            )

    async def _filter_accessible_documents(self, db: AsyncIOMotorDatabase, full_documents: List[Any], user_id_str: Optional[str], request_id: Optional[str]) -> List[Any]:
        if not user_id_str: return full_documents
        try:
            user_uuid = uuid.UUID(user_id_str)
            accessible_documents = [doc for doc in full_documents if hasattr(doc, 'owner_id') and doc.owner_id == user_uuid]
            if not accessible_documents:
                logger.warning("用戶無權限訪問相關文檔或獲取文檔內容失敗")
                return []
            return accessible_documents
        except ValueError:
            await log_event(db=db, level=LogLevel.ERROR, message=f"Invalid user_id format for access filtering: {user_id_str}", source="service.enhanced_ai_qa._filter_accessible_documents", user_id=user_id_str, request_id=request_id)
            return []

    async def _select_documents_for_detailed_query(
        self,
        db: AsyncIOMotorDatabase,
        user_question: str,
        semantic_contexts: List[SemanticContextDocument],
        user_id: Optional[str],
        request_id: Optional[str],
        ai_selection_limit: int,
        similarity_threshold: float
    ) -> List[str]:
        """
        使用 AI 從候選文件中智慧選擇最相關的文件進行詳細查詢，
        包含去重邏輯和動態數量決策
        """
        if not semantic_contexts:
            return []

        # 第一步：根據分數進行去重
        # RRF融合搜索的結果已經過排序和初步篩選，此處主要進行去重
        filtered_contexts = {}
        
        for ctx in semantic_contexts:
            # 相似度篩選 - 由於RRF分數與相似度閾值不可比，移除此過濾
            # if ctx.similarity_score < similarity_threshold:
            #     continue
                
            # 去重：如果同一個文件有多個片段，選擇相似度（或RRF分數）最高的
            if ctx.document_id not in filtered_contexts or ctx.similarity_score > filtered_contexts[ctx.document_id].similarity_score:
                filtered_contexts[ctx.document_id] = ctx
        
        # 按分數排序（RRF分數越高越好）
        unique_contexts = sorted(filtered_contexts.values(), key=lambda x: x.similarity_score, reverse=True)
        
        # 第二步：動態決定要提供給AI的候選數量
        max_candidates = min(ai_selection_limit * 2, len(unique_contexts))  # 提供給AI的候選數是選擇限制的2倍
        candidates_for_ai = unique_contexts[:max_candidates]
        
        if len(candidates_for_ai) < 2:
            logger.info(f"候選文件數量不足（{len(candidates_for_ai)}），跳過AI選擇，直接返回所有候選")
            return [ctx.document_id for ctx in candidates_for_ai]

        # 準備候選文件資料給AI分析
        candidate_docs_for_ai = [
            {
                "document_id": ctx.document_id, 
                "summary": ctx.summary_or_chunk_text,
                "similarity_score": ctx.similarity_score
            }
            for ctx in candidates_for_ai
        ]

        await log_event(db=db, level=LogLevel.INFO,
                        message=f"經過去重和篩選後，準備請AI從 {len(candidate_docs_for_ai)} 個候選文件中選擇最相關的進行詳細查詢（用戶限制：{ai_selection_limit}個）",
                        source="service.enhanced_ai_qa._select_documents_for_detailed_query",
                        user_id=user_id, request_id=request_id,
                        details={"candidates": [{"id": doc["document_id"], "score": doc["similarity_score"]} for doc in candidate_docs_for_ai], "user_selection_limit": ai_selection_limit})

        selection_response = await unified_ai_service_simplified.select_documents_for_detailed_query(
            user_question=user_question,
            candidate_documents=candidate_docs_for_ai,
            db=db,
            user_id=user_id,
            session_id=request_id,
            max_selections=ai_selection_limit  # 傳遞用戶的選擇限制
        )

        if selection_response.success and isinstance(selection_response.output_data, AIDocumentSelectionOutput):
            selected_ids = selection_response.output_data.selected_document_ids
            reasoning = selection_response.output_data.reasoning
            
            # 驗證選擇的文件ID是否有效
            valid_candidate_ids = {doc["document_id"] for doc in candidate_docs_for_ai}
            validated_selected_ids = [doc_id for doc_id in selected_ids if doc_id in valid_candidate_ids]
            
            if len(validated_selected_ids) != len(selected_ids):
                dropped_ids = set(selected_ids) - set(validated_selected_ids)
                logger.warning(f"AI選擇了一些無效的文件ID，已過濾掉: {dropped_ids}")
            
            await log_event(db=db, level=LogLevel.INFO,
                            message=f"AI智慧選擇了 {len(validated_selected_ids)} 個文件進行詳細查詢",
                            source="service.enhanced_ai_qa._select_documents_for_detailed_query",
                            user_id=user_id, request_id=request_id,
                            details={
                                "selected_ids": validated_selected_ids, 
                                "reasoning": reasoning,
                                "original_candidates": len(semantic_contexts),
                                "after_dedup_filter": len(candidates_for_ai),
                                "final_selected": len(validated_selected_ids)
                            })
            
            return validated_selected_ids
        else:
            await log_event(db=db, level=LogLevel.WARNING,
                            message=f"AI文件選擇失敗，回退策略：選擇相似度最高的前{min(ai_selection_limit, len(candidates_for_ai))}個文件",
                            source="service.enhanced_ai_qa._select_documents_for_detailed_query",
                            user_id=user_id, request_id=request_id,
                            details={"error": selection_response.error_message, "fallback_count": min(ai_selection_limit, len(candidates_for_ai))})
            
            # 回退策略：根據用戶設定選擇相似度最高的文件
            fallback_count = min(ai_selection_limit, len(candidates_for_ai))
            fallback_selection = [ctx.document_id for ctx in candidates_for_ai[:fallback_count]]
            return fallback_selection

    async def _rewrite_query_unified(self, db: AsyncIOMotorDatabase, original_query: str, user_id: Optional[str], request_id: Optional[str], query_rewrite_count: int) -> Tuple[QueryRewriteResult, int]:
        """統一的查詢重寫方法 - 支持新的智能意圖分析和動態策略路由"""
        ai_response = await unified_ai_service_simplified.rewrite_query(original_query=original_query, db=db)
        tokens = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
        
        if ai_response.success and ai_response.output_data:
            # 嘗試解析新的 AIQueryRewriteOutput 格式
            if isinstance(ai_response.output_data, AIQueryRewriteOutput):
                output = ai_response.output_data
                logger.info(f"🧠 AI意圖分析：{output.reasoning}")
                logger.info(f"📊 問題粒度：{output.query_granularity}")
                logger.info(f"🎯 建議策略：{output.search_strategy_suggestion}")
                logger.info(f"📝 重寫查詢數量：{len(output.rewritten_queries)}")
                
                # 創建擴展的 QueryRewriteResult，包含新的策略信息
                return QueryRewriteResult(
                    original_query=original_query, 
                    rewritten_queries=output.rewritten_queries, 
                    extracted_parameters=output.extracted_parameters, 
                    intent_analysis=output.intent_analysis,
                    # 添加新的策略信息到 extracted_parameters
                    query_granularity=output.query_granularity,
                    search_strategy_suggestion=output.search_strategy_suggestion,
                    reasoning=output.reasoning
                ), tokens
            
            # 向後兼容：處理舊的 AIQueryRewriteOutputLegacy 格式
            elif hasattr(ai_response.output_data, 'rewritten_queries'):
                output = ai_response.output_data
                logger.warning("使用舊版查詢重寫格式，缺少智能策略路由信息")
                return QueryRewriteResult(
                    original_query=original_query, 
                    rewritten_queries=output.rewritten_queries if hasattr(output, 'rewritten_queries') else [original_query], 
                    extracted_parameters=output.extracted_parameters if hasattr(output, 'extracted_parameters') else {}, 
                    intent_analysis=output.intent_analysis if hasattr(output, 'intent_analysis') else "Legacy format - no intent analysis"
                ), tokens
        
        # 失敗回退
        logger.error("查詢重寫失敗，使用原始查詢")
        return QueryRewriteResult(
            original_query=original_query, 
            rewritten_queries=[original_query], 
            extracted_parameters={}, 
            intent_analysis="Query rewrite failed."
        ), tokens

    async def _perform_traditional_single_stage_search(
        self,
        db: AsyncIOMotorDatabase,
        original_query: str,
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        similarity_threshold: float,
        document_ids: Optional[List[str]] = None
    ) -> List[SemanticSearchResult]:
        """
        執行傳統的單階段向量搜索，同時搜索文檔摘要和文本片段。
        """
        logger.info(f"執行傳統單階段搜索 (摘要+文本片段) for query: '{original_query[:100]}...'")

        # 1. 生成查詢向量
        # 修正: 使用正確的方法名稱 encode_text
        query_embedding = embedding_service.encode_text(original_query)
        if not query_embedding or not any(query_embedding): # 檢查是否為空或零向量
            logger.error("無法生成查詢的嵌入向量或生成了零向量。")
            return []

        # 2. 並行執行對摘要和文本片段的搜索
        # 修正: 使用單一 collection 並通過 metadata filter 區分 'summary' 和 'chunk'
        # 修正: 使用 asyncio.to_thread 來調用同步的 aiohttp 方法

        # 準備摘要搜索的過濾器
        summary_metadata_filter = {"type": "summary"}
        if document_ids:
            summary_metadata_filter["document_id"] = {"$in": document_ids}

        summary_search_task = asyncio.to_thread(
            vector_db_service.search_similar_vectors,
            query_vector=query_embedding,
            top_k=top_k,
            owner_id_filter=user_id,
            metadata_filter=summary_metadata_filter,
            similarity_threshold=similarity_threshold
        )
        
        # 準備文本片段搜索的過濾器
        chunks_metadata_filter = {"type": "chunk"}
        if document_ids:
            chunks_metadata_filter["document_id"] = {"$in": document_ids}

        chunks_search_task = asyncio.to_thread(
            vector_db_service.search_similar_vectors,
            query_vector=query_embedding,
            top_k=top_k,
            owner_id_filter=user_id,
            metadata_filter=chunks_metadata_filter,
            similarity_threshold=similarity_threshold
        )
        
        summary_results, chunks_results = await asyncio.gather(summary_search_task, chunks_search_task)
        
        # 3. 合併並去重結果
        # 使用字典來確保每個 document_id 只保留最高分
        all_results = {}
        
        search_results = summary_results + chunks_results
        
        for result in search_results:
            doc_id = result.document_id
            if doc_id not in all_results or result.similarity_score > all_results[doc_id].similarity_score:
                all_results[doc_id] = result
        
        # 4. 按分數降序排序
        final_results = sorted(list(all_results.values()), key=lambda r: r.similarity_score, reverse=True)
        
        logger.info(f"傳統單階段搜索完成，合併後共找到 {len(final_results)} 個不重複的文檔。")
        
        return final_results[:top_k]

    async def _semantic_search_summary_only(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        similarity_threshold: float,
        document_ids: Optional[List[str]] = None
    ) -> List[SemanticSearchResult]:
        """摘要專用搜索 - 適合主題級問題"""
        logger.info(f"🎯 執行摘要專用搜索，查詢數量: {len(queries)}")
        
        all_results_map: Dict[str, SemanticSearchResult] = {}
        
        for i, query in enumerate(queries):
            logger.debug(f"執行第 {i+1}/{len(queries)} 個查詢的摘要搜索: {query[:50]}...")
            
            # 生成查詢向量
            query_embedding = embedding_service.encode_text(query)
            if not query_embedding or not any(query_embedding):
                logger.warning(f"查詢 '{query[:30]}...' 無法生成嵌入向量，跳過")
                continue
            
            # 準備摘要搜索的過濾器
            summary_metadata_filter = {"type": "summary"}
            if document_ids:
                summary_metadata_filter["document_id"] = {"$in": document_ids}
            
            # 執行摘要向量搜索
            summary_results = await asyncio.to_thread(
                vector_db_service.search_similar_vectors,
                query_vector=query_embedding,
                top_k=top_k * 2,  # 多取一些候選
                owner_id_filter=user_id,
                metadata_filter=summary_metadata_filter,
                similarity_threshold=similarity_threshold * 0.9  # 稍微降低閾值以獲得更多候選
            )
            
            # 應用查詢權重（主題級查詢第一個通常最重要）
            query_weight = 1.2 if i == 0 else 1.0
            
            for result in summary_results:
                weighted_score = result.similarity_score * query_weight
                
                if result.document_id not in all_results_map:
                    all_results_map[result.document_id] = SemanticSearchResult(
                        document_id=result.document_id,
                        similarity_score=weighted_score,
                        summary_text=result.summary_text,
                        metadata=result.metadata
                    )
                else:
                    # 保留最高分
                    if weighted_score > all_results_map[result.document_id].similarity_score:
                        all_results_map[result.document_id].similarity_score = weighted_score
                        all_results_map[result.document_id].summary_text = result.summary_text
        
        # 排序並返回結果
        final_results = list(all_results_map.values())
        final_results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        logger.info(f"摘要專用搜索完成，找到 {len(final_results)} 個結果")
        return final_results[:top_k]

    async def _perform_optimized_search_direct(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int,
        user_id: Optional[str],
        request_id: Optional[str],
        query_rewrite_result: Optional[QueryRewriteResult],
        similarity_threshold: float,
        enable_query_expansion: bool
    ) -> List[SemanticSearchResult]:
        """簡化的搜索執行邏輯 - 使用統一搜索接口"""
        
        # 獲取 AI 建議的策略
        strategy = self._extract_search_strategy(query_rewrite_result)
        
        logger.info(f"🎯 執行搜索策略: {strategy}")
        
        # 統一搜索調用
        return await self._unified_search(
            db=db,
            queries=queries,
            search_strategy=strategy,
            top_k=top_k,
            user_id=user_id,
            request_id=request_id,
            similarity_threshold=similarity_threshold
                )
    
    async def _semantic_search_with_hybrid_retrieval(
        self, 
        db: AsyncIOMotorDatabase, 
        queries: List[str], 
        top_k: int, 
        user_id: Optional[Any], 
        request_id: Optional[str], 
        query_rewrite_result: Optional[QueryRewriteResult], 
        similarity_threshold: float, 
        enable_query_expansion: bool
    ) -> List[SemanticSearchResult]:
        """使用兩階段混合檢索進行語義搜索 - 已重構使用統一配置"""
        
        # 為了日誌和服務調用，確保 user_id 是字串
        user_id_str = str(user_id) if user_id else None

        try:
            # 導入兩階段搜索服務
            from app.services.enhanced_search_service import enhanced_search_service
            
            all_results_map: Dict[str, SemanticSearchResult] = {}
            
            # 為每個重寫查詢執行兩階段搜索
            for i, query in enumerate(queries):
                logger.debug(f"執行第 {i+1}/{len(queries)} 個查詢的 RRF 融合搜索: {query[:50]}...")
                
                # 執行 RRF 融合搜索
                stage_results = await enhanced_search_service.two_stage_hybrid_search(
                    db=db,
                    query=query,
                    user_id=user_id_str,  # 強制使用字串
                    search_type="rrf_fusion",  # 強制使用 RRF 融合搜索
                    stage1_top_k=min(top_k * 2, 15),  # RRF內部會使用此參數作為候選數
                    stage2_top_k=top_k,
                    similarity_threshold=similarity_threshold * 0.8  # 保持AIQA原有的閾值策略
                )
                
                # 使用統一的權重配置合併結果
                SearchWeightConfig.merge_weighted_results(all_results_map, stage_results, i)
                
                logger.debug(f"查詢 {i+1} 完成，本次找到 {len(stage_results)} 個結果")
            
            # 最終結果排序和多樣性優化
            final_results = list(all_results_map.values())
            final_results.sort(key=lambda x: x.similarity_score, reverse=True)
            
            # 多樣性優化
            if len(final_results) > top_k:
                final_results = self._apply_diversity_optimization(final_results, top_k)
            
            result_list = final_results[:top_k]
            
            logger.info(f"兩階段混合檢索完成: {len(queries)} 個查詢 → {len(result_list)} 個最終結果")
            
            await log_event(db=db, level=LogLevel.INFO,
                            message=f"兩階段混合檢索完成: {len(result_list)} 個結果",
                            source="service.enhanced_ai_qa.semantic_search_hybrid",
                            user_id=user_id_str, request_id=request_id,
                            details={
                                "query_count": len(queries),
                                "final_results": len(result_list),
                                "search_strategy": "two_stage_hybrid",
                                "diversity_optimization": True
                            })
            
            return result_list
            
        except Exception as e:
            logger.error(f"兩階段混合檢索失敗，回退到傳統搜索: {str(e)}", exc_info=True)
            await log_event(db=db, level=LogLevel.WARNING,
                            message=f"兩階段混合檢索失敗，回退到傳統搜索: {str(e)}",
                            source="service.enhanced_ai_qa.semantic_search_hybrid_fallback",
                            user_id=user_id_str, request_id=request_id,
                            details={"error": str(e)})
            
            # 回退到傳統搜索
            return await self._semantic_search_legacy(
                db, queries, top_k, user_id_str, request_id, query_rewrite_result, 
                similarity_threshold, enable_query_expansion
            )
    
    async def _semantic_search_legacy(
        self, 
        db: AsyncIOMotorDatabase, 
        queries: List[str], 
        top_k: int, 
        user_id: Optional[str], 
        request_id: Optional[str], 
        query_rewrite_result: Optional[QueryRewriteResult], 
        similarity_threshold: float, 
        enable_query_expansion: bool
    ) -> List[SemanticSearchResult]:
        """傳統單階段語義搜索 - 保持原有AIQA邏輯"""
        
        all_results_map: Dict[str, SemanticSearchResult] = {}
        
        # 改進的元數據過濾
        chroma_metadata_filter: Dict[str, Any] = {}
        if query_rewrite_result and query_rewrite_result.extracted_parameters:
            file_type = query_rewrite_result.extracted_parameters.get("file_type") or (query_rewrite_result.extracted_parameters.get("document_types", [])[0] if query_rewrite_result.extracted_parameters.get("document_types") else None)
            if file_type: 
                chroma_metadata_filter["file_type"] = file_type

        # 使用統一的向量獲取接口
        query_vectors = await self._get_query_vectors(queries)
        
        try:
            owner_id_filter_for_vector_db = user_id if user_id else None

            for i, q_item in enumerate(queries):
                if q_item not in query_vectors:
                    continue
                    
                query_vector = query_vectors[q_item]
                # 根據查詢類型調整 top_k，確保多樣性
                adjusted_top_k = min(top_k * 2, 20) if len(queries) > 1 else top_k
                
                # 嘗試帶過濾條件的搜索
                results = vector_db_service.search_similar_vectors(
                    query_vector=query_vector, 
                    top_k=adjusted_top_k, 
                    owner_id_filter=owner_id_filter_for_vector_db, 
                    metadata_filter=chroma_metadata_filter,
                    similarity_threshold=similarity_threshold * 0.8  # 略微降低閾值以獲得更多候選
                )
                
                # 如果帶過濾條件的搜索沒有結果，且有 metadata_filter，則嘗試不帶 metadata_filter 的搜索
                if not results and chroma_metadata_filter:
                    logger.warning(f"帶 metadata_filter 的搜索沒有結果，嘗試回退搜索。Filter: {chroma_metadata_filter}")
                    results = vector_db_service.search_similar_vectors(
                        query_vector=query_vector, 
                        top_k=adjusted_top_k, 
                        owner_id_filter=owner_id_filter_for_vector_db, 
                        metadata_filter=None,  # 回退：移除 metadata_filter
                        similarity_threshold=similarity_threshold * 0.8
                    )
                    if results:
                        logger.info(f"回退搜索成功找到 {len(results)} 個結果")
                    
                # 使用統一的權重配置合併結果
                SearchWeightConfig.merge_weighted_results(all_results_map, results, i)

            # 重排序和多樣性優化
            final_results = list(all_results_map.values())
            final_results.sort(key=lambda x: x.similarity_score, reverse=True)
            
            # 多樣性優化
            if len(final_results) > top_k:
                final_results = self._apply_diversity_optimization(final_results, top_k)
            
            # 最終過濾：確保分數不低於調整後的閾值
            final_threshold = similarity_threshold
            final_results = [r for r in final_results if r.similarity_score >= final_threshold]
            
            return final_results[:top_k]
            
        except Exception as e:
            logger.error(f"語義搜索過程中發生異常: {e}", exc_info=True)
            return []

    async def _t2q_filter(self, db: AsyncIOMotorDatabase, document_ids: List[str], extracted_parameters: Dict[str, Any], user_id: Optional[str], request_id: Optional[str]) -> List[str]:
        # This function is no longer called in the main flow but is kept for potential future use.
        return document_ids

    async def _generate_answer_unified(self, db: AsyncIOMotorDatabase, original_query: str, documents_for_context: List[Any], query_rewrite_result: QueryRewriteResult, detailed_document_data: Optional[List[Dict[str, Any]]], ai_generated_query_reasoning: Optional[str], user_id: Optional[str], request_id: Optional[str], model_preference: Optional[str] = None, ensure_chinese_output: Optional[bool] = None, detailed_text_max_length: Optional[int] = None, max_chars_per_doc: Optional[int] = None, conversation_history: Optional[str] = None) -> Tuple[str, int, float, List[LLMContextDocument]]:
        """步驟4: 生成最終答案（使用統一AI服務）- Implements focused context logic."""
        actual_contexts_for_llm: List[LLMContextDocument] = []
        context_parts = []
        
        log_details_context = {
            "num_docs_for_context_initial": len(documents_for_context),
            "original_query_length": len(original_query),
            "intent": query_rewrite_result.intent_analysis[:100] if query_rewrite_result.intent_analysis else None,
            "has_detailed_document_data": bool(detailed_document_data)
        }
        await log_event(db=db, level=LogLevel.DEBUG, message="Assembling context for AI answer generation.",
                        source="service.enhanced_ai_qa.generate_answer_internal", user_id=user_id, request_id=request_id, details=log_details_context)

        try:
            # === 聚焦上下文邏輯：優先使用詳細資料，提升準確性並降低 Token 消耗 ===
            if detailed_document_data and len(detailed_document_data) > 0:
                logger.info(f"聚焦上下文路徑：使用來自 {len(detailed_document_data)} 個 AI 選中文件的詳細資料")
                
                for i, detail_item in enumerate(detailed_document_data):
                    doc_id_for_detail = str(detail_item.get("_id", f"unknown_detailed_doc_{i}"))
                    detailed_data_str = json.dumps(detail_item, ensure_ascii=False, indent=2)

                    context_preamble = f"智慧查詢文件 {doc_id_for_detail} 的詳細資料：\n"
                    if i == 0 and ai_generated_query_reasoning: # 在第一個文件顯示查詢推理
                        context_preamble += f"AI 查詢推理：{ai_generated_query_reasoning}\n\n"
                    
                    context_preamble += f"查詢到的精準資料：\n{detailed_data_str}\n\n"
                    context_parts.append(context_preamble)
                    actual_contexts_for_llm.append(LLMContextDocument(
                        document_id=doc_id_for_detail, 
                        content_used=detailed_data_str[:300], 
                        source_type="ai_detailed_query"
                    ))
                
                logger.info(f"使用聚焦上下文：{len(context_parts)} 個詳細查詢結果，總長度約 {sum(len(part) for part in context_parts)} 字符")
            
            # === 備用通用上下文邏輯：當沒有詳細資料時使用 ===
            else:
                logger.info("通用上下文路徑：沒有詳細資料可用，使用來自向量搜索的通用文件摘要")
                max_general_docs = 5

                for i, doc in enumerate(documents_for_context[:max_general_docs], 1):
                    doc_content_to_use = ""
                    content_source_type = "unknown_general"
                    doc_id_str = str(doc.id) if hasattr(doc, 'id') else f"unknown_general_doc_{i}"
                    
                    # 嘗試獲取 AI 分析的摘要
                    raw_extracted_text = getattr(doc, 'extracted_text', None)
                    ai_summary = None
                    if hasattr(doc, 'analysis') and doc.analysis and hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                        try:
                            analysis_output = AIDocumentAnalysisOutputDetail(**doc.analysis.ai_analysis_output)
                            if analysis_output.key_information and analysis_output.key_information.content_summary:
                                ai_summary = analysis_output.key_information.content_summary
                            elif analysis_output.initial_summary:
                                ai_summary = analysis_output.initial_summary
                        except (ValidationError, Exception):
                            pass
                    
                    # 選擇最佳的內容來源
                    if ai_summary:
                        doc_content_to_use, content_source_type = ai_summary, "general_ai_summary"
                    elif raw_extracted_text and isinstance(raw_extracted_text, str) and raw_extracted_text.strip():
                        # 截斷過長的原始文本
                        truncated_text = raw_extracted_text[:1000] + ("..." if len(raw_extracted_text) > 1000 else "")
                        doc_content_to_use, content_source_type = truncated_text, "general_extracted_text"
                    else:
                        doc_content_to_use, content_source_type = f"文件 '{getattr(doc, 'filename', 'N/A')}' 沒有可用的文字內容。", "general_placeholder"
                    
                    actual_contexts_for_llm.append(LLMContextDocument(
                        document_id=doc_id_str, 
                        content_used=doc_content_to_use[:300], 
                        source_type=content_source_type
                    ))
                    context_parts.append(f"通用上下文文件 {i} (ID: {doc_id_str}, 來源: {content_source_type}):\n{doc_content_to_use}")

                logger.info(f"使用通用上下文：{len(context_parts)} 個文件摘要，總長度約 {sum(len(part) for part in context_parts)} 字符")

            query_for_answer_gen = query_rewrite_result.rewritten_queries[0] if query_rewrite_result.rewritten_queries else original_query
            
            # 如果有對話歷史，將其添加到上下文開頭
            if conversation_history:
                context_parts.insert(0, conversation_history)
                logger.info("已將對話歷史添加到 AI 上下文中")

            log_details_ai_call = {"query_for_answer_gen_length": len(query_for_answer_gen), "num_docs_in_final_context": len(actual_contexts_for_llm), "total_context_length": len("\n\n".join(context_parts)), "model_preference": model_preference, "has_conversation_history": bool(conversation_history)}
            await log_event(db=db, level=LogLevel.DEBUG, message="Calling AI for answer generation.", source="service.enhanced_ai_qa.generate_answer_internal", user_id=user_id, request_id=request_id, details=log_details_ai_call)
            
            ai_response: UnifiedAIResponse = await unified_ai_service_simplified.generate_answer(
                user_question=query_for_answer_gen,
                intent_analysis=query_rewrite_result.intent_analysis or "",
                document_context=context_parts,
                db=db,
                model_preference=model_preference,
                ai_ensure_chinese_output=ensure_chinese_output,
                detailed_text_max_length=detailed_text_max_length,
                max_chars_per_doc=max_chars_per_doc
            )
            
            tokens_used = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
            answer_text = "Error: AI service did not return a successful response or content."
            confidence = 0.1

            if ai_response.success and ai_response.output_data:
                if isinstance(ai_response.output_data, AIGeneratedAnswerOutput):
                    answer_text = ai_response.output_data.answer_text
                else:
                    answer_text = f"Error: AI returned unexpected answer format: {type(ai_response.output_data).__name__}."
                
                confidence = min(0.9, 0.3 + (len(actual_contexts_for_llm) * 0.1) + (0.1 if not answer_text.lower().startswith("error") else -0.2))
                await log_event(db=db, level=LogLevel.INFO, message="AI answer generation successful.", source="service.enhanced_ai_qa.generate_answer_internal", user_id=user_id, request_id=request_id, details={"model_used": ai_response.model_used, "response_length": len(answer_text), "tokens": tokens_used, "confidence": confidence})
            else:
                error_msg = ai_response.error_message or "AI failed to generate answer."
                await log_event(db=db, level=LogLevel.ERROR, message=f"AI answer generation failed: {error_msg}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=user_id, request_id=request_id, details={**log_details_ai_call, "error": error_msg})
                answer_text = f"Sorry, I couldn't generate an answer: {error_msg}"

            return answer_text, tokens_used, confidence, actual_contexts_for_llm
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR, message=f"Unexpected error in _generate_answer_unified: {str(e)}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=user_id, request_id=request_id, details={"error_type": type(e).__name__})
            return f"An internal error occurred while generating the answer: {str(e)}", 0, 0.0, actual_contexts_for_llm

    async def _optimize_field_selection(
        self,
        db: AsyncIOMotorDatabase,
        user_question: str,
        document_analysis_summary: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        基於用戶問題智慧選擇需要的文檔欄位，避免查詢過多不必要的資料
        
        Args:
            user_question: 用戶問題
            document_analysis_summary: 文檔分析摘要
            
        Returns:
            優化後的 projection 配置
        """
        try:
            # 基於問題類型的智慧欄位映射
            field_mapping = {
                "summary": ["analysis.ai_analysis_output.key_information.content_summary", "analysis.summary"],
                "date": ["analysis.ai_analysis_output.key_information.dates_mentioned", "created_at", "updated_at"],
                "topic": ["analysis.ai_analysis_output.key_information.main_topics", "analysis.ai_analysis_output.key_information.semantic_tags"],
                "concept": ["analysis.ai_analysis_output.key_information.key_concepts", "analysis.key_terms"],
                "action": ["analysis.ai_analysis_output.key_information.action_items"],
                "content": ["extracted_text"],
                "metadata": ["filename", "file_type", "content_type_human_readable", "metadata"],
                "dynamic": ["analysis.ai_analysis_output.key_information.dynamic_fields"]
            }
            
            # 分析問題意圖
            question_lower = user_question.lower()
            selected_fields = set(["_id", "filename"])  # 基本必要欄位
            
            # 基於關鍵詞智慧選擇欄位
            if any(keyword in question_lower for keyword in ["總結", "摘要", "概要", "summary"]):
                selected_fields.update(field_mapping["summary"])
            
            if any(keyword in question_lower for keyword in ["日期", "時間", "when", "date"]):
                selected_fields.update(field_mapping["date"])
                
            if any(keyword in question_lower for keyword in ["主題", "話題", "topic", "about"]):
                selected_fields.update(field_mapping["topic"])
                
            if any(keyword in question_lower for keyword in ["概念", "concept", "key"]):
                selected_fields.update(field_mapping["concept"])
                
            if any(keyword in question_lower for keyword in ["待辦", "任務", "action", "todo"]):
                selected_fields.update(field_mapping["action"])
                
            if any(keyword in question_lower for keyword in ["內容", "文字", "content", "text", "具體", "詳細", "細節", "技術", "實現", "方式", "機制", "流程", "步驟"]):
                selected_fields.update(field_mapping["content"])
                
            if any(keyword in question_lower for keyword in ["檔名", "類型", "metadata", "file"]):
                selected_fields.update(field_mapping["metadata"])
            
            # 如果問題包含特定實體（如人名、公司名等），包含動態欄位
            if any(char.isupper() for char in user_question) or "誰" in question_lower or "who" in question_lower:
                selected_fields.update(field_mapping["dynamic"])
            
            # 如果沒有明確匹配，使用平衡策略
            if len(selected_fields) <= 2:
                selected_fields.update(field_mapping["summary"])
                selected_fields.update(field_mapping["topic"])
                selected_fields.update(field_mapping["dynamic"])
                # 對於複雜問題，也包含部分原始內容
                if any(complex_keyword in question_lower for complex_keyword in ["如何", "為什麼", "機制", "原理", "流程", "架構"]):
                    selected_fields.update(field_mapping["content"])
            
            # 建構 MongoDB projection
            projection = {field: 1 for field in selected_fields}
            
            await log_event(db=db, level=LogLevel.DEBUG,
                            message=f"智慧欄位選擇完成，選擇了 {len(selected_fields)} 個欄位",
                            source="service.enhanced_ai_qa.field_optimization",
                            user_id=user_id,
                            details={
                                "selected_fields": list(selected_fields),
                                "question_keywords": [kw for kw in ["總結", "日期", "主題", "概念", "待辦", "內容", "檔名"] if kw in question_lower],
                                "estimated_data_reduction": f"{max(0, 100 - len(selected_fields) * 10)}%"
                            })
            
            return projection
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR,
                            message=f"智慧欄位選擇失敗，使用預設配置: {str(e)}",
                            source="service.enhanced_ai_qa.field_optimization_error",
                            user_id=user_id,
                            details={"error": str(e)})
            
            # 回退到基本欄位選擇
            return {
                "_id": 1,
                "filename": 1,
                "analysis.ai_analysis_output.key_information": 1,
                "analysis.summary": 1
            }

    async def _batch_detailed_query(
        self,
        db: AsyncIOMotorDatabase,
        user_question: str,
        selected_documents: List[Any],
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        批次處理多個文檔的詳細查詢，減少AI調用次數
        
        Args:
            user_question: 用戶問題
            selected_documents: 已選擇的文檔列表
            
        Returns:
            批次查詢結果列表
        """
        try:
            if not selected_documents:
                return []
            
            # 獲取 Schema 緩存（現在通過緩存管理器處理）
            # 這裡準備 schema 資訊以供後續使用
            document_schema_info = {
                "description": "MongoDB 文檔 Schema 資訊",
                "fields": {
                    "analysis.ai_analysis_output.key_information": "結構化資訊",
                    "extracted_text": "文本內容",
                    "filename": "檔案名稱"
                }
            }
            schema_cache_name = await self.cache_manager.get_or_create_schema_cache(db, document_schema_info, user_id)
            
            all_detailed_data = []
            batch_size = 3  # 每批次處理的文檔數量
            
            for i in range(0, len(selected_documents), batch_size):
                batch_docs = selected_documents[i:i + batch_size]
                
                # 為當前批次構建上下文
                batch_context = f"用戶問題：{user_question}\n\n"
                batch_context += "需要查詢的文檔列表：\n"
                
                for j, doc in enumerate(batch_docs, 1):
                    doc_summary = "無可用摘要"
                    if hasattr(doc, 'analysis') and doc.analysis:
                        if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                            try:
                                analysis_output = doc.analysis.ai_analysis_output
                                if 'key_information' in analysis_output and 'content_summary' in analysis_output['key_information']:
                                    doc_summary = analysis_output['key_information']['content_summary']
                            except Exception:
                                pass
                    
                    batch_context += f"{j}. 文檔ID: {doc.id}\n"
                    batch_context += f"   檔名: {getattr(doc, 'filename', 'Unknown')}\n"
                    batch_context += f"   摘要: {doc_summary}\n\n"
                
                # 使用智慧欄位選擇
                optimized_projection = await self._optimize_field_selection(
                    db, user_question, batch_context, user_id
                )
                
                await log_event(db=db, level=LogLevel.INFO,
                                message=f"開始批次處理 {len(batch_docs)} 個文檔（批次 {i//batch_size + 1}）",
                                source="service.enhanced_ai_qa.batch_detailed_query",
                                user_id=user_id, request_id=request_id,
                                details={
                                    "batch_size": len(batch_docs),
                                    "batch_number": i//batch_size + 1,
                                    "total_batches": (len(selected_documents) + batch_size - 1) // batch_size,
                                    "optimized_fields_count": len(optimized_projection)
                                })
                
                # 對批次中的每個文檔執行查詢
                for doc in batch_docs:
                    try:
                        # 使用優化的 projection 查詢文檔
                        mongo_filter = {"_id": doc.id}
                        safe_projection = remove_projection_path_collisions(optimized_projection)
                        fetched_data = await db.documents.find_one(mongo_filter, projection=safe_projection)
                        
                        if fetched_data:
                            # 資料清理
                            def sanitize(data: Any) -> Any:
                                if isinstance(data, dict): 
                                    return {k: sanitize(v) for k, v in data.items()}
                                if isinstance(data, list): 
                                    return [sanitize(i) for i in data]
                                if isinstance(data, uuid.UUID): 
                                    return str(data)
                                return data
                            
                            all_detailed_data.append(sanitize(fetched_data))
                            logger.info(f"批次查詢成功獲取文檔 {doc.id} 的資料")
                        else:
                            logger.warning(f"批次查詢中文檔 {doc.id} 沒有返回資料")
                            
                    except Exception as doc_error:
                        logger.error(f"批次查詢文檔 {doc.id} 時發生錯誤: {str(doc_error)}")
                        continue
                
                # 批次間的小延遲，避免過度負載
                if i + batch_size < len(selected_documents):
                    await asyncio.sleep(0.1)
            
            await log_event(db=db, level=LogLevel.INFO,
                            message=f"批次詳細查詢完成，成功處理 {len(all_detailed_data)}/{len(selected_documents)} 個文檔",
                            source="service.enhanced_ai_qa.batch_detailed_query_complete",
                            user_id=user_id, request_id=request_id,
                            details={
                                "total_requested": len(selected_documents),
                                "successful_queries": len(all_detailed_data),
                                "success_rate": f"{len(all_detailed_data)/len(selected_documents)*100:.1f}%" if selected_documents else "0%"
                            })
            
            return all_detailed_data
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR,
                            message=f"批次詳細查詢失敗: {str(e)}",
                            source="service.enhanced_ai_qa.batch_detailed_query_error",
                            user_id=user_id, request_id=request_id,
                            details={"error": str(e), "document_count": len(selected_documents) if selected_documents else 0})
            return []

enhanced_ai_qa_service = EnhancedAIQAService()