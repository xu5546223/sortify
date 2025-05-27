from typing import List, Optional, Dict, Any, Tuple
import time
import json
import uuid  # Add uuid import
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging_utils import AppLogger
from app.services.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.embedding_service import embedding_service
from app.services.vector_db_service import vector_db_service
from app.models.vector_models import (
    AIQARequest, AIQAResponse, QueryRewriteResult, LLMContextDocument,
    SemanticSearchRequest, SemanticSearchResult, SemanticContextDocument
)
from app.models.ai_models_simplified import TokenUsage
from app.models.ai_models_simplified import (
    AITextAnalysisOutput, AIQueryRewriteOutput,
    AIDocumentAnalysisOutputDetail, AIDocumentKeyInformation,
    AIGeneratedAnswerOutput # Added new model for answer generation
)
from app.crud.crud_documents import get_documents_by_ids
from pydantic import ValidationError
import logging
from datetime import datetime

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class EnhancedAIQAService:
    """增強的AI問答服務 - 使用統一AI管理架構"""
    
    def __init__(self):
        # 使用統一的AI服務，不再需要單獨的AI服務實例
        pass
    
    async def process_qa_request(
        self, 
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: str = None
    ) -> AIQAResponse:
        """
        處理AI問答請求的主要流程 - 支持用戶認證
        
        實現步驟：
        1. 查詢理解與重寫（使用統一AI服務）
        2. 向量搜索
        3. T2Q二次過濾（可選）
        4. 獲取完整文檔內容（檢查用戶權限）
        5. 生成最終答案（使用統一AI服務）
        """
        start_time = time.time()
        total_tokens = 0
        
        try:
            logger.info(f"開始處理AI問答請求: {request.question[:100]}... (用戶: {user_id})")
            
            # 步驟1: 查詢理解與重寫（使用統一AI服務）
            query_rewrite_result, rewrite_tokens = await self._rewrite_query_unified(
                db, request.question
            )
            total_tokens += rewrite_tokens
            
            # 步驟2: 向量搜索
            semantic_results_raw = await self._semantic_search(
                query_rewrite_result.rewritten_queries[0] if query_rewrite_result.rewritten_queries else request.question,
                request.context_limit
            )

            # 將原始 semantic_results 轉換為 SemanticContextDocument 列表
            semantic_contexts_for_response: List[SemanticContextDocument] = []
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
                    db, document_ids, query_rewrite_result.extracted_parameters
                )
                if filtered_document_ids:
                    document_ids = filtered_document_ids
                    logger.info(f"T2Q過濾後剩餘 {len(document_ids)} 個文檔")
            
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
                        # 如果 user_id 不是 UUID 也不是 str，記錄錯誤並可能跳過權限檢查或拋出配置錯誤
                        logger.error(f"無法識別的 user_id 類型: {type(user_id)}，值: {user_id}. 無法執行權限檢查。")
                        full_documents = [] # 或者根據策略決定是否拋出異常
                        # raise TypeError(f"Invalid user_id type: {type(user_id)}") 

                    accessible_documents = []
                    if full_documents: # 確保 full_documents 不是 None 或空列表
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
                db, request.question, full_documents, query_rewrite_result
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
            logger.error(f"處理AI問答請求失敗: {e}", exc_info=True)
            return AIQAResponse(
                answer=f"處理您的問題時出現錯誤: {str(e)}",
                source_documents=[],
                confidence_score=0.0,
                tokens_used=total_tokens,
                processing_time=time.time() - start_time,
                semantic_search_contexts=[], # 出錯時傳遞空列表
                session_id=request.session_id
            )
    
    async def _rewrite_query_unified(
        self, 
        db: AsyncIOMotorDatabase,
        original_query: str
    ) -> Tuple[QueryRewriteResult, int]:
        """步驟1: 查詢理解與重寫（使用統一AI服務）"""
        try:
            logger.info(f"使用統一AI服務重寫查詢: {original_query[:50]}...")
            
            # 使用統一AI服務進行查詢重寫
            ai_response = await unified_ai_service_simplified.rewrite_query(
                original_query=original_query,
                db=db
            )
            
            if not ai_response.success:
                logger.warning(f"查詢重寫失敗: {ai_response.error_message}")
                # 返回原查詢作為fallback
                fallback_result = QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=[original_query],
                    extracted_parameters={},
                    intent_analysis=f"查詢重寫失敗: {ai_response.error_message}"
                )
                return fallback_result, ai_response.token_usage.total_tokens
            
            # 解析AI回應（從統一AI服務返回的結構化輸出中提取）
            try:
                # ai_response.content 現在可能是 dict (for QUERY_REWRITE) 或 AITextAnalysisOutput
                content_data = ai_response.content
                
                rewritten_queries_list = [original_query] # 默認使用原查詢
                extracted_params_dict = {}
                intent_analysis_str = "意圖分析未提供" # 默認值

                if isinstance(content_data, dict):
                    logger.info("Attempting to parse content_data as dict using AIQueryRewriteOutput model.")
                    try:
                        parsed_output = AIQueryRewriteOutput(**content_data)
                        rewritten_queries_list = parsed_output.rewritten_queries if parsed_output.rewritten_queries else [original_query]
                        extracted_params_dict = parsed_output.extracted_parameters if parsed_output.extracted_parameters else {}
                        intent_analysis_str = parsed_output.intent_analysis
                        logger.info(f"Successfully parsed AI query rewrite output using AIQueryRewriteOutput model. Intent: {intent_analysis_str[:50]}")
                        
                        query_rewrite_result = QueryRewriteResult(
                            original_query=original_query,
                            rewritten_queries=rewritten_queries_list,
                            extracted_parameters=extracted_params_dict,
                            intent_analysis=intent_analysis_str
                        )
                    except ValidationError as ve:
                        logger.warning(f"Validation error when parsing AI query rewrite output dictionary: {ve}. Content: {content_data}")
                        # Fallback logic
                        query_rewrite_result = QueryRewriteResult(
                            original_query=original_query,
                            rewritten_queries=[original_query],
                            extracted_parameters={},
                            intent_analysis=f"Failed to parse AI rewrite response: {str(ve)}"
                        )
                        # Skip further processing in this try block for content_data, as query_rewrite_result is set
                        return query_rewrite_result, ai_response.token_usage.total_tokens

                elif isinstance(content_data, AITextAnalysisOutput): 
                    logger.info("Processing content_data as AITextAnalysisOutput for Query Rewrite (fallback path).")
                    # This path is now more of a fallback if the AI service returns the older model type.
                    ai_output: AITextAnalysisOutput = content_data
                    key_info = ai_output.key_information if hasattr(ai_output, 'key_information') and ai_output.key_information else None
                    
                    if key_info: # key_info 在 AITextAnalysisOutput 中本身就是 FlexibleKeyInformation 或 dict
                        # FlexibleKeyInformation 的字段可以直接訪問，或者如果是 dict，則使用 .get()
                        if hasattr(key_info, 'rewritten_queries') and isinstance(key_info.rewritten_queries, list) and key_info.rewritten_queries:
                            rewritten_queries_list = key_info.rewritten_queries
                        elif isinstance(key_info, dict) and key_info.get('rewritten_queries') and isinstance(key_info.get('rewritten_queries'), list):
                            rewritten_queries_list = key_info.get('rewritten_queries')
                        
                        if hasattr(key_info, 'extracted_parameters') and isinstance(key_info.extracted_parameters, dict):
                            extracted_params_dict = key_info.extracted_parameters
                        elif isinstance(key_info, dict) and key_info.get('extracted_parameters') and isinstance(key_info.get('extracted_parameters'), dict):
                            extracted_params_dict = key_info.get('extracted_parameters')

                        if hasattr(key_info, 'intent_analysis') and isinstance(key_info.intent_analysis, str) and key_info.intent_analysis:
                            intent_analysis_str = key_info.intent_analysis
                        elif isinstance(key_info, dict) and key_info.get('intent_analysis') and isinstance(key_info.get('intent_analysis'), str):
                            intent_analysis_str = key_info.get('intent_analysis')
                        elif ai_output.initial_summary: # 後備選項1 (來自 AITextAnalysisOutput)
                            intent_analysis_str = ai_output.initial_summary
                        elif ai_output.content_type: # 後備選項2 (來自 AITextAnalysisOutput)
                            intent_analysis_str = ai_output.content_type
                    else: # 如果 key_info 本身就是 None
                        if ai_output.initial_summary:
                            intent_analysis_str = ai_output.initial_summary
                        elif ai_output.content_type:
                            intent_analysis_str = ai_output.content_type
                        else:
                            intent_analysis_str = "關鍵資訊提取失敗或未提供意圖分析 (AITextAnalysisOutput path)"
                else:
                    logger.warning(f"content_data is of unexpected type: {type(content_data)}. Using fallback values for rewrite result.")
                    intent_analysis_str = f"查詢重寫結果內容類型未知: {type(content_data)}"
                
                # This assignment will be skipped if the dict parsing resulted in ValidationError and returned early
                query_rewrite_result = QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=rewritten_queries_list if rewritten_queries_list else [original_query],
                    extracted_parameters=extracted_params_dict if extracted_params_dict else {},
                    intent_analysis=intent_analysis_str
                )
                logger.info(f"Query rewrite processing complete. Rewritten queries: {len(query_rewrite_result.rewritten_queries)}, Intent: {query_rewrite_result.intent_analysis[:50]}")

            except AttributeError as ae: # This might still occur if AITextAnalysisOutput path has issues
                logger.warning(f"Attribute error during query rewrite content processing (likely AITextAnalysisOutput path): {ae}", exc_info=True)
                query_rewrite_result = QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=[original_query],
                    extracted_parameters={},
                    intent_analysis=f"查詢重寫結果解析時屬性錯誤: {str(ae)}"
                )
            except Exception as e: # Catch other unexpected errors during content processing
                logger.warning(f"Unexpected error during query rewrite content processing: {e}", exc_info=True)
                query_rewrite_result = QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=[original_query],
                    extracted_parameters={},
                    intent_analysis=f"查詢重寫結果解析時發生未知錯誤: {str(e)}"
                )
            
            return query_rewrite_result, ai_response.token_usage.total_tokens
            
        except Exception as e: # Outer exception for issues with unified_ai_service_simplified.rewrite_query call itself
            logger.error(f"Unified AI service query rewrite call failed: {e}", exc_info=True)
            # 返回原查詢作為fallback
            fallback_result = QueryRewriteResult(
                original_query=original_query,
                rewritten_queries=[original_query],
                extracted_parameters={},
                intent_analysis=f"查詢重寫出錯: {str(e)}"
            )
            return fallback_result, 0
    
    async def _semantic_search(
        self, 
        query: str, 
        top_k: int = 10
    ) -> List[SemanticSearchResult]:
        """步驟2: 向量搜索（保持不變）"""
        try:
            # 將查詢轉換為向量
            query_vector = embedding_service.encode_text(query)
            
            # 在向量資料庫中搜索
            results = vector_db_service.search_similar_vectors(
                query_vector=query_vector,
                top_k=top_k,
                similarity_threshold=0.3  # 降低閾值以獲得更多候選
            )
            
            logger.info(f"語義搜索找到 {len(results)} 個相關文檔")
            return results
            
        except Exception as e:
            logger.error(f"語義搜索失敗: {e}")
            return []
    
    async def _t2q_filter(
        self, 
        db: AsyncIOMotorDatabase,
        document_ids: List[str], 
        extracted_parameters: Dict[str, Any]
    ) -> List[str]:
        """步驟3: T2Q二次過濾（保持不變）"""
        try:
            if not extracted_parameters:
                return document_ids
            
            # 構建MongoDB查詢條件
            filter_conditions = {"_id": {"$in": document_ids}}
            
            # 根據提取的參數添加過濾條件
            doc_types_param = extracted_parameters.get("document_types") or extracted_parameters.get("file_type")
            
            # 檢查是否為非常通用的類型列表，如果是，則可能跳過 file_type 過濾
            is_generic_doc_type_list = False
            if isinstance(doc_types_param, list) and doc_types_param:
                generic_types = ["文檔", "文件", "資料", "文獻", "文本"]
                # 如果列表中的所有類型都是通用類型
                if all(dt.lower() in [gt.lower() for gt in generic_types] for dt in doc_types_param):
                    is_generic_doc_type_list = True
                    logger.info(f"T2Q: Detected generic document type list: {doc_types_param}. Will not filter by file_type strictly.")

            if doc_types_param and not is_generic_doc_type_list:
                if isinstance(doc_types_param, list) and doc_types_param:
                    filter_conditions["file_type"] = {"$in": doc_types_param}
                    logger.info(f"T2Q: Applying file_type filter with $in: {doc_types_param}")
                elif isinstance(doc_types_param, str) and doc_types_param:
                    filter_conditions["file_type"] = doc_types_param
                    logger.info(f"T2Q: Applying file_type filter with exact match: {doc_types_param}")
            elif not doc_types_param:
                 logger.info("T2Q: No document_types/file_type parameter provided for filtering.")

            if "date_range" in extracted_parameters:
                date_range = extracted_parameters["date_range"]
                if "start" in date_range:
                    filter_conditions["created_at"] = {"$gte": date_range["start"]}
                if "end" in date_range:
                    if "created_at" not in filter_conditions:
                        filter_conditions["created_at"] = {}
                    filter_conditions["created_at"]["$lt"] = date_range["end"]
            
            # 執行過濾查詢
            cursor = db.documents.find(filter_conditions, {"_id": 1})
            filtered_docs = await cursor.to_list(length=None)
            
            filtered_ids = [str(doc["_id"]) for doc in filtered_docs]
            
            logger.info(f"T2Q過濾：{len(document_ids)} -> {len(filtered_ids)}")
            return filtered_ids
            
        except Exception as e:
            logger.error(f"T2Q過濾失敗: {e}")
            return document_ids  # 過濾失敗時返回原列表
    
    async def _generate_answer_unified(
        self, 
        db: AsyncIOMotorDatabase,
        original_query: str,
        documents_for_context: List[Any],
        query_rewrite_result: QueryRewriteResult
    ) -> Tuple[str, int, float, List[LLMContextDocument]]:
        """步驟4: 生成最終答案（使用統一AI服務）"""
        qa_start_time = time.time()
        actual_contexts_for_llm: List[LLMContextDocument] = []
        try:
            context_parts = []
            for i, doc in enumerate(documents_for_context[:5], 1):  # 限制最多5個文檔
                doc_content_to_use = ""
                content_source_type = "unknown"
                doc_id_str = str(doc.id) if hasattr(doc, 'id') else f"unknown_doc_{i}"

                # 候選內容來源
                raw_extracted_text: Optional[str] = getattr(doc, 'extracted_text', None)
                ai_summary: Optional[str] = None
                ai_dynamic_long_text: Optional[str] = None
                current_summary: Optional[str] = None # Initialize current_summary for broader scope

                if doc.analysis and doc.analysis.ai_analysis_output and isinstance(doc.analysis.ai_analysis_output, dict):
                    try:
                        # Attempt to parse the dictionary into AIDocumentAnalysisOutputDetail
                        analysis_output_data = AIDocumentAnalysisOutputDetail(**doc.analysis.ai_analysis_output)
                        logger.debug(f"Successfully parsed doc.analysis.ai_analysis_output for doc_id: {doc_id_str} using Pydantic models.")

                        # Try to get initial summary or description
                        current_summary = analysis_output_data.initial_summary or analysis_output_data.initial_description

                        if analysis_output_data.key_information:
                            key_info_model = analysis_output_data.key_information # This is now an AIDocumentKeyInformation object

                            # If initial summary is short, try content_summary from key_info
                            if not current_summary or len(str(current_summary).strip()) < 50:
                                content_summary_from_key = key_info_model.content_summary
                                if content_summary_from_key and len(str(content_summary_from_key).strip()) > len(str(current_summary).strip() if current_summary else ""):
                                    current_summary = content_summary_from_key
                            
                            # Try to get a long text from dynamic_fields in key_info
                            if key_info_model.dynamic_fields:
                                for field_name, field_value in key_info_model.dynamic_fields.items():
                                    if isinstance(field_value, str) and len(field_value) > 200:
                                        if not ai_dynamic_long_text or len(field_value) > len(ai_dynamic_long_text):
                                            ai_dynamic_long_text = field_value
                        
                        if current_summary and isinstance(current_summary, str) and current_summary.strip():
                            ai_summary = current_summary.strip()

                    except ValidationError as ve:
                        logger.warning(f"Validation error parsing doc.analysis.ai_analysis_output for doc_id {doc_id_str}: {ve}. Content: {doc.analysis.ai_analysis_output}")
                        # Fallback: Try to extract some basic info directly if main parsing fails,
                        # otherwise ai_summary and ai_dynamic_long_text remain None.
                        if isinstance(doc.analysis.ai_analysis_output, dict): # Ensure it's still a dict
                            current_summary = doc.analysis.ai_analysis_output.get('initial_summary') or doc.analysis.ai_analysis_output.get('initial_description')
                            if current_summary and isinstance(current_summary, str) and current_summary.strip():
                                ai_summary = current_summary.strip()
                    except Exception as e: # Catch any other unexpected errors during this parsing
                        logger.error(f"Unexpected error parsing doc.analysis.ai_analysis_output for doc_id {doc_id_str}: {e}. Content: {doc.analysis.ai_analysis_output}", exc_info=True)
                        # ai_summary and ai_dynamic_long_text will remain None

                # The rest of the logic for determining doc_content_to_use remains similar,
                # using the potentially populated ai_dynamic_long_text, raw_extracted_text, ai_summary
                # Priority: AI dynamic long text > raw extracted text > AI summary
                if ai_dynamic_long_text:
                    doc_content_to_use = ai_dynamic_long_text
                    content_source_type = "ai_analysis_dynamic_field"
                elif raw_extracted_text and isinstance(raw_extracted_text, str) and len(raw_extracted_text.strip()) > 0:
                    doc_content_to_use = raw_extracted_text
                    content_source_type = "extracted_text"
                elif ai_summary: # 僅在前兩者都不可用或不佳時使用AI摘要
                    doc_content_to_use = ai_summary
                    content_source_type = "ai_analysis_summary"
                else:
                    doc_content_to_use = f"文檔 '{getattr(doc, 'filename', '未知')}' ({getattr(doc, 'file_type', '未知類型')}) 無法確定有效的上下文內容。"
                    content_source_type = "placeholder_no_content_determined"
                
                actual_contexts_for_llm.append(LLMContextDocument(
                    document_id=doc_id_str,
                    content_used=doc_content_to_use,
                    source_type=content_source_type
                ))
                
                doc_context_for_prompt = f'''文檔 {i} (ID: {doc_id_str}):
文件名: {getattr(doc, 'filename', '未知')}
文件類型: {getattr(doc, 'file_type', '未知類型')}
內容 (來源: {content_source_type}):
{doc_content_to_use}
'''
                context_parts.append(doc_context_for_prompt)
            
            full_document_context = "\n\n".join(context_parts) # 使用雙換行符分隔不同的文檔上下文
            
            current_intent_analysis = query_rewrite_result.intent_analysis or ""
            
            # Determine the query to use for answer generation
            # Prefer the first rewritten query if available and sensible, else original query
            query_for_answer_gen = original_query
            if query_rewrite_result.rewritten_queries and query_rewrite_result.rewritten_queries[0]:
                query_for_answer_gen = query_rewrite_result.rewritten_queries[0]

            logger.info(f"使用統一AI服務生成答案。查詢: '{query_for_answer_gen[:100]}...', 文檔數量: {len(documents_for_context)}")
            
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=query_for_answer_gen,
                intent_analysis=current_intent_analysis,
                document_context=full_document_context,
                db=db
            )
            
            tokens_used = 0
            if ai_response.token_usage:
                tokens_used = ai_response.token_usage.total_tokens

            if not ai_response.success or not ai_response.content:
                error_msg = ai_response.error_message or "AI未能生成有效內容"
                logger.error(f"統一AI服務生成答案失敗或內容為空: {error_msg}")
                return f"抱歉，無法生成答案: {error_msg}", tokens_used, 0.1, actual_contexts_for_llm

            answer_text: str
            answer_text: str
    
            if isinstance(ai_response.content, dict):
                try:
                    parsed_answer = AIGeneratedAnswerOutput(**ai_response.content)
                    answer_text = parsed_answer.answer_text
                    logger.info(f"Successfully parsed AI-generated answer using AIGeneratedAnswerOutput model: {answer_text[:100]}...")
                except ValidationError as ve:
                    logger.warning(f"Validation error parsing AI-generated answer dictionary: {ve}. Content: {ai_response.content}")
                    answer_text = f"AI返回的答案格式無效: {str(ve)}" # Or a more generic error
                except Exception as e: # Catch any other unexpected errors during this parsing
                    logger.error(f"Unexpected error parsing AI-generated answer dictionary: {e}. Content: {ai_response.content}", exc_info=True)
                    answer_text = f"解析AI答案時發生意外錯誤。"

            elif isinstance(ai_response.content, str):
                answer_text = ai_response.content
                logger.info(f"Successfully received answer as string from unified_ai_service: {answer_text[:100]}...")
            
            elif isinstance(ai_response.content, AITextAnalysisOutput): # Retain this if still a possible path
                logger.warning(f"Received AITextAnalysisOutput for an ANSWER_GENERATION task. Attempting to extract answer as fallback.")
                # Fallback logic from previous version, simplified
                extracted_answer = None
                if ai_response.content.key_information and isinstance(ai_response.content.key_information, dict):
                    extracted_answer = (
                        ai_response.content.key_information.get("answer") or
                        ai_response.content.key_information.get("answer_text") or
                        ai_response.content.key_information.get("generated_answer")
                    )
                
                if not extracted_answer and isinstance(ai_response.content.initial_summary, str) and ai_response.content.initial_summary.strip():
                    extracted_answer = ai_response.content.initial_summary
                
                if extracted_answer:
                    answer_text = str(extracted_answer)
                    logger.info(f"Extracted answer from AITextAnalysisOutput fallback: {answer_text[:100]}...")
                else:
                    answer_text = "AI服務返回了結構化數據，但無法從中提取明確的答案文本 (AITextAnalysisOutput path)。"
                    logger.warning(f"Could not extract a clear answer from AITextAnalysisOutput fallback. Content: {ai_response.content}")
                    
            else: # ai_response.content is not dict, str, or AITextAnalysisOutput
                answer_text = f"AI返回了非預期的答案格式: {type(ai_response.content)}"
                logger.warning(answer_text)

            # Basic confidence score calculation (can be refined)
            confidence = min(0.9, 0.3 + (len(documents_for_context) * 0.1) + (0.1 if ai_response.success and answer_text and not answer_text.startswith("AI返回") and not answer_text.startswith("抱歉") else -0.2))
            
            logger.info(f"答案生成成功。模型: {ai_response.model_used}, Token使用: {tokens_used}")
            return answer_text, tokens_used, confidence, actual_contexts_for_llm
            
        except Exception as e:
            logger.error(f"在 _generate_answer_unified 中生成答案時發生意外錯誤: {e}", exc_info=True)
            # 即使出錯，也嘗試返回已收集的上下文信息
            return f"生成答案時發生內部嚴重錯誤: {str(e)}", 0, 0.0, actual_contexts_for_llm

# 全局增強AI問答服務實例
enhanced_ai_qa_service = EnhancedAIQAService() 