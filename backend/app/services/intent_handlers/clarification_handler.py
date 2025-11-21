"""
澄清問題處理器

處理需要澄清的模糊問題,生成友好的澄清問題引導用戶
支持用戶回答後自動重新路由到合適的處理器
"""
import time
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import AIQARequest, AIQAResponse, QueryRewriteResult
from app.models.question_models import QuestionClassification
from app.services.qa_workflow.question_classifier_service import question_classifier_service

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


# 注意: 澄清處理器的設計理念
# 1. 當首次提問模糊時,生成澄清問題
# 2. 用戶回答澄清問題後,前端會創建新的對話消息,自然進入下一輪智能路由
# 3. 由於對話歷史已保存,新一輪分類會看到完整上下文,自動路由到合適的handler
# 4. 因此 clarification_handler 主要負責"生成澄清問題",而不需要處理"澄清後的回答"


class ClarificationHandler:
    """澄清問題處理器 - 生成澄清問題,1-2次API調用"""
    
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
        處理需要澄清的問題
        
        Args:
            request: AI QA 請求
            classification: 問題分類結果
            context: 對話上下文（用於生成更好的澄清問題）
            db: 數據庫連接
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 包含澄清問題的回答
        """
        start_time = time.time()
        
        logger.info(f"處理澄清需求: {request.question}")
        
        # 如果分類結果已經包含澄清問題,直接使用
        if classification.clarification_question and classification.suggested_responses:
            clarification_question = classification.clarification_question
            suggested_responses = classification.suggested_responses
            api_calls = 1  # 只有分類的1次調用
        else:
            # 需要生成澄清問題(帶對話歷史)
            clarification_data = await question_classifier_service.generate_clarification_question(
                original_question=request.question,
                ambiguity_reason=classification.reasoning,
                db=db,
                user_id=user_id,
                conversation_id=request.conversation_id  # 傳遞conversation_id
            )
            
            clarification_question = clarification_data.get(
                "clarification_question",
                "您的問題有點模糊,能否提供更多細節?"
            )
            suggested_responses = clarification_data.get(
                "suggested_responses",
                ["提供更詳細的描述", "指定具體的文檔或主題"]
            )
            api_calls = 2  # 分類 + 生成澄清問題
        
        # 構建友好的回答
        answer = self._build_clarification_answer(
            original_question=request.question,
            clarification_question=clarification_question,
            suggested_responses=suggested_responses,
            classification=classification
        )
        
        processing_time = time.time() - start_time
        
        # 保存對話記錄
        if db is not None:
            from app.services.qa_workflow.conversation_helper import conversation_helper
            
            # ✅ 如果用戶提供了 @ 文件，傳遞給 save_qa_to_conversation
            # 它會自動調用 _update_document_pool
            source_docs = request.document_ids if request.document_ids else []
            
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=api_calls * 50,
                source_documents=source_docs
            )
        
        # 記錄日誌
        if db is not None:
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="生成澄清問題",
                source="handler.clarification",
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                details={
                    "original_question": request.question[:100],
                    "clarification_question": clarification_question,
                    "api_calls": api_calls
                }
            )
        
        # 創建查詢重寫結果
        query_rewrite_result = QueryRewriteResult(
            original_query=request.question,
            rewritten_queries=[request.question],
            extracted_parameters={},
            intent_analysis=f"需要澄清: {classification.reasoning}"
        )
        
        logger.info(f"澄清處理完成,耗時: {processing_time:.2f}秒, API調用: {api_calls}次")
        
        return AIQAResponse(
            answer=answer,
            source_documents=[],
            confidence_score=0.7,
            tokens_used=api_calls * 50,  # 估算
            processing_time=processing_time,
            query_rewrite_result=query_rewrite_result,
            semantic_search_contexts=[],
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "need_clarification",
                "strategy_used": "clarification",
                "api_calls": api_calls,
                "clarification_question": clarification_question,
                "suggested_responses": suggested_responses,
                "is_clarification": True  # 標記這是澄清問題，不需要批准流程
            },
            next_action=None,  # 澄清問題不需要 next_action
            pending_approval=None  # 澄清問題不需要批准
        )
    
    def _build_clarification_answer(
        self,
        original_question: str,
        clarification_question: str,
        suggested_responses: list,
        classification: QuestionClassification
    ) -> str:
        """
        構建友好的澄清回答
        
        Args:
            original_question: 原始問題
            clarification_question: 澄清問題
            suggested_responses: 建議的回答選項
            classification: 分類結果
            
        Returns:
            str: 格式化的澄清回答
        """
        answer_parts = []
        
        # 開頭
        answer_parts.append(f"📝 關於您的問題:「{original_question}」\n")
        
        # 說明為何需要澄清
        answer_parts.append(f"💡 {clarification_question}\n")
        
        # 提供建議選項
        if suggested_responses and len(suggested_responses) > 0:
            answer_parts.append("\n🔖 您可以:")
            for i, option in enumerate(suggested_responses, 1):
                answer_parts.append(f"\n  {i}. {option}")
        
        # 鼓勵性結尾
        answer_parts.append("\n\n✨ 提供更多細節將幫助我為您找到更準確的答案!")
        
        return "".join(answer_parts)


# 創建全局實例
clarification_handler = ClarificationHandler()

