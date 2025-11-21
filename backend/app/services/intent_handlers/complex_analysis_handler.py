"""
複雜分析處理器

處理複雜的分析問題,使用完整的RAG流程,保持高質量
使用新的模塊化服務,確保所有功能(MongoDB查詢、AI文檔選擇等)都保留
"""
import time
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import (
    AIQARequest,
    AIQAResponse,
    QueryRewriteResult,
    SemanticContextDocument
)
from app.models.question_models import QuestionClassification
from app.services.qa_core.qa_query_rewriter import qa_query_rewriter
from app.services.qa_core.qa_search_coordinator import qa_search_coordinator
from app.services.qa_core.qa_document_processor import qa_document_processor
from app.services.qa_core.qa_answer_service import qa_answer_service
from app.services.qa_workflow.conversation_helper import conversation_helper
from app.crud.crud_documents import get_documents_by_ids

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class ComplexAnalysisHandler:
    """
    複雜分析處理器 - 使用完整RAG流程（統一策略版）
    
    統一策略（2024優化版）:
    - ✅ AI查詢重寫
    - ✅ RRF融合檢索（優先搜索文檔池）
    - ✅ AI智能文檔選擇
    - ✅ MongoDB詳細查詢
    - ✅ 統一對話歷史載入（unified_context_helper）
    - ✅ 文檔池優先級支持
    - ✅ 答案生成
    
    優勢:
    - 與其他策略保持一致的上下文處理
    - 優先使用文檔池提高相關性
    - 完整RAG流程保證高質量
    """
    
    async def handle(
        self,
        request: AIQARequest,
        classification: QuestionClassification,
        context: Optional[dict],
        db: Optional[AsyncIOMotorDatabase] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """處理複雜分析請求（統一策略版）"""
        start_time = time.time()
        total_tokens = 0
        
        logger.info(f"複雜分析(統一策略): {request.question}")
        
        try:
            # 獲取文檔池優先級信息（如果有）
            priority_document_ids = context.get('priority_document_ids', []) if context else []
            should_reuse_cached = context.get('should_reuse_cached', False) if context else False
            
            if priority_document_ids:
                logger.info(f"🎯 文檔池包含 {len(priority_document_ids)} 個優先文檔")
            
            # Step 1: 查詢重寫（传递 @ 文件信息）
            # ✅ 如果用户 @ 了文件，告诉查询重写器
            document_context = None
            if request.document_ids:
                logger.info(f"🎯 查询重写：用户选择了 {len(request.document_ids)} 个文件")
                document_context = {
                    "document_ids": request.document_ids,
                    "document_count": len(request.document_ids)
                }
            
            query_rewrite_result, rewrite_tokens = await qa_query_rewriter.rewrite_query(
                db=db,
                original_query=request.question,
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                document_context=document_context  # ✅ 传递文档上下文
            )
            total_tokens += rewrite_tokens
            
            # Step 2: RRF融合檢索（優先使用文檔池）
            search_strategy = qa_search_coordinator.extract_search_strategy(query_rewrite_result)
            
            # ✅ 优先级：1. request.document_ids (@ 文件) 2. priority_document_ids (如果建议重用)
            document_ids_filter = None
            if request.document_ids:
                document_ids_filter = request.document_ids
                logger.info(f"🎯 使用 @ 文件: {len(request.document_ids)} 個")
            elif priority_document_ids and should_reuse_cached:
                document_ids_filter = priority_document_ids
                logger.info(f"🎯 使用優先文檔池: {len(priority_document_ids)} 個")
            
            semantic_results = await qa_search_coordinator.coordinate_search(
                db=db,
                query=query_rewrite_result.rewritten_queries[0] if query_rewrite_result.rewritten_queries else request.question,
                user_id=str(user_id) if user_id else None,
                search_strategy=search_strategy,
                top_k=getattr(request, 'max_documents_for_selection', 8),
                similarity_threshold=getattr(request, 'similarity_threshold', 0.3),
                document_ids=document_ids_filter  # 優先搜索 @ 文件或文檔池
            )
            
            semantic_contexts = [
                SemanticContextDocument(
                    document_id=r.document_id,
                    summary_or_chunk_text=r.summary_text,
                    similarity_score=r.similarity_score,
                    metadata=r.metadata
                )
                for r in semantic_results
            ]
            
            if not semantic_results:
                return self._create_no_results_response(
                    request, query_rewrite_result, semantic_contexts,
                    total_tokens, time.time() - start_time, classification, db, user_id
                )
            
            # Step 3: 獲取並過濾文檔
            documents = await get_documents_by_ids(db, [r.document_id for r in semantic_results])
            if user_id:
                from uuid import UUID
                user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
                documents = [doc for doc in documents if hasattr(doc, 'owner_id') and doc.owner_id == user_uuid]
            
            if not documents:
                return self._create_no_results_response(
                    request, query_rewrite_result, semantic_contexts,
                    total_tokens, time.time() - start_time, classification, db, user_id
                )
            
            # Step 4: AI選擇文檔
            selected_doc_ids = await qa_document_processor.select_documents_for_detailed_query(
                db=db,
                user_question=request.question,
                semantic_contexts=semantic_contexts,
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                ai_selection_limit=getattr(request, 'ai_selection_limit', 3)
            )
            
            # Step 5: MongoDB詳細查詢
            detailed_data = []
            if selected_doc_ids:
                schema_info = {"description": "MongoDB文件Schema", "fields": {"filename": "文件名", "extracted_text": "文本", "analysis": "AI分析"}}
                
                for doc_id in selected_doc_ids:
                    detail = await qa_document_processor.query_document_details(
                        db=db,
                        document_id=doc_id,
                        user_question=request.question,
                        document_schema_info=schema_info,
                        user_id=str(user_id) if user_id else None,
                        model_preference=request.model_preference
                    )
                    if detail:
                        detailed_data.append(detail)
            
            # Step 6: 載入對話歷史（統一方式）
            from app.services.qa_workflow.unified_context_helper import unified_context_helper
            
            conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
                db=db,
                conversation_id=request.conversation_id,
                user_id=user_id,
                limit=5,
                max_content_length=2000
            )
            
            logger.info(f"載入對話歷史: {len(conversation_history_text) if conversation_history_text else 0} 字符")
            
            # Step 7: 生成答案
            answer, answer_tokens, confidence, contexts = await qa_answer_service.generate_answer(
                db=db,
                original_query=request.question,
                documents_for_context=documents,
                query_rewrite_result=query_rewrite_result,
                detailed_document_data=detailed_data if detailed_data else None,
                ai_generated_query_reasoning=None,
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                model_preference=request.model_preference,
                conversation_history=conversation_history_text
            )
            total_tokens += answer_tokens
            
            processing_time = time.time() - start_time
            
            # 保存對話
            if db is not None:
                # ✅ 合併搜索結果 + 用戶 @ 的文件
                all_doc_ids = set(str(d.id) for d in documents)
                if request.document_ids:
                    all_doc_ids.update(request.document_ids)
                
                await conversation_helper.save_qa_to_conversation(
                    db=db,
                    conversation_id=request.conversation_id,
                    user_id=str(user_id) if user_id else None,
                    question=request.question,
                    answer=answer,
                    tokens_used=total_tokens,
                    source_documents=list(all_doc_ids)
                )
            
            # ✅ 正确计算是否使用了文档池
            used_document_pool = bool(request.document_ids) or (bool(priority_document_ids) and should_reuse_cached)
            doc_pool_size = len(request.document_ids) if request.document_ids else (len(priority_document_ids) if priority_document_ids else 0)
            
            logger.info(
                f"複雜分析完成: {processing_time:.2f}秒, Token: {total_tokens}, "
                f"使用 @ 文件: {bool(request.document_ids)}, "
                f"使用文檔池: {used_document_pool}, "
                f"文檔數: {doc_pool_size}"
            )
            
            return AIQAResponse(
                answer=answer,
                source_documents=[str(d.id) for d in documents],
                confidence_score=confidence,
                tokens_used=total_tokens,
                processing_time=processing_time,
                query_rewrite_result=query_rewrite_result,
                semantic_search_contexts=semantic_contexts,
                session_id=request.session_id,
                llm_context_documents=contexts,
                classification=classification,
                workflow_state={
                    "current_step": "completed",
                    "strategy_used": "complex_analysis_unified",
                    "api_calls": 4 + len(selected_doc_ids) if selected_doc_ids else 4,
                    "used_conversation_history": bool(conversation_history_text),
                    "used_document_pool": used_document_pool,
                    "document_pool_size": doc_pool_size,
                    "used_at_mention_files": bool(request.document_ids)
                },
                detailed_document_data_from_ai_query=detailed_data if detailed_data else None
            )
            
        except Exception as e:
            logger.error(f"複雜分析失敗: {e}", exc_info=True)
            return self._create_error_response(request, str(e), time.time() - start_time, total_tokens, classification)
    
    def _create_no_results_response(self, request, query_rewrite_result, semantic_contexts, tokens_used, processing_time, classification, db, user_id):
        """創建無結果響應"""
        answer = "抱歉,我在您的文檔庫中沒有找到相關內容。"
        return AIQAResponse(
            answer=answer,
            source_documents=[],
            confidence_score=0.0,
            tokens_used=tokens_used,
            processing_time=processing_time,
            query_rewrite_result=query_rewrite_result,
            semantic_search_contexts=semantic_contexts,
            session_id=request.session_id,
            classification=classification
        )
    
    def _create_error_response(self, request, error_msg, processing_time, tokens_used, classification):
        """創建錯誤響應"""
        return AIQAResponse(
            answer=f"處理複雜分析時發生錯誤: {error_msg}",
            source_documents=[],
            confidence_score=0.0,
            tokens_used=tokens_used,
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={},
                intent_analysis="處理失敗"
            ),
            semantic_search_contexts=[],
            session_id=request.session_id,
            classification=classification,
            error_message=error_msg
        )


# 創建全局實例
complex_analysis_handler = ComplexAnalysisHandler()
