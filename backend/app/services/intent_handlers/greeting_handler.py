"""
寒暄處理器

處理簡單的問候和寒暄,快速回答,不需要查找文檔
"""
import time
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.models.vector_models import AIQARequest, AIQAResponse, QueryRewriteResult
from app.models.question_models import QuestionClassification

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class GreetingHandler:
    """寒暄問候處理器 - 快速回答,0次文檔查詢"""
    
    # 預設的寒暄回答
    GREETING_RESPONSES = {
        "你好": "你好!我是你的 AI 文檔助手,很高興為你服務。你可以問我關於你文檔庫的任何問題,或者上傳新的文檔讓我幫你分析。",
        "嗨": "嗨!有什麼我可以幫助你的嗎?",
        "hello": "Hello! I'm your AI document assistant. How can I help you today?",
        "hi": "Hi there! Ready to help you with your documents.",
        "早安": "早安!今天有什麼我可以協助的嗎?",
        "午安": "午安!需要查詢什麼文檔嗎?",
        "晚安": "晚安!雖然是晚上了,我還是隨時可以幫助你。",
        "哈囉": "哈囉!我是你的文檔助手,有什麼問題嗎?"
    }
    
    async def handle(
        self,
        request: AIQARequest,
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        處理寒暄問候
        
        Args:
            request: AI QA 請求
            classification: 問題分類結果
            db: 數據庫連接
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 快速友好的回答
        """
        start_time = time.time()
        
        logger.info(f"處理寒暄問候: {request.question}")
        
        # 使用統一工具載入對話歷史
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=request.conversation_id,
            user_id=user_id,
            limit=3,  # 寒暄只需要少量歷史
            max_content_length=500  # 保留足夠的上下文
        )
        
        if conversation_history_text:
            logger.info(f"寒暄處理器載入了對話歷史")
        
        # 使用統一AI接口生成友好回答
        tokens_used = 0
        try:
            from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
            
            # 構建簡單的上下文
            context_parts = []
            if conversation_history_text:
                context_parts.append(conversation_history_text)
            context_parts.append("這是一個寒暄或問候。請用友好、簡短的方式回應,並簡單介紹你是AI文檔助手,可以幫助用戶查詢和分析文檔。")
            
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=request.question,
                intent_analysis=classification.reasoning,
                document_context=context_parts,
                db=db,
                user_id=str(user_id) if user_id else None,
                model_preference=request.model_preference  # 使用用戶偏好的模型
            )
            
            if ai_response.success and ai_response.output_data:
                answer = ai_response.output_data.answer_text
                tokens_used = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
                logger.info(f"使用AI生成寒暄回答,Token: {tokens_used}")
            else:
                # AI調用失敗,使用預設回答
                logger.warning(f"AI生成失敗,使用預設回答: {ai_response.error_message}")
                answer = self._get_greeting_response(request.question) or \
                        "你好!我是你的 AI 文檔助手。你可以問我關於文檔的任何問題,例如:\n" \
                        "- 「幫我找財務報表」\n" \
                        "- 「上個月的會議記錄在哪裡?」\n" \
                        "- 「總結所有專案相關文檔」\n\n" \
                        "有什麼我可以幫助你的嗎?"
        
        except Exception as e:
            logger.error(f"寒暄回答生成錯誤,使用預設回答: {e}")
            answer = self._get_greeting_response(request.question) or \
                    "你好!我是你的 AI 文檔助手,有什麼可以幫助你的嗎?"
        
        processing_time = time.time() - start_time
        
        # 創建簡單的查詢重寫結果(保持兼容性)
        query_rewrite_result = QueryRewriteResult(
            original_query=request.question,
            rewritten_queries=[request.question],
            extracted_parameters={},
            intent_analysis=f"寒暄問候: {classification.reasoning}"
        )
        
        logger.info(f"寒暄處理完成,耗時: {processing_time:.2f}秒")
        
        # 保存對話記錄
        if db is not None:
            from app.services.qa_workflow.conversation_helper import conversation_helper
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=tokens_used,  # 使用真實token數
                source_documents=[]
            )
        
        # 記錄統計數據
        if db is not None:
            try:
                from app.services.qa_workflow.qa_analytics_service import qa_analytics_service
                await qa_analytics_service.log_qa_request(
                    db=db,
                    question=request.question,
                    classification=classification,
                    processing_time=processing_time,
                    api_calls=1,  # 分類 + 答案生成
                    strategy_used="greeting_fast_path",
                    user_id=str(user_id) if user_id else None,
                    conversation_id=request.conversation_id,
                    tokens_used=tokens_used,  # 使用真實的token數
                    success=True
                )
            except Exception as e:
                logger.warning(f"記錄統計失敗(不影響主流程): {e}")
        
        return AIQAResponse(
            answer=answer,
            source_documents=[],
            confidence_score=0.95,  # 高置信度
            tokens_used=tokens_used,  # 使用真實token數
            processing_time=processing_time,
            query_rewrite_result=query_rewrite_result,
            semantic_search_contexts=[],
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "greeting_fast_path",
                "api_calls": 0
            }
        )
    
    def _get_greeting_response(self, question: str) -> Optional[str]:
        """
        根據問題獲取對應的寒暄回答
        
        Args:
            question: 用戶問題
            
        Returns:
            str or None: 對應的回答,如果沒有匹配則返回 None
        """
        q_lower = question.lower().strip()
        
        # 移除標點符號
        q_lower = q_lower.rstrip('!?。!?')
        
        # 精確匹配
        if q_lower in self.GREETING_RESPONSES:
            return self.GREETING_RESPONSES[q_lower]
        
        # 模糊匹配
        for greeting, response in self.GREETING_RESPONSES.items():
            if greeting in q_lower and len(q_lower) <= len(greeting) + 3:
                return response
        
        return None


# 創建全局實例
greeting_handler = GreetingHandler()

