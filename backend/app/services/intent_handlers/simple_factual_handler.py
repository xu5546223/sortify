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
        
        統一策略（2024優化版）:
        1. **不執行向量搜索**（simple_factual 不需要查找文檔）
        2. **總是載入對話歷史**（最近 5 條消息）
        3. **如果有文檔池，提供文檔池摘要信息**
        4. 使用 AI 通用知識 + 對話歷史 + 文檔池回答
        5. 跳過查詢重寫（節省API調用）
        
        優勢:
        - AI 能看到完整上下文（歷史 + 文檔池）
        - 回答更準確和相關
        - 無需向量搜索，快速響應
        
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
        logger.info("⭐ Simple Factual 不執行向量搜索，使用對話歷史 + 文檔池（如有）+ AI 知識回答")
        
        # 統一策略：總是載入對話歷史和文檔池信息
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        # 1. 載入對話歷史（最近 5 條）
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=request.conversation_id,
            user_id=user_id,
            limit=5,
            max_content_length=2000
        )
        
        # 2. 構建文檔池上下文（如果有）
        doc_pool_context = None
        cached_doc_data = context.get('cached_documents', []) if context else []  # ✅ 修复：使用 cached_documents
        
        if cached_doc_data:
            logger.info(f"文檔池包含 {len(cached_doc_data)} 個文檔，添加到上下文")
            doc_pool_context = "📁 當前文檔池中的文件：\n\n"
            for idx, doc_info in enumerate(cached_doc_data, 1):
                filename = doc_info.get('filename', '未知文件')
                summary = doc_info.get('summary', '無摘要')
                relevance = doc_info.get('relevance_score', 0)
                access_count = doc_info.get('access_count', 0)
                
                # ✅ 使用 AI 期望的引用格式
                doc_pool_context += f"=== 文檔{idx}（引用編號: citation:{idx}）: {filename} ===\n"
                doc_pool_context += f"相關性: {relevance:.0%} | 訪問次數: {access_count}\n"
                if summary and summary != '無摘要':
                    doc_pool_context += f"摘要: {summary}\n"
                doc_pool_context += "\n"
        
        # 3. 構建完整上下文
        context_parts = []
        if conversation_history_text:
            context_parts.append(f"📝 對話歷史：\n{conversation_history_text}")
        if doc_pool_context:
            context_parts.append(doc_pool_context)
        
        # 添加系統提示
        if not cached_doc_data:
            context_parts.append("💡 提示：文檔池為空，請基於通用知識和對話歷史回答。")
        else:
            context_parts.append("💡 提示：可以參考文檔池中的文件信息來回答問題。\n⚠️ 重要：提及文檔時，必須使用 [文檔名](citation:N) 格式創建可點擊引用。")
        
        # 4. 使用 AI 生成答案
        from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
        
        ai_response = await unified_ai_service_simplified.generate_answer(
            user_question=request.question,
            intent_analysis="",
            document_context=context_parts,
            db=db,
            user_id=user_id
        )
        api_calls += 1
        
        # 提取答案文本
        answer = ai_response.output_data.answer_text if ai_response.success and ai_response.output_data else "抱歉，無法生成答案。"
        
        processing_time = time.time() - start_time
        
        # 保存對話記錄（無文檔情況）
        if db is not None:
            # ✅ 如果用戶提供了 @ 文件，也要保存
            source_docs = request.document_ids if request.document_ids else []
            
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=api_calls * 100,
                source_documents=source_docs
            )
        
        logger.info(
            f"簡單事實查詢完成，耗時: {processing_time:.2f}秒，"
            f"使用文檔池: {len(cached_doc_data) > 0}，"
            f"API調用: {api_calls}次"
        )
        
        return AIQAResponse(
            answer=answer,
            source_documents=[],
            confidence_score=0.85 if cached_doc_data else 0.75,  # 有文檔池時置信度更高
            tokens_used=api_calls * 100,
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={},
                intent_analysis=f"簡單事實查詢（統一策略）: {classification.reasoning}"
            ),
            semantic_search_contexts=[],  # 無向量搜索
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "simple_factual_unified",
                "api_calls": api_calls,
                "skipped_vector_search": True,
                "used_conversation_history": bool(conversation_history_text),
                "used_document_pool": len(cached_doc_data) > 0,
                "document_pool_size": len(cached_doc_data)
            }
        )
    
    async def _generate_answer_from_document_pool(
        self,
        request: AIQARequest,
        context: dict,
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        start_time: float,
        api_calls: int
    ) -> AIQAResponse:
        """直接從文檔池信息生成答案（不執行向量搜索）"""
        
        # 獲取文檔池數據
        cached_doc_data = context.get('cached_documents', [])  # ✅ 修复：使用 cached_documents
        
        logger.info(f"從文檔池載入了 {len(cached_doc_data)} 個文檔")
        
        # 載入對話歷史
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=request.conversation_id,
            user_id=user_id,
            limit=5,
            include_summary=False
        )
        
        # 構建文檔池上下文（格式化為易讀的文本）
        doc_pool_context = "當前文檔池中的文件：\n\n"
        for idx, doc_info in enumerate(cached_doc_data, 1):
            filename = doc_info.get('filename', '未知文件')
            summary = doc_info.get('summary', '無摘要')
            relevance = doc_info.get('relevance_score', 0)
            access_count = doc_info.get('access_count', 0)
            
            # ✅ 使用 AI 期望的引用格式
            doc_pool_context += f"=== 文檔{idx}（引用編號: citation:{idx}）: {filename} ===\n"
            doc_pool_context += f"相關性: {relevance:.0%} | 訪問次數: {access_count}\n"
            if summary and summary != '無摘要':
                doc_pool_context += f"摘要: {summary}\n"
            doc_pool_context += "\n"
        
        # 使用 AI 生成答案
        from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
        
        answer = await unified_ai_service_simplified.generate_answer(
            question=request.question,
            document_contexts=[doc_pool_context],
            conversation_history=conversation_history_text,
            user_id=user_id
        )
        
        api_calls += 1
        processing_time = time.time() - start_time
        
        logger.info(f"文檔池總覽回答完成，耗時: {processing_time:.2f}秒")
        
        return AIQAResponse(
            answer=answer,
            source_documents=[],  # 不引用特定文檔
            confidence_score=0.9,  # 高置信度（信息來自文檔池）
            tokens_used=api_calls * 100,
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={},
                intent_analysis=f"文檔池總覽問題: {classification.reasoning}"
            ),
            semantic_search_contexts=[],
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "document_pool_overview",
                "api_calls": api_calls,
                "documents_in_pool": len(cached_doc_data),
                "skipped_vector_search": True
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

