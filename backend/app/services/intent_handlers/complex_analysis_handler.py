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
    複雜分析處理器 - 使用完整RAG流程
    
    保留所有原有功能:
    - ✅ AI查詢重寫
    - ✅ RRF融合檢索
    - ✅ AI智能文檔選擇
    - ✅ MongoDB詳細查詢
    - ✅ 答案生成
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
        """處理複雜分析請求"""
        start_time = time.time()
        total_tokens = 0
        
        logger.info(f"複雜分析(模塊化): {request.question}")
        
        try:
            # Step 1: 查詢重寫
            query_rewrite_result, rewrite_tokens = await qa_query_rewriter.rewrite_query(
                db=db,
                original_query=request.question,
                user_id=str(user_id) if user_id else None,
                request_id=request_id
            )
            total_tokens += rewrite_tokens
            
            # Step 2: RRF融合檢索
            search_strategy = qa_search_coordinator.extract_search_strategy(query_rewrite_result)
            semantic_results = await qa_search_coordinator.coordinate_search(
                db=db,
                query=query_rewrite_result.rewritten_queries[0] if query_rewrite_result.rewritten_queries else request.question,
                user_id=str(user_id) if user_id else None,
                search_strategy=search_strategy,
                top_k=getattr(request, 'max_documents_for_selection', 8),
                similarity_threshold=getattr(request, 'similarity_threshold', 0.3)
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
            
            # Step 6: 生成答案
            conv_history = self._format_conversation_history(context) if context else None
            
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
                conversation_history=conv_history
            )
            total_tokens += answer_tokens
            
            processing_time = time.time() - start_time
            
            # 保存對話
            if db is not None:
                await conversation_helper.save_qa_to_conversation(
                    db=db,
                    conversation_id=request.conversation_id,
                    user_id=str(user_id) if user_id else None,
                    question=request.question,
                    answer=answer,
                    tokens_used=total_tokens,
                    source_documents=[str(d.id) for d in documents]
                )
            
            logger.info(f"複雜分析完成: {processing_time:.2f}秒, Token: {total_tokens}")
            
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
                    "strategy_used": "complex_analysis_modular",
                    "api_calls": 4 + len(selected_doc_ids) if selected_doc_ids else 4
                },
                detailed_document_data_from_ai_query=detailed_data if detailed_data else None
            )
            
        except Exception as e:
            logger.error(f"複雜分析失敗: {e}", exc_info=True)
            return self._create_error_response(request, str(e), time.time() - start_time, total_tokens, classification)
    
    def _format_conversation_history(self, context: dict) -> Optional[str]:
        """格式化對話歷史"""
        if not context or not context.get('recent_messages'):
            return None
        
        history_parts = ["=== 對話歷史(最近5條) ==="]
        for msg in context['recent_messages']:
            role = "用戶" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")[:200]
            history_parts.append(f"{role}: {content}")
        history_parts.append("=== 當前問題 ===")
        return "\n".join(history_parts)
    
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
