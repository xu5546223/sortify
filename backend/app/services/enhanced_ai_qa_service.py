from typing import List, Optional, Dict, Any, Tuple
import time
# import json # Unused
import uuid
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.services.unified_ai_service_simplified import unified_ai_service_simplified, AIResponse as UnifiedAIResponse # Alias
from app.services.embedding_service import embedding_service
from app.services.vector_db_service import vector_db_service
from app.models.vector_models import (
    AIQARequest, AIQAResponse, QueryRewriteResult, LLMContextDocument,
    # SemanticSearchRequest, # Unused
    SemanticSearchResult, SemanticContextDocument
)
from app.models.ai_models_simplified import TokenUsage
from app.models.ai_models_simplified import (
    # AITextAnalysisOutput, # Unused
    AIQueryRewriteOutput,
    AIDocumentAnalysisOutputDetail, AIDocumentKeyInformation, # AIDocumentKeyInformation is likely used by AIDocumentAnalysisOutputDetail
    AIGeneratedAnswerOutput 
)
from app.crud.crud_documents import get_documents_by_ids
from pydantic import ValidationError
import logging
from datetime import datetime
import traceback

from cachetools import LRUCache # Added for caching

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class EnhancedAIQAService:
    """增強的AI問答服務 - 使用統一AI管理架構"""
    
    def __init__(self):
        # 使用統一的AI服務，不再需要單獨的AI服務實例
        self.query_embedding_cache: LRUCache[str, List[float]] = LRUCache(maxsize=128)
        logger.info(f"EnhancedAIQAService initialized with LRUCache for query embeddings (maxsize={self.query_embedding_cache.maxsize}).")
    
    async def process_qa_request(
        self, 
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: Optional[str] = None, # Made Optional
        request_id: Optional[str] = None # Added for propagated request_id
    ) -> AIQAResponse:
        """
        處理AI問答請求的主要流程 - 支持用戶認證
        """
        start_time = time.time()
        total_tokens = 0
        
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

        query_rewrite_result: Optional[QueryRewriteResult] = None # Ensure it's defined for error return
        semantic_contexts_for_response: List[SemanticContextDocument] = [] # Ensure defined

        try:
            query_rewrite_result, rewrite_tokens = await self._rewrite_query_unified(
                db, request.question, user_id, request_id
            )
            total_tokens += rewrite_tokens
            
            semantic_results_raw = await self._semantic_search(
                db, # Pass db instance
                query_rewrite_result.rewritten_queries[0] if query_rewrite_result.rewritten_queries else request.question,
                request.context_limit,
                user_id, # Pass user_id
                request_id # Pass request_id
            )

            # 將原始 semantic_results 轉換為 SemanticContextDocument 列表
            semantic_contexts_for_response: List[SemanticContextDocument] = []
            if not isinstance(semantic_results_raw, list): # Ensure semantic_results_raw is a list
                logger.error(f"semantic_results_raw is not a list, but {type(semantic_results_raw)}. Defaulting to empty list.")
                semantic_results_raw = []
            
            if semantic_results_raw:
                for res in semantic_results_raw:
                    semantic_contexts_for_response.append(
                        SemanticContextDocument(
                            document_id=res.document_id,
                            summary_or_chunk_text=res.summary_text, # SemanticSearchResult 有 summary_text
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
                    semantic_search_contexts=semantic_contexts_for_response, # 即使為空也傳遞
                    session_id=request.session_id
                )
            
            # 獲取文檔ID列表
            document_ids = [result.document_id for result in semantic_results_raw]
            
            # 步驟3: T2Q二次過濾（可選）
            if request.use_structured_filter and query_rewrite_result.extracted_parameters:
                filtered_document_ids = await self._t2q_filter(
                    db, document_ids, query_rewrite_result.extracted_parameters, user_id, request_id # Pass user_id and request_id
                )
                if filtered_document_ids:
                    document_ids = filtered_document_ids
                    # Add check for document_ids before len()
                    if not isinstance(document_ids, list):
                        logger.error(f"After _t2q_filter, document_ids is not a list, but {type(document_ids)}. Value: {document_ids}. Defaulting to empty list.")
                        document_ids = []
                    logger.info(f"T2Q過濾後剩餘 {len(document_ids)} 個文檔")
            
            # Add another check for document_ids before get_documents_by_ids, if not filtered
            elif not isinstance(document_ids, list): # If not filtered, document_ids comes from semantic_results_raw
                logger.error(f"Before get_documents_by_ids (no T2Q filter), document_ids is not a list, but {type(document_ids)}. Value: {document_ids}. Defaulting to empty list.")
                document_ids = []

            # 步驟4: 獲取完整文檔內容（檢查用戶權限）
            full_documents = await get_documents_by_ids(db, document_ids)
            
            # 過濾用戶有權限訪問的文檔
            if user_id:
                try:
                    # user_uuid = uuid.UUID(user_id)
                    # 修正 user_uuid 的獲取方式
                    if isinstance(user_id, uuid.UUID):
                        user_uuid = user_id
                    elif isinstance(user_id, str):
                        user_uuid = uuid.UUID(user_id)
                    else:
                        logger.error(f"無法識別的 user_id 類型: {type(user_id)}，值: {user_id}. 無法執行權限檢查。")
                        full_documents = [] 

                    accessible_documents = []
                    if full_documents: 
                        for doc in full_documents:
                            # Ensure doc.owner_id is also a UUID object for comparison
                            # (It should be if retrieved from DB correctly and model types are right)
                            if hasattr(doc, 'owner_id') and isinstance(doc.owner_id, uuid.UUID) and doc.owner_id == user_uuid:
                                accessible_documents.append(doc)
                            else:
                                # Log if owner_id is not a UUID for debugging data issues
                                if hasattr(doc, 'owner_id') and not isinstance(doc.owner_id, uuid.UUID):
                                    logger.warning(f"Document ID {getattr(doc, 'id', 'N/A')} has owner_id of type {type(doc.owner_id)}, expected UUID.")
                                logger.debug(f"用戶 {user_id} (UUID: {user_uuid if 'user_uuid' in locals() else 'N/A'}) 無權訪問文檔 {getattr(doc, 'id', 'N/A')} (Owner: {getattr(doc, 'owner_id', 'N/A')})")
                        full_documents = accessible_documents
                except ValueError as e_uuid:
                    logger.error(f"無效的 user_id 格式: {user_id} (錯誤: {e_uuid})，無法執行權限過濾。")
                    full_documents = [] # Treat as no accessible documents if user_id is invalid string
            
            if not full_documents:
                logger.warning("用戶無權限訪問相關文檔或獲取文檔內容失敗")
                return AIQAResponse(
                    answer="找到了相關文檔，但您可能沒有訪問權限，或獲取詳細內容時出現問題。",
                    source_documents=[],
                    confidence_score=0.3,
                    tokens_used=total_tokens,
                    processing_time=time.time() - start_time,
                    query_rewrite_result=query_rewrite_result,
                    semantic_search_contexts=semantic_contexts_for_response, # 傳遞
                    session_id=request.session_id
                )
            
            # 步驟5: 生成最終答案（使用統一AI服務）
            answer, answer_tokens, confidence, actual_contexts_for_llm = await self._generate_answer_unified(
                db, request.question, full_documents, query_rewrite_result, user_id, request_id, request.model_preference # Pass user_id, request_id and model_preference
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
                semantic_search_contexts=semantic_contexts_for_response, # 傳遞
                session_id=request.session_id,
                llm_context_documents=actual_contexts_for_llm
            )
            
        except Exception as e:
            processing_time_on_error = time.time() - start_time
            error_trace = traceback.format_exc() # Make sure traceback is imported
            await log_event(db=db, level=LogLevel.ERROR, message=f"Enhanced AI QA failed: {str(e)}",
                            source="service.enhanced_ai_qa.process_request_error", user_id=str(user_id) if user_id else None, request_id=request_id,
                            details={"error": str(e), "error_type": type(e).__name__, "traceback": error_trace, **log_details_initial})
            
            # Ensure total_tokens is an int, default to 0 if not (though it should be an int already)
            current_total_tokens = total_tokens if isinstance(total_tokens, int) else 0
            
            # Ensure query_rewrite_result is valid or provide a fallback
            current_qrr: Optional[QueryRewriteResult] = query_rewrite_result
            if not isinstance(current_qrr, QueryRewriteResult):
                current_qrr = QueryRewriteResult(
                    original_query=request.question, 
                    rewritten_queries=[request.question], 
                    extracted_parameters={},
                    intent_analysis="Error occurred before query rewrite completed or result was invalid."
                )

            # Ensure semantic_contexts_for_response is a list
            current_semantic_contexts = semantic_contexts_for_response
            if not isinstance(current_semantic_contexts, list):
                current_semantic_contexts = []

            return AIQAResponse(
                answer=f"An error occurred while processing your question: {str(e)}", 
                source_documents=[], 
                confidence_score=0.0, 
                tokens_used=current_total_tokens,
                processing_time=processing_time_on_error,
                query_rewrite_result=current_qrr,
                semantic_search_contexts=current_semantic_contexts, 
                session_id=request.session_id,
                llm_context_documents=[], 
                error_message=str(e) 
            )

    async def _filter_accessible_documents(
        self, 
        db: AsyncIOMotorDatabase, # For logging
        full_documents: List[Any], # Assuming Document model instances
        user_id_str: Optional[str], 
        request_id: Optional[str]
    ) -> List[Any]:
        """
        Filters a list of documents based on user ownership.
        Logs access attempts and errors.
        """
        if not user_id_str: # No user_id means public access or no filtering needed at this stage
            return full_documents

        accessible_documents = []
        user_uuid: Optional[uuid.UUID] = None

        try:
            user_uuid = uuid.UUID(user_id_str)
        except ValueError as e_uuid:
            await log_event(db=db, level=LogLevel.ERROR, 
                            message=f"Invalid user_id format for access filtering: {user_id_str} (Error: {e_uuid}). No documents will be accessible.",
                            source="service.enhanced_ai_qa._filter_accessible_documents", user_id=user_id_str, request_id=request_id)
            return [] # No documents accessible if user_id is malformed

        if not full_documents:
            return []

        for doc in full_documents:
            doc_id_for_log = getattr(doc, 'id', 'N/A')
            owner_id_for_log = getattr(doc, 'owner_id', 'N/A')

            if hasattr(doc, 'owner_id') and isinstance(doc.owner_id, uuid.UUID) and doc.owner_id == user_uuid:
                accessible_documents.append(doc)
            else:
                if hasattr(doc, 'owner_id') and not isinstance(doc.owner_id, uuid.UUID):
                    logger.warning(f"Document ID {doc_id_for_log} has owner_id of type {type(doc.owner_id)}, expected UUID.")
                
                log_details_permission = {
                    "document_id": str(doc_id_for_log),
                    "document_owner_id": str(owner_id_for_log),
                    "target_user_uuid": str(user_uuid)
                }
                await log_event(db=db, level=LogLevel.DEBUG, # Changed to DEBUG as it's an expected operational log
                                message=f"User {user_id_str} does not have permission for document {doc_id_for_log}.",
                                source="service.enhanced_ai_qa._filter_accessible_documents", user_id=user_id_str, request_id=request_id,
                                details=log_details_permission)
        
        return accessible_documents

    async def _rewrite_query_unified(
        self, 
        db: AsyncIOMotorDatabase,
        original_query: str,
        user_id: Optional[str],
        request_id: Optional[str]
    ) -> Tuple[QueryRewriteResult, int]:
        """步驟1: 查詢理解與重寫（使用統一AI服務）"""
        log_details = {"original_query_length": len(original_query)}
        await log_event(db=db, level=LogLevel.DEBUG, message="Starting query rewrite using unified AI service.",
                        source="service.enhanced_ai_qa.rewrite_query_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details)

        try:
            ai_response: UnifiedAIResponse = await unified_ai_service_simplified.rewrite_query(
                original_query=original_query, db=db
            )
            tokens = ai_response.token_usage.total_tokens if ai_response.token_usage else 0

            if not ai_response.success or not ai_response.output_data:
                error_msg = ai_response.error_message or "AI query rewrite returned no content or failed."
                await log_event(db=db, level=LogLevel.WARNING, message=f"Query rewrite failed or no content: {error_msg}",
                                source="service.enhanced_ai_qa.rewrite_query_internal", user_id=str(user_id) if user_id else None, request_id=request_id,
                                details={**log_details, "error": error_msg, "ai_success": ai_response.success})
                return QueryRewriteResult(original_query=original_query, rewritten_queries=[original_query], extracted_parameters={}, intent_analysis=f"Query rewrite failed: {error_msg}"), tokens

            content_data = ai_response.output_data
            parsed_output: Optional[AIQueryRewriteOutput] = None
            query_rewrite_result: QueryRewriteResult

            if isinstance(content_data, AIQueryRewriteOutput):
                parsed_output = content_data
                log_msg_parse = "Successfully used pre-parsed AIQueryRewriteOutput model."
            elif isinstance(content_data, dict):
                log_msg_parse = "Attempting to parse content_data dict using AIQueryRewriteOutput model."
                try:
                    parsed_output = AIQueryRewriteOutput(**content_data)
                except ValidationError as ve:
                    await log_event(db=db, level=LogLevel.WARNING, message=f"Validation error parsing AI query rewrite dict: {ve}. Content: {content_data}",
                                    source="service.enhanced_ai_qa.rewrite_query_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
                    parsed_output = None # Ensure fallback
            else: # Fallback for unexpected content_data types
                log_msg_parse = f"content_data is of unexpected type: {type(content_data)}. Using fallback values."
                parsed_output = None

            if parsed_output:
                # Ensure rewritten_queries contains only strings
                raw_queries = parsed_output.rewritten_queries
                processed_queries = []
                if isinstance(raw_queries, list):
                    # Ensure elements are strings and filter out None before str conversion
                    processed_queries = [str(q) for q in raw_queries if q is not None]
                elif raw_queries is not None: # If it's a single item, not a list
                    processed_queries = [str(raw_queries)]

                if not processed_queries: # Fallback if list is empty or all items were None
                    processed_queries = [str(original_query)]
                    
                query_rewrite_result = QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=processed_queries, # Use processed list
                    extracted_parameters=parsed_output.extracted_parameters if parsed_output.extracted_parameters else {},
                    intent_analysis=parsed_output.intent_analysis or "Intent analysis not provided."
                )
                log_msg_parse += f" Intent: {query_rewrite_result.intent_analysis[:50]}"
            else: # Fallback if parsing failed or type was unexpected
                query_rewrite_result = QueryRewriteResult(
                    original_query=original_query, rewritten_queries=[str(original_query)], extracted_parameters={},
                    intent_analysis=log_msg_parse # Use the parsing status as intent analysis
                )
            
            await log_event(db=db, level=LogLevel.DEBUG, message=f"Query rewrite processing complete. {log_msg_parse}",
                            source="service.enhanced_ai_qa.rewrite_query_internal", user_id=str(user_id) if user_id else None, request_id=request_id,
                            details={"rewritten_queries_count": len(query_rewrite_result.rewritten_queries), "params_extracted": bool(query_rewrite_result.extracted_parameters)})
            return query_rewrite_result, tokens
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR, message=f"Error during unified AI service query rewrite call: {str(e)}",
                            source="service.enhanced_ai_qa.rewrite_query_internal", user_id=str(user_id) if user_id else None, request_id=request_id,
                            details={**log_details, "error": str(e), "error_type": type(e).__name__})
            return QueryRewriteResult(original_query=original_query, rewritten_queries=[original_query], extracted_parameters={}, intent_analysis=f"Query rewrite error: {str(e)}"), 0
    
    async def _semantic_search(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int = 10,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        query_rewrite_result: Optional[QueryRewriteResult] = None # New parameter
    ) -> List[SemanticSearchResult]:
        """步驟2: 向量搜索 - Modified to handle multiple queries, combine results, and apply metadata filters."""
        final_user_id_for_log: Optional[str] = str(user_id) if user_id is not None else None

        logger.debug(f"In _semantic_search, entry: type(db) is {type(db)}, db is {str(db)[:200]}")

        if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            logger.error(f"_semantic_search: queries is not a list of strings. Received: {type(queries)}. Auto-wrapping original query if possible, or using empty list.")
            # Attempt to recover if a single string was passed, else log error and use empty list
            if isinstance(queries, str): # This case should ideally not happen if called correctly
                 queries = [queries]
            else:
                 queries = [] # Cannot proceed with non-string queries

        log_details = {
            "num_queries": len(queries),
            "first_query_length": len(queries[0]) if queries else 0,
            "top_k_per_query": top_k,
            "user_id_filter_for_search": user_id
        }
        await log_event(db=db, level=LogLevel.DEBUG, message="Starting semantic search for multiple queries.",
                        source="service.enhanced_ai_qa.semantic_search_internal", user_id=final_user_id_for_log, request_id=request_id, details=log_details)

        all_results_map: Dict[str, SemanticSearchResult] = {}

        chroma_metadata_filter: Dict[str, Any] = {}
        if query_rewrite_result and query_rewrite_result.extracted_parameters:
            file_type_param = query_rewrite_result.extracted_parameters.get("file_type")
            document_types_param = query_rewrite_result.extracted_parameters.get("document_types")

            if isinstance(file_type_param, str) and file_type_param.strip():
                chroma_metadata_filter["file_type"] = file_type_param.strip()
                logger.debug(f"Applying metadata filter for file_type: {file_type_param.strip()}")
            elif isinstance(document_types_param, list) and document_types_param and isinstance(document_types_param[0], str) and document_types_param[0].strip():
                chroma_metadata_filter["file_type"] = document_types_param[0].strip()
                logger.debug(f"Applying metadata filter for file_type from document_types: {document_types_param[0].strip()}")

        log_details["metadata_filter_applied"] = list(chroma_metadata_filter.keys()) if chroma_metadata_filter else "None"

        # --- Batch Embedding Attempt (Fallback Strategy) ---
        unique_valid_queries_to_embed = []
        if queries:
            seen_queries = set()
            for q_item_for_batch in queries:
                if isinstance(q_item_for_batch, str) and q_item_for_batch.strip():
                    stripped_q = q_item_for_batch.strip()
                    if stripped_q not in self.query_embedding_cache and stripped_q not in seen_queries:
                        unique_valid_queries_to_embed.append(stripped_q)
                        seen_queries.add(stripped_q)

        if unique_valid_queries_to_embed:
            logger.info(f"Found {len(unique_valid_queries_to_embed)} unique queries not in cache. Attempting batch encoding.")
            try:
                if hasattr(embedding_service, 'encode_batch'):
                    query_vectors_batch = embedding_service.encode_batch(unique_valid_queries_to_embed)
                    for q_str, vec in zip(unique_valid_queries_to_embed, query_vectors_batch):
                        self.query_embedding_cache[q_str] = vec
                    logger.info(f"Successfully batch encoded and cached {len(unique_valid_queries_to_embed)} new query embeddings.")
                else:
                    logger.warning("embedding_service does not have 'encode_batch' method. Falling back to per-query encoding within the loop for uncached items.")
                    # No explicit action needed here, per-query logic below will handle it.
            except Exception as e_batch_embed:
                logger.error(f"Error during batch embedding: {e_batch_embed}. Will attempt per-query encoding for these items.", exc_info=True)
        # --- End of Batch Embedding Attempt ---

        try:
            owner_id_filter_for_vector_db = user_id
            if isinstance(owner_id_filter_for_vector_db, uuid.UUID):
                owner_id_filter_for_vector_db = str(owner_id_filter_for_vector_db)

            for i, q_item in enumerate(queries):
                query_log_details = {**log_details, "current_query_index": i, "current_query_length": len(q_item)}

                if not isinstance(q_item, str) or not q_item.strip():
                    await log_event(db=db, level=LogLevel.WARNING, message=f"Skipping empty or invalid query string at index {i}.",
                                    source="service.enhanced_ai_qa.semantic_search_internal.skip_query", user_id=final_user_id_for_log, request_id=request_id, details=query_log_details)
                    continue

                stripped_q_item = q_item.strip()
                query_vector: Optional[List[float]] = None

                # Caching Logic
                if stripped_q_item in self.query_embedding_cache:
                    query_vector = self.query_embedding_cache[stripped_q_item]
                    logger.debug(f"Query embedding cache HIT for: '{stripped_q_item[:50]}...'")
                    query_log_details["embedding_source"] = "cache_hit"
                else:
                    logger.debug(f"Query embedding cache MISS for: '{stripped_q_item[:50]}...'. Encoding now.")
                    query_log_details["embedding_source"] = "cache_miss_encoded_now"
                    try:
                        query_vector = embedding_service.encode_text(stripped_q_item)
                        self.query_embedding_cache[stripped_q_item] = query_vector
                    except Exception as e_single_encode:
                        await log_event(db=db, level=LogLevel.ERROR, message=f"Failed to encode query '{stripped_q_item[:50]}...': {e_single_encode}",
                                        source="service.enhanced_ai_qa.semantic_search_internal.encode_error", user_id=final_user_id_for_log, request_id=request_id, details=query_log_details)
                        continue # Skip this query if encoding fails

                if query_vector is None: # Should not happen if logic above is correct, but as a safeguard
                    await log_event(db=db, level=LogLevel.ERROR, message=f"Query vector is None for '{stripped_q_item[:50]}...' after caching/encoding attempts.",
                                    source="service.enhanced_ai_qa.semantic_search_internal.vector_none", user_id=final_user_id_for_log, request_id=request_id, details=query_log_details)
                    continue

                await log_event(db=db, level=LogLevel.DEBUG, message=f"Processing query {i+1}/{len(queries)}: '{stripped_q_item[:100]}...' (Embedding from: {query_log_details.get('embedding_source', 'unknown')})",
                                source="service.enhanced_ai_qa.semantic_search_internal.query_item", user_id=final_user_id_for_log, request_id=request_id, details=query_log_details)

                current_results = vector_db_service.search_similar_vectors(
                    query_vector=query_vector, # type: ignore # query_vector is List[float] here
                    top_k=top_k,
                    similarity_threshold=0.3,
                    owner_id_filter=owner_id_filter_for_vector_db,
                    metadata_filter=chroma_metadata_filter # Pass the constructed filter
                )

                await log_event(db=db, level=LogLevel.DEBUG, message=f"Query '{q_item[:50]}...' (with metadata_filter: {chroma_metadata_filter if chroma_metadata_filter else 'None'}) yielded {len(current_results)} results.",
                                source="service.enhanced_ai_qa.semantic_search_internal.query_results", user_id=final_user_id_for_log, request_id=request_id,
                                details={**query_log_details, "results_for_this_query": len(current_results)})

                for result in current_results:
                    if not isinstance(result, SemanticSearchResult) or not result.document_id:
                        await log_event(db=db, level=LogLevel.WARNING, message=f"Skipping invalid search result object: {type(result)}",
                                        source="service.enhanced_ai_qa.semantic_search_internal.skip_invalid_result_obj", user_id=final_user_id_for_log, request_id=request_id)
                        continue # Skip if result is not as expected

                    if result.document_id in all_results_map:
                        if result.similarity_score > all_results_map[result.document_id].similarity_score:
                            all_results_map[result.document_id] = result
                    else:
                        all_results_map[result.document_id] = result
            
            combined_results = list(all_results_map.values())
            combined_results.sort(key=lambda r: r.similarity_score, reverse=True)
            
            await log_event(db=db, level=LogLevel.DEBUG, message=f"Semantic search completed. Combined {len(combined_results)} unique results from {len(queries)} queries.",
                            source="service.enhanced_ai_qa.semantic_search_internal.final_results", user_id=final_user_id_for_log, request_id=request_id,
                            details={**log_details, "combined_results_count": len(combined_results)})
            return combined_results
            
        except Exception as e:
            error_trace = traceback.format_exc()
            await log_event(db=db, level=LogLevel.ERROR, message=f"Semantic search failed: {str(e)}",
                            source="service.enhanced_ai_qa.semantic_search_internal.exception", # This is the failing one
                            user_id=final_user_id_for_log, request_id=request_id,
                            details={**log_details, "error": str(e), "error_type": type(e).__name__, "traceback": error_trace})
            return []

    async def _t2q_filter(
        self, 
        db: AsyncIOMotorDatabase,
        document_ids: List[str], 
        extracted_parameters: Dict[str, Any],
        user_id: Optional[str],
        request_id: Optional[str]
    ) -> List[str]:
        """步驟3: T2Q二次過濾，增強安全性"""
        log_details = {
            "initial_doc_ids_count": len(document_ids),
            "extracted_params_keys": list(extracted_parameters.keys())
        }
        await log_event(db=db, level=LogLevel.DEBUG, message="T2Q filter process started.",
                        source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details)
        try:
            if not extracted_parameters or not document_ids:
                await log_event(db=db, level=LogLevel.DEBUG, message="T2Q filter: No parameters or document IDs to filter, returning original list.",
                                source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details)
                return document_ids
            
            allowed_filter_keys = {"document_types", "file_type", "date_range", "key_entities"}
            
            # Convert string IDs to UUIDs for MongoDB query
            uuid_document_ids = []
            for doc_id_str_val in document_ids:
                try:
                    uuid_document_ids.append(uuid.UUID(doc_id_str_val))
                except ValueError:
                     await log_event(db=db, level=LogLevel.WARNING, message=f"T2Q Filter: Invalid document ID format '{doc_id_str_val}', skipping.",
                                    source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
            if not uuid_document_ids:
                return []

            filter_conditions: Dict[str, Any] = {"_id": {"$in": uuid_document_ids}}
            
            for key, value in extracted_parameters.items():
                if key not in allowed_filter_keys:
                    await log_event(db=db, level=LogLevel.DEBUG, message=f"T2Q Filter: Ignoring disallowed filter key '{key}'.",
                                    source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
                    continue

                if isinstance(key, str) and key.startswith("$"): # Basic check for NoSQL injection
                    await log_event(db=db, level=LogLevel.WARNING, message=f"T2Q Filter: Potential malicious filter key '{key}' detected and ignored.",
                                    source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
                    continue

                if key == "document_types" or key == "file_type":
                    if isinstance(value, str) and not value.startswith("$"):
                        filter_conditions["file_type"] = value
                    elif isinstance(value, list) and all(isinstance(v, str) and not v.startswith("$") for v in value) and value:
                        generic_types_lower = ["文檔", "文件", "資料", "文獻", "文本"] # TODO: Internationalize/centralize
                        is_generic_list = all(dt.lower() in generic_types_lower for dt in value)
                        if not is_generic_list: filter_conditions["file_type"] = {"$in": value}
                        else: await log_event(db=db, level=LogLevel.DEBUG, message=f"T2Q Filter: Generic document type list {value} ignored.", source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
                    elif value:
                         await log_event(db=db, level=LogLevel.WARNING, message=f"T2Q Filter: Invalid value '{value}' for key '{key}', ignored.", source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)

                elif key == "date_range":
                    if isinstance(value, dict):
                        date_conditions: Dict[str, datetime] = {}
                        # Simplified date parsing, robust parsing needed for production
                        try:
                            if value.get("start") and isinstance(value["start"], str): date_conditions["$gte"] = datetime.fromisoformat(value["start"].replace('Z', '+00:00'))
                            if value.get("end") and isinstance(value["end"], str): date_conditions["$lt"] = datetime.fromisoformat(value["end"].replace('Z', '+00:00'))
                        except ValueError:
                             await log_event(db=db, level=LogLevel.WARNING, message=f"T2Q Filter: Invalid date format in date_range '{value}'.", source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
                        if date_conditions: filter_conditions["created_at"] = date_conditions
                    elif value:
                        await log_event(db=db, level=LogLevel.WARNING, message=f"T2Q Filter: Invalid value '{value}' for key 'date_range', ignored.", source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id)

            if len(filter_conditions) == 1 and "_id" in filter_conditions:
                 await log_event(db=db, level=LogLevel.DEBUG, message="T2Q Filter: No effective filter parameters applied, returning original document ID list.",
                                 source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details)
                 return document_ids # Return original string IDs

            cursor = db.documents.find(filter_conditions, {"_id": 1})
            filtered_docs = await cursor.to_list(length=None) # Set length to avoid default 101 limit if many docs
            filtered_ids = [str(doc["_id"]) for doc in filtered_docs]
            
            await log_event(db=db, level=LogLevel.DEBUG, message=f"T2Q filter applied. Initial count: {len(document_ids)}, Filtered count: {len(filtered_ids)}.",
                            source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id,
                            details={"initial_count": len(document_ids), "filtered_count": len(filtered_ids), "applied_conditions": {k:v for k,v in filter_conditions.items() if k != "_id"}})
            return filtered_ids
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR, message=f"T2Q filter failed: {str(e)}",
                            source="service.enhanced_ai_qa.t2q_filter_internal", user_id=str(user_id) if user_id else None, request_id=request_id,
                            details={**log_details, "error": str(e), "error_type": type(e).__name__})
            return document_ids
    
    async def _generate_answer_unified(
        self, 
        db: AsyncIOMotorDatabase,
        original_query: str,
        documents_for_context: List[Any], # Assuming Document objects
        query_rewrite_result: QueryRewriteResult,
        user_id: Optional[str], # Added
        request_id: Optional[str], # Added
        model_preference: Optional[str] = None 
    ) -> Tuple[str, int, float, List[LLMContextDocument]]:
        """步驟4: 生成最終答案（使用統一AI服務）"""
        actual_contexts_for_llm: List[LLMContextDocument] = []

        log_details_context = {
            "num_docs_for_context": len(documents_for_context),
            "original_query_length": len(original_query),
            "intent": query_rewrite_result.intent_analysis[:100] if query_rewrite_result.intent_analysis else None # Log snippet
        }
        await log_event(db=db, level=LogLevel.DEBUG, message="Assembling context for AI answer generation.",
                        source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details_context)

        try:
            context_parts = []
            for i, doc in enumerate(documents_for_context[:5], 1):
                doc_content_to_use = ""
                content_source_type = "unknown"
                doc_id_str = str(doc.id) if hasattr(doc, 'id') else f"unknown_doc_{i}"

                raw_extracted_text: Optional[str] = getattr(doc, 'extracted_text', None)
                ai_summary: Optional[str] = None
                ai_dynamic_long_text: Optional[str] = None
                current_summary: Optional[str] = None

                if doc.analysis and doc.analysis.ai_analysis_output and isinstance(doc.analysis.ai_analysis_output, dict):
                    try:
                        analysis_output_data = AIDocumentAnalysisOutputDetail(**doc.analysis.ai_analysis_output)
                        current_summary = analysis_output_data.initial_summary or analysis_output_data.initial_description
                        if analysis_output_data.key_information:
                            key_info_model = analysis_output_data.key_information
                            if not current_summary or len(str(current_summary).strip()) < 50:
                                content_summary_from_key = key_info_model.content_summary
                                if content_summary_from_key and len(str(content_summary_from_key).strip()) > len(str(current_summary).strip() if current_summary else ""):
                                    current_summary = content_summary_from_key
                            if key_info_model.dynamic_fields:
                                for field_value in key_info_model.dynamic_fields.values():
                                    if isinstance(field_value, str) and len(field_value) > 200:
                                        if not ai_dynamic_long_text or len(field_value) > len(ai_dynamic_long_text):
                                            ai_dynamic_long_text = field_value
                        if current_summary and isinstance(current_summary, str) and current_summary.strip():
                            ai_summary = current_summary.strip()
                    except ValidationError as ve:
                        await log_event(db=db, level=LogLevel.WARNING, message=f"Validation error parsing doc analysis for doc_id {doc_id_str}: {ve}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id)
                        if isinstance(doc.analysis.ai_analysis_output, dict):
                            current_summary = doc.analysis.ai_analysis_output.get('initial_summary') or doc.analysis.ai_analysis_output.get('initial_description')
                            if current_summary and isinstance(current_summary, str) and current_summary.strip():
                                ai_summary = current_summary.strip()
                    except Exception as e_parse:
                        await log_event(db=db, level=LogLevel.ERROR, message=f"Unexpected error parsing doc analysis for doc_id {doc_id_str}: {e_parse}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={"error": str(e_parse)})
                
                if ai_dynamic_long_text: doc_content_to_use, content_source_type = ai_dynamic_long_text, "ai_analysis_dynamic_field"
                elif raw_extracted_text and isinstance(raw_extracted_text, str) and len(raw_extracted_text.strip()) > 0: doc_content_to_use, content_source_type = raw_extracted_text, "extracted_text"
                elif ai_summary: doc_content_to_use, content_source_type = ai_summary, "ai_analysis_summary"
                else: doc_content_to_use, content_source_type = f"Document '{getattr(doc, 'filename', 'Unknown')}' ({getattr(doc, 'file_type', 'Unknown Type')}) has no usable content.", "placeholder_no_content"
                
                actual_contexts_for_llm.append(LLMContextDocument(document_id=doc_id_str, content_used=doc_content_to_use[:200], source_type=content_source_type)) # Log snippet
                context_parts.append(f"Document {i} (ID: {doc_id_str}, Source: {content_source_type}):\n{doc_content_to_use}")
            
            full_document_context = "\n\n".join(context_parts)
            query_for_answer_gen = query_rewrite_result.rewritten_queries[0] if query_rewrite_result.rewritten_queries and query_rewrite_result.rewritten_queries[0] else original_query

            log_details_ai_call = {"query_for_answer_gen_length": len(query_for_answer_gen), "num_docs_in_context": len(documents_for_context), "total_context_length": len(full_document_context), "model_preference": model_preference}
            await log_event(db=db, level=LogLevel.DEBUG, message="Calling AI for answer generation.", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details=log_details_ai_call)
            
            ai_response: UnifiedAIResponse = await unified_ai_service_simplified.generate_answer(
                user_question=query_for_answer_gen, intent_analysis=query_rewrite_result.intent_analysis or "",
                document_context=full_document_context, db=db, model_preference=model_preference
            )
            
            tokens_used = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
            answer_text = "Error: AI service did not return a successful response or content."
            confidence = 0.1

            if ai_response.success and ai_response.output_data:
                output_data = ai_response.output_data
                if isinstance(output_data, AIGeneratedAnswerOutput): 
                    answer_text = output_data.answer_text
                elif isinstance(output_data, dict): 
                    answer_text = output_data.get("answer_text", "Error: Could not parse AI answer from dict.")
                elif isinstance(output_data, str): 
                    answer_text = output_data
                else: 
                    # Ensure answer_text is a string representation in case of unexpected type
                    answer_text = f"Error: AI returned unexpected answer format: {type(output_data).__name__}. Raw: {str(output_data)[:100]}"
                
                confidence = min(0.9, 0.3 + (len(documents_for_context) * 0.1) + (0.1 if answer_text and not str(answer_text).lower().startswith("error:") and not str(answer_text).lower().startswith("sorry") else -0.2))
                # Ensure answer_text is string before len() for logging
                current_answer_text_for_log = str(answer_text)
                await log_event(db=db, level=LogLevel.INFO, message="AI answer generation successful.", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={"model_used": ai_response.model_used, "response_length": len(current_answer_text_for_log), "tokens": tokens_used, "confidence": confidence})
            else:
                error_msg = ai_response.error_message or "AI failed to generate answer or content was empty."
                await log_event(db=db, level=LogLevel.ERROR, message=f"AI answer generation failed: {error_msg}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={**log_details_ai_call, "error": error_msg})
                answer_text = f"Sorry, I couldn't generate an answer: {error_msg}" # User-friendly

            return answer_text, tokens_used, confidence, actual_contexts_for_llm
            
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR, message=f"Unexpected error in _generate_answer_unified: {str(e)}", source="service.enhanced_ai_qa.generate_answer_internal", user_id=str(user_id) if user_id else None, request_id=request_id, details={"error_type": type(e).__name__})
            return f"An internal error occurred while generating the answer: {str(e)}", 0, 0.0, actual_contexts_for_llm

# 全局增強AI問答服務實例
enhanced_ai_qa_service = EnhancedAIQAService() 