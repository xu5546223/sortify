"""
簡單事實查詢處理器

處理簡單的事實查詢,執行輕量級搜索,快速回答
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
from app.services.vector.embedding_service import embedding_service
from app.services.vector.vector_db_service import vector_db_service
from app.services.ai.unified_ai_service_simplified import (
    unified_ai_service_simplified,
    AIRequest,
    TaskType
)
from app.services.qa_workflow.conversation_helper import conversation_helper
from app.crud.crud_documents import get_documents_by_ids

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class SimpleFactualHandler:
    """簡單事實查詢處理器 - 輕量級搜索,2-3次API調用"""
    
    async def handle(
        self,
        request: AIQARequest,
        classification: QuestionClassification,
        context: Optional[dict] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        處理簡單事實查詢
        
        策略:
        1. 跳過查詢重寫(節省1次API調用)
        2. 執行單次摘要向量搜索
        3. 使用摘要直接生成答案
        4. 不執行詳細文檔查詢
        
        Args:
            request: AI QA 請求
            classification: 問題分類結果
            context: 對話上下文（未使用）
            db: 數據庫連接
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 快速回答
        """
        start_time = time.time()
        api_calls = 0
        
        logger.info(f"處理簡單事實查詢: {request.question}")
        
        # Step 1: 生成查詢向量
        query_embedding = embedding_service.encode_text(request.question)
        if not query_embedding or not any(query_embedding):
            logger.error("無法生成查詢的嵌入向量")
            return self._create_error_response(
                request, "無法處理您的問題,請稍後再試",
                time.time() - start_time
            )
        
        # Step 2: 執行摘要向量搜索(只搜索摘要,不搜索文本片段)
        try:
            summary_metadata_filter = {"type": "summary"}
            if request.document_ids:
                summary_metadata_filter["document_id"] = {"$in": request.document_ids}
            
            search_results = vector_db_service.search_similar_vectors(
                query_vector=query_embedding,
                top_k=min(5, request.context_limit or 5),  # 限制搜索數量
                owner_id_filter=str(user_id) if user_id else None,
                metadata_filter=summary_metadata_filter,
                similarity_threshold=0.4  # 稍微寬鬆的閾值
            )
            
            logger.info(f"摘要搜索找到 {len(search_results)} 個相關文檔")
            
        except Exception as e:
            logger.error(f"向量搜索失敗: {e}", exc_info=True)
            search_results = []
        
        # Step 3: 準備語義搜索上下文
        semantic_contexts = []
        for result in search_results:
            semantic_contexts.append(
                SemanticContextDocument(
                    document_id=result.document_id,
                    summary_or_chunk_text=result.summary_text,
                    similarity_score=result.similarity_score,
                    metadata=result.metadata
                )
            )
        
        # Step 4: 如果沒有找到相關文檔,直接用AI回答
        if not search_results:
            logger.info("未找到相關文檔,使用AI通用知識回答")
            answer = await self._generate_answer_without_documents(
                request.question,
                classification,
                db,
                user_id,
                request.conversation_id  # 傳遞 conversation_id
            )
            api_calls += 1
            
            processing_time = time.time() - start_time
            
            # 保存對話記錄(無文檔情況)
            if db is not None:
                await conversation_helper.save_qa_to_conversation(
                    db=db,
                    conversation_id=request.conversation_id,
                    user_id=str(user_id) if user_id else None,
                    question=request.question,
                    answer=answer,
                    tokens_used=api_calls * 100,
                    source_documents=[]
                )
            
            return AIQAResponse(
                answer=answer,
                source_documents=[],
                confidence_score=0.6,
                tokens_used=api_calls * 100,  # 估算
                processing_time=processing_time,
                query_rewrite_result=QueryRewriteResult(
                    original_query=request.question,
                    rewritten_queries=[request.question],
                    extracted_parameters={},
                    intent_analysis=f"簡單事實查詢(無文檔): {classification.reasoning}"
                ),
                semantic_search_contexts=semantic_contexts,
                session_id=request.session_id,
                classification=classification,
                workflow_state={
                    "current_step": "completed",
                    "strategy_used": "simple_factual_no_docs",
                    "api_calls": api_calls
                }
            )
        
        # Step 5: 獲取文檔詳細信息
        document_ids = [result.document_id for result in search_results[:3]]  # 只取前3個
        try:
            documents = await get_documents_by_ids(db, document_ids)
            
            # 過濾用戶有權限的文檔
            if user_id:
                from uuid import UUID
                user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
                documents = [
                    doc for doc in documents 
                    if hasattr(doc, 'owner_id') and doc.owner_id == user_uuid
                ]
            
        except Exception as e:
            logger.error(f"獲取文檔失敗: {e}", exc_info=True)
            documents = []
        
        # Step 6: 使用摘要生成答案(不做詳細查詢)
        if documents:
            answer = await self._generate_answer_with_summaries(
                request.question,
                documents,
                search_results,
                classification,
                db,
                user_id,
                request.conversation_id  # 傳遞 conversation_id
            )
            api_calls += 1
        else:
            answer = await self._generate_answer_without_documents(
                request.question,
                classification,
                db,
                user_id
            )
            api_calls += 1
        
        processing_time = time.time() - start_time
        
        # 保存對話記錄
        if db is not None:
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=api_calls * 100,
                source_documents=[str(doc.id) for doc in documents] if documents else []
            )
        
        # 記錄日誌
        if db is not None:
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="簡單事實查詢處理完成",
                source="handler.simple_factual",
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                details={
                    "question": request.question[:100],
                    "documents_found": len(documents),
                    "api_calls": api_calls,
                    "processing_time": processing_time
                }
            )
        
        logger.info(
            f"簡單事實查詢完成,耗時: {processing_time:.2f}秒, "
            f"API調用: {api_calls}次"
        )
        
        return AIQAResponse(
            answer=answer,
            source_documents=[str(doc.id) for doc in documents],
            confidence_score=0.8,
            tokens_used=api_calls * 100,  # 估算
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={},
                intent_analysis=f"簡單事實查詢: {classification.reasoning}"
            ),
            semantic_search_contexts=semantic_contexts,
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "simple_factual_with_summaries",
                "api_calls": api_calls,
                "documents_used": len(documents)
            }
        )
    
    async def _generate_answer_with_summaries(
        self,
        question: str,
        documents: list,
        search_results: list,
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        conversation_id: Optional[str] = None
    ) -> str:
        """使用文檔摘要生成答案(帶對話歷史)"""
        
        # 使用統一工具載入對話歷史（重要：保留完整信息）
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            limit=5,  # 增加到5條，確保能看到之前的完整回答
            max_content_length=2000  # 保留完整內容（答案可能在歷史中）
        )
        
        # 構建上下文(只使用摘要,不查詢詳細內容)
        context_parts = []
        if conversation_history_text:
            context_parts.append(conversation_history_text)
        
        for i, doc in enumerate(documents[:3], 1):  # 最多3個文檔
            # 嘗試獲取AI分析的摘要
            summary = None
            if hasattr(doc, 'analysis') and doc.analysis:
                if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                    key_info = doc.analysis.ai_analysis_output.get('key_information', {})
                    summary = key_info.get('content_summary')
            
            # 如果沒有摘要,使用搜索結果中的文本
            if not summary:
                matching_result = next(
                    (r for r in search_results if r.document_id == str(doc.id)),
                    None
                )
                if matching_result:
                    summary = matching_result.summary_text
            
            if summary:
                context_parts.append(
                    f"文檔{i} ({getattr(doc, 'filename', 'Unknown')}):\n{summary}"
                )
        
        context_str = "\n\n".join(context_parts) if context_parts else "無相關文檔內容"
        
        # 調用AI生成答案(使用用戶偏好的模型)
        try:
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=question,
                intent_analysis=classification.reasoning,
                document_context=[context_str],
                db=db,
                user_id=user_id,
                model_preference=None  # 使用系統配置的用戶偏好模型
            )
            
            if ai_response.success and ai_response.output_data:
                return ai_response.output_data.answer_text
            else:
                logger.error(f"AI生成答案失敗: {ai_response.error_message}")
                return "抱歉,我無法根據找到的文檔生成答案。"
                
        except Exception as e:
            logger.error(f"生成答案時發生錯誤: {e}", exc_info=True)
            return "抱歉,生成答案時發生錯誤。"
    
    async def _generate_answer_without_documents(
        self,
        question: str,
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        conversation_id: Optional[str] = None
    ) -> str:
        """不使用文檔,直接用AI回答(基於通用知識,帶對話歷史)"""
        
        # 使用統一工具載入對話歷史（重要：保留完整信息）
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            limit=5,  # 增加到5條
            max_content_length=2000  # 保留完整內容（答案可能在歷史中）
        )
        
        context_parts = []
        if conversation_history_text:
            context_parts.append(conversation_history_text)
        context_parts.append("注意: 用戶的文檔庫中沒有找到相關內容,請基於你的通用知識簡潔地回答這個問題。如果對話歷史中已經包含了答案,請直接從歷史中提取回答。")
        
        try:
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=question,
                intent_analysis=classification.reasoning,
                document_context=context_parts,
                db=db,
                user_id=user_id,
                model_preference=None  # 使用系統配置的用戶偏好模型
            )
            
            if ai_response.success and ai_response.output_data:
                answer = ai_response.output_data.answer_text
                # 添加提示說明這是基於通用知識的回答
                return f"{answer}\n\n💡 提示: 這個回答基於AI的通用知識,未在您的文檔中找到相關資料。"
            else:
                return "抱歉,我無法回答這個問題。您可以嘗試上傳相關文檔或換個方式提問。"
                
        except Exception as e:
            logger.error(f"生成答案時發生錯誤: {e}", exc_info=True)
            return "抱歉,生成答案時發生錯誤。"
    
    def _create_error_response(
        self,
        request: AIQARequest,
        error_message: str,
        processing_time: float
    ) -> AIQAResponse:
        """創建錯誤響應"""
        return AIQAResponse(
            answer=error_message,
            source_documents=[],
            confidence_score=0.0,
            tokens_used=0,
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={},
                intent_analysis="處理失敗"
            ),
            semantic_search_contexts=[],
            session_id=request.session_id,
            error_message=error_message
        )


# 創建全局實例
simple_factual_handler = SimpleFactualHandler()

