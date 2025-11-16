"""
工作流協調器

處理工作流在各個階段的靈活轉換,確保對話流暢
支持: 澄清→搜索/直接回答、搜索→澄清、批准機制等
"""
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import AIQARequest, AIQAResponse
from app.models.question_models import QuestionClassification, QuestionIntent

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class WorkflowCoordinator:
    """工作流協調器 - 管理各階段間的轉換"""
    
    async def handle_clarification_response(
        self,
        original_request: AIQARequest,
        clarification_response: str,
        db: AsyncIOMotorDatabase,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        處理用戶的澄清回答,重新分類並路由
        
        Args:
            original_request: 原始請求
            clarification_response: 用戶的澄清回答
            db: 數據庫連接
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 處理結果
        """
        logger.info(f"處理澄清回答: {clarification_response[:100]}")
        
        # 創建新請求,包含澄清回答
        new_request = AIQARequest(
            question=clarification_response,
            conversation_id=original_request.conversation_id,
            session_id=original_request.session_id,
            model_preference=original_request.model_preference,
            context_limit=original_request.context_limit,
            # 繼承其他設置
            **{k: v for k, v in original_request.model_dump().items() 
               if k not in ['question']}
        )
        
        # 重新進入智能路由流程(這次會帶上澄清的對話歷史)
        from app.services.qa_orchestrator import qa_orchestrator
        
        logger.info("澄清後重新路由,AI將看到完整對話上下文")
        response = await qa_orchestrator.process_qa_request_intelligent(
            db=db,
            request=new_request,
            user_id=user_id,
            request_id=request_id
        )
        
        # 在 workflow_state 中標記這是澄清後的處理
        if response.workflow_state:
            response.workflow_state["previous_step"] = "clarification"
            response.workflow_state["clarification_resolved"] = True
        
        return response
    
    async def handle_search_no_results(
        self,
        original_request: AIQARequest,
        classification: QuestionClassification,
        db: AsyncIOMotorDatabase,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        處理搜索無結果的情況,提供選項:
        1. 調整搜索條件(生成澄清問題)
        2. 使用通用知識回答
        
        Args:
            original_request: 原始請求
            classification: 分類結果
            db: 數據庫連接
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 處理結果
        """
        logger.info(f"搜索無結果,生成建議")
        
        # 生成智能建議(帶對話歷史)
        from app.services.qa_workflow.question_classifier_service import question_classifier_service
        
        clarification_data = await question_classifier_service.generate_clarification_question(
            original_question=original_request.question,
            ambiguity_reason="未在文檔庫中找到相關內容",
            db=db,
            user_id=user_id,
            conversation_id=original_request.conversation_id  # 傳遞對話ID
        )
        
        clarification_question = clarification_data.get(
            "clarification_question",
            "未找到相關文檔。您可以:\n1. 調整搜索關鍵詞\n2. 上傳相關文檔\n3. 讓我基於通用知識回答"
        )
        
        suggested_responses = clarification_data.get(
            "suggested_responses",
            ["使用不同的關鍵詞重新提問", "上傳相關文檔", "用通用知識回答"]
        )
        
        # 構建回答
        answer = f"🔍 {clarification_question}\n\n"
        answer += "💡 建議的選項:\n"
        for i, option in enumerate(suggested_responses, 1):
            answer += f"{i}. {option}\n"
        
        # 保存對話
        from app.services.qa_workflow.conversation_helper import conversation_helper
        await conversation_helper.save_qa_to_conversation(
            db=db,
            conversation_id=original_request.conversation_id,
            user_id=str(user_id) if user_id else None,
            question=original_request.question,
            answer=answer,
            tokens_used=100,
            source_documents=[]
        )
        
        from app.models.vector_models import QueryRewriteResult
        
        return AIQAResponse(
            answer=answer,
            source_documents=[],
            confidence_score=0.0,
            tokens_used=100,
            processing_time=0.5,
            query_rewrite_result=QueryRewriteResult(
                original_query=original_request.question,
                rewritten_queries=[original_request.question],
                extracted_parameters={},
                intent_analysis="搜索無結果,提供調整建議"
            ),
            semantic_search_contexts=[],
            session_id=original_request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "need_clarification",
                "strategy_used": "search_no_results_clarification",
                "api_calls": 2,
                "clarification_question": clarification_question,
                "suggested_responses": suggested_responses,
                "pending_action": "provide_clarification"
            },
            next_action="provide_clarification",
            pending_approval="clarification"
        )
    
    def should_request_search_approval(
        self,
        classification: QuestionClassification,
        config: dict
    ) -> bool:
        """
        判斷是否需要請求搜索批准
        
        Args:
            classification: 問題分類結果
            config: 系統配置
            
        Returns:
            bool: 是否需要批准
        """
        # 如果禁用批准機制,直接返回 False
        if config.get('auto_approve_all_searches', False):
            return False
        
        # 簡單查詢和寒暄不需要批准
        if classification.intent in [
            QuestionIntent.GREETING,
            QuestionIntent.CHITCHAT,
            QuestionIntent.SIMPLE_FACTUAL
        ]:
            return False
        
        # 複雜分析和文檔搜索需要批准
        if classification.intent in [
            QuestionIntent.DOCUMENT_SEARCH,
            QuestionIntent.COMPLEX_ANALYSIS
        ]:
            # 如果置信度很高且配置允許自動批准,則跳過
            if classification.confidence > 0.9 and config.get('auto_approve_high_confidence', False):
                logger.info(f"高置信度({classification.confidence:.2f}),自動批准搜索")
                return False
            
            return True
        
        return False


# 創建全局實例
workflow_coordinator = WorkflowCoordinator()

