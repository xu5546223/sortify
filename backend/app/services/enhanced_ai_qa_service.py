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

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class EnhancedAIQAService:
    """增強的AI問答服務 - 使用統一AI管理架構和專門的緩存管理器"""
    
    def __init__(self):
        # 使用專門的緩存管理器
        self.cache_manager = ai_cache_manager
        logger.info("EnhancedAIQAService 初始化完成，使用專門的 AI 緩存管理器")
    
# 注意：_get_or_create_schema_cache 和 _get_or_create_system_instruction_cache 方法
# 現在通過 self.cache_manager 統一管理，不再需要在此類中單獨實現

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
                        source="service.enhanced_ai_qa.request", user_id=str(user_id) if user_id else None, request_id=request_id,
                        details=log_details_initial)

        query_rewrite_result: Optional[QueryRewriteResult] = None
        semantic_contexts_for_response: List[SemanticContextDocument] = []

        try:
            query_rewrite_result, rewrite_tokens = await self._rewrite_query_unified(
                db, request.question, user_id, request_id, 
                query_rewrite_count=getattr(request, 'query_rewrite_count', 3)
            )
            total_tokens += rewrite_tokens
            
            semantic_results_raw = await self._semantic_search(
                db,
                query_rewrite_result.rewritten_queries if query_rewrite_result.rewritten_queries else [request.question],
                getattr(request, 'max_documents_for_selection', request.context_limit),  # 使用候選文件數量
                user_id,
                request_id,
                query_rewrite_result=query_rewrite_result,
                similarity_threshold=getattr(request, 'similarity_threshold', 0.3),  # 使用相似度閾值
                enable_query_expansion=getattr(request, 'enable_query_expansion', True)  # 使用查詢擴展設定
            )

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
            
            if not isinstance(document_ids, list):
                logger.error(f"Before get_documents_by_ids, document_ids is not a list, but {type(document_ids)}. Defaulting to empty list.")
                document_ids = []

            full_documents = await get_documents_by_ids(db, document_ids)
            
            if user_id:
                full_documents = await self._filter_accessible_documents(db, full_documents, str(user_id), request_id)
            
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
                    str(user_id) if user_id else None, request_id,
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
                                user_id=str(user_id) if user_id else None,
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
                                    fetched_data = await db.documents.find_one(mongo_filter, projection=mongo_projection or None)
                                    
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
                                        
                                        fallback_data = await db.documents.find_one(fallback_filter, projection=fallback_projection)
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
                user_id,
                request_id,
                request.model_preference,
                ensure_chinese_output=getattr(request, 'ensure_chinese_output', None),
                detailed_text_max_length=getattr(request, 'detailed_text_max_length', 8000),  # 傳遞用戶設定的文本長度限制
                max_chars_per_doc=getattr(request, 'max_chars_per_doc', None)  # 傳遞用戶設定的單文檔限制
            )
            total_tokens += answer_tokens
            
            processing_time = time.time() - start_time
            
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
                            source="service.enhanced_ai_qa.process_request_error", user_id=str(user_id) if user_id else None, request_id=request_id,
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

        # 第一步：根據相似度分數進行初步篩選和去重
        # 去除相似度過低的文件（<0.3），並按文件ID去重
        filtered_contexts = {}
        
        for ctx in semantic_contexts:
            # 相似度篩選
            if ctx.similarity_score < similarity_threshold:
                continue
                
            # 去重：如果同一個文件有多個片段，選擇相似度最高的
            if ctx.document_id not in filtered_contexts or ctx.similarity_score > filtered_contexts[ctx.document_id].similarity_score:
                filtered_contexts[ctx.document_id] = ctx
        
        # 按相似度排序
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
        ai_response = await unified_ai_service_simplified.rewrite_query(original_query=original_query, db=db)
        tokens = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
        if ai_response.success and isinstance(ai_response.output_data, AIQueryRewriteOutput):
            output = ai_response.output_data
            return QueryRewriteResult(original_query=original_query, rewritten_queries=output.rewritten_queries, extracted_parameters=output.extracted_parameters, intent_analysis=output.intent_analysis), tokens
        return QueryRewriteResult(original_query=original_query, rewritten_queries=[original_query], extracted_parameters={}, intent_analysis="Query rewrite failed."), tokens

    async def _semantic_search(self, db: AsyncIOMotorDatabase, queries: List[str], top_k: int, user_id: Optional[str], request_id: Optional[str], query_rewrite_result: Optional[QueryRewriteResult], similarity_threshold: float, enable_query_expansion: bool) -> List[SemanticSearchResult]:
        all_results_map: Dict[str, SemanticSearchResult] = {}
        chroma_metadata_filter: Dict[str, Any] = {}
        if query_rewrite_result and query_rewrite_result.extracted_parameters:
            file_type = query_rewrite_result.extracted_parameters.get("file_type") or (query_rewrite_result.extracted_parameters.get("document_types", [])[0] if query_rewrite_result.extracted_parameters.get("document_types") else None)
            if file_type: chroma_metadata_filter["file_type"] = file_type

        # 使用緩存管理器處理查詢向量緩存
        uncached_queries = [q for q in queries if self.cache_manager.get_query_embedding(q) is None]
        if uncached_queries:
            query_vectors = embedding_service.encode_batch(uncached_queries)
            self.cache_manager.batch_set_query_embeddings(uncached_queries, query_vectors)
        
        try:
            owner_id_filter_for_vector_db = user_id
            if isinstance(owner_id_filter_for_vector_db, uuid.UUID):
                owner_id_filter_for_vector_db = str(owner_id_filter_for_vector_db)

            for i, q_item in enumerate(queries):
                query_vector = self.cache_manager.get_query_embedding(q_item)
                if query_vector:
                    # 嘗試帶過濾條件的搜索
                    results = vector_db_service.search_similar_vectors(
                        query_vector=query_vector, 
                        top_k=top_k, 
                        owner_id_filter=owner_id_filter_for_vector_db, 
                        metadata_filter=chroma_metadata_filter
                    )
                    
                    # 如果帶過濾條件的搜索沒有結果，且有 metadata_filter，則嘗試不帶 metadata_filter 的搜索
                    if not results and chroma_metadata_filter:
                        logger.warning(f"帶 metadata_filter 的搜索沒有結果，嘗試回退搜索。Filter: {chroma_metadata_filter}")
                        results = vector_db_service.search_similar_vectors(
                            query_vector=query_vector, 
                            top_k=top_k, 
                            owner_id_filter=owner_id_filter_for_vector_db, 
                            metadata_filter=None  # 回退：移除 metadata_filter
                        )
                        if results:
                            logger.info(f"回退搜索成功找到 {len(results)} 個結果")
                    
                    for res in results:
                        if res.document_id not in all_results_map or res.similarity_score > all_results_map[res.document_id].similarity_score:
                            all_results_map[res.document_id] = res
        
        except Exception as e:
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"Unexpected error in _semantic_search: {str(e)}",
                source="service.enhanced_ai_qa._semantic_search",
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                details={"error_type": type(e).__name__, "error": str(e)}
            )
            return []
        
        combined = sorted(all_results_map.values(), key=lambda r: r.similarity_score, reverse=True)
        return combined

    async def _t2q_filter(self, db: AsyncIOMotorDatabase, document_ids: List[str], extracted_parameters: Dict[str, Any], user_id: Optional[str], request_id: Optional[str]) -> List[str]:
        # This function is no longer called in the main flow but is kept for potential future use.
        return document_ids

    async def _generate_answer_unified(self, db: AsyncIOMotorDatabase, original_query: str, documents_for_context: List[Any], query_rewrite_result: QueryRewriteResult, detailed_document_data: Optional[List[Dict[str, Any]]], ai_generated_query_reasoning: Optional[str], user_id: Optional[str], request_id: Optional[str], model_preference: Optional[str] = None, ensure_chinese_output: Optional[bool] = None, detailed_text_max_length: Optional[int] = None, max_chars_per_doc: Optional[int] = None) -> Tuple[str, int, float, List[LLMContextDocument]]:
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
                        source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details_context)

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

            log_details_ai_call = {"query_for_answer_gen_length": len(query_for_answer_gen), "num_docs_in_final_context": len(actual_contexts_for_llm), "total_context_length": len("\n\n".join(context_parts)), "model_preference": model_preference}
            await log_event(db=db, level=LogLevel.DEBUG, message="Calling AI for answer generation.", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details_ai_call)
            
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
                await log_event(db=db, level=LogLevel.INFO, message="AI answer generation successful.", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={"model_used": ai_response.model_used, "response_length": len(answer_text), "tokens": tokens_used, "confidence": confidence})
            else:
                error_msg = ai_response.error_message or "AI failed to generate answer."
                await log_event(db=db, level=LogLevel.ERROR, message=f"AI answer generation failed: {error_msg}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={**log_details_ai_call, "error": error_msg})
                answer_text = f"Sorry, I couldn't generate an answer: {error_msg}"

            return answer_text, tokens_used, confidence, actual_contexts_for_llm
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR, message=f"Unexpected error in _generate_answer_unified: {str(e)}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={"error_type": type(e).__name__})
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
                
            if any(keyword in question_lower for keyword in ["內容", "文字", "content", "text"]):
                selected_fields.update(field_mapping["content"])
                
            if any(keyword in question_lower for keyword in ["檔名", "類型", "metadata", "file"]):
                selected_fields.update(field_mapping["metadata"])
            
            # 如果問題包含特定實體（如人名、公司名等），包含動態欄位
            if any(char.isupper() for char in user_question) or "誰" in question_lower or "who" in question_lower:
                selected_fields.update(field_mapping["dynamic"])
            
            # 如果沒有明確匹配，使用保守策略（包含更多欄位）
            if len(selected_fields) <= 2:
                selected_fields.update(field_mapping["summary"])
                selected_fields.update(field_mapping["topic"])
                selected_fields.update(field_mapping["dynamic"])
            
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
                        fetched_data = await db.documents.find_one(mongo_filter, projection=optimized_projection)
                        
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