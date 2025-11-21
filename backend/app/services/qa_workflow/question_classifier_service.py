"""
問題分類器服務

使用 Gemini 2.0 Flash 快速分類用戶問題的意圖類型
"""
import logging
import time
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.question_models import (
    QuestionIntent,
    QuestionClassification,
    QuestionClassifierConfig
)
from app.services.ai.unified_ai_service_simplified import (
    unified_ai_service_simplified,
    AIRequest,
    TaskType
)

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class QuestionClassifierService:
    """問題分類器服務"""
    
    def __init__(self):
        # 從配置文件讀取設定(不硬編碼)
        from app.core.config import settings
        
        self.config = QuestionClassifierConfig(
            enabled=settings.QUESTION_CLASSIFIER_ENABLED,
            model=settings.QUESTION_CLASSIFIER_MODEL,
            confidence_threshold=settings.QUESTION_CLASSIFIER_CONFIDENCE_THRESHOLD
        )
        logger.info(f"問題分類器初始化完成,使用模型: {self.config.model}, 啟用狀態: {self.config.enabled}")
    
    async def classify_question(
        self,
        question: str,
        conversation_history: Optional[list] = None,
        has_cached_documents: bool = False,
        cached_documents_info: Optional[list] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
        user_id: Optional[str] = None
    ) -> QuestionClassification:
        """
        分類用戶問題的意圖
        
        Args:
            question: 用戶問題
            conversation_history: 對話歷史(可選)
            has_cached_documents: 是否有緩存的文檔
            db: 數據庫連接
            user_id: 用戶ID(用於日誌記錄)
            
        Returns:
            QuestionClassification: 分類結果
        """
        if not self.config.enabled:
            logger.warning("問題分類器已禁用,返回默認分類")
            return self._get_default_classification(question)
        
        start_time = time.time()
        
        try:
            # 準備上下文信息
            has_conversation_history = bool(conversation_history and len(conversation_history) > 0)
            
            # 格式化對話歷史
            conversation_history_text = ""
            if has_conversation_history:
                conversation_history_text = "=== 最近對話記錄 ===\n"
                
                # 重要：成對處理用戶問題和AI回答，保持上下文連貫性
                i = 0
                while i < len(conversation_history):
                    msg = conversation_history[i]
                    role_name = "用戶" if msg.get("role") == "user" else "助手"
                    content = msg.get("content", "")
                    
                    # 智能截斷：用戶問題保留完整，AI回答保留關鍵部分
                    if role_name == "用戶":
                        # 用戶問題保留完整（最多300字，確保不丟失關鍵信息）
                        if len(content) > 300:
                            content = content[:300] + "..."
                        conversation_history_text += f"用戶: {content}\n"
                    else:
                        # AI回答處理策略：盡量保留完整內容
                        if "澄清" in content or "🔖" in content or "💡" in content:
                            # 這是澄清回答，提取核心澄清問題部分即可（澄清回答通常很長但重點在問題）
                            lines = content.split('\n')
                            # 保留"關於您的問題"和"💡"開頭的澄清問題
                            core_parts = []
                            for line in lines:
                                if '關於您的問題' in line or '💡' in line:
                                    core_parts.append(line)
                                    if len(core_parts) >= 2:
                                        break
                            if core_parts:
                                content = '\n'.join(core_parts)
                            elif len(content) > 600:
                                content = content[:600] + "..."
                        else:
                            # 普通回答：意圖分類時適度保留即可（理解上下文即可）
                            # 保留前800字（包含摘要和主要信息）
                            if len(content) > 800:
                                content = content[:800] + "...[後續省略]"
                        
                        conversation_history_text += f"助手: {content}\n"
                    
                    i += 1
                
                conversation_history_text += "=== 當前問題 ==="
            else:
                conversation_history_text = "無對話歷史"
            
            # 格式化文檔池信息（按相關性排序）
            cached_documents_text = ""
            if cached_documents_info and len(cached_documents_info) > 0:
                cached_documents_text = "=== 文檔池（會話文檔，按相關性排序）===\n"
                for doc_info in cached_documents_info:
                    doc_id = doc_info.get("document_id", "unknown")
                    filename = doc_info.get("filename", "未知文件")
                    summary = doc_info.get("summary", "")
                    relevance_score = doc_info.get("relevance_score", 0.0)
                    access_count = doc_info.get("access_count", 0)
                    key_concepts = doc_info.get("key_concepts", [])
                    semantic_tags = doc_info.get("semantic_tags", [])
                    ref_num = doc_info.get("reference_number", 0)
                    
                    cached_documents_text += f"文檔{ref_num} (ID: {doc_id}):\n"
                    cached_documents_text += f"  文件名: {filename}\n"
                    cached_documents_text += f"  相關性: {relevance_score:.2f} (訪問 {access_count} 次)\n"
                    if summary:
                        cached_documents_text += f"  摘要: {summary[:200]}{'...' if len(summary) > 200 else ''}\n"
                    if key_concepts:
                        cached_documents_text += f"  關鍵概念: {', '.join(key_concepts)}\n"
                    if semantic_tags:
                        cached_documents_text += f"  語義標籤: {', '.join(semantic_tags)}\n"
                    cached_documents_text += "\n"
            else:
                cached_documents_text = "無緩存文檔"
            
            # 🔍 調試輸出：顯示傳遞給AI的完整內容
            logger.info("="*80)
            logger.info("📤 傳遞給AI意圖分類的內容:")
            logger.info(f"當前問題: {question}")
            logger.info(f"對話歷史:\n{conversation_history_text}")
            logger.info(f"緩存文檔:\n{cached_documents_text}")
            logger.info("="*80)
            
            # 調用 AI 進行分類
            ai_request = AIRequest(
                task_type=TaskType.QUESTION_INTENT_CLASSIFICATION,
                content=question,
                model_preference=self.config.model,
                prompt_params={
                    "user_question": question,
                    "conversation_history": conversation_history_text,
                    "has_conversation_history": str(has_conversation_history),
                    "has_cached_documents": str(has_cached_documents),
                    "cached_documents_info": cached_documents_text
                },
                user_id=user_id,
                generation_params_override={
                    "temperature": self.config.temperature,
                    "max_output_tokens": self.config.max_output_tokens
                }
            )
            
            response = await unified_ai_service_simplified.process_request(ai_request, db)
            
            if not response.success:
                logger.error(f"問題分類失敗: {response.error_message}")
                return self._get_fallback_classification(question, "AI 分類失敗")
            
            # 解析分類結果
            classification_data = response.output_data
            
            # 🔍 調試輸出：顯示AI的分類結果
            logger.info("="*80)
            logger.info("📥 AI分類結果:")
            logger.info(f"意圖: {classification_data.get('intent')}")
            logger.info(f"置信度: {classification_data.get('confidence')}")
            logger.info(f"推理: {classification_data.get('reasoning')}")
            logger.info("="*80)
            
            # 驗證並構建分類結果
            classification = QuestionClassification(
                intent=QuestionIntent(classification_data.get("intent", "document_search")),
                confidence=float(classification_data.get("confidence", 0.5)),
                reasoning=classification_data.get("reasoning", ""),
                requires_documents=bool(classification_data.get("requires_documents", True)),
                requires_context=bool(classification_data.get("requires_context", False)),
                suggested_strategy=classification_data.get("suggested_strategy", "standard_search"),
                query_complexity=classification_data.get("query_complexity", "moderate"),
                estimated_api_calls=int(classification_data.get("estimated_api_calls", 3)),
                clarification_question=classification_data.get("clarification_question"),
                suggested_responses=classification_data.get("suggested_responses"),
                target_document_ids=classification_data.get("target_document_ids"),
                target_document_reasoning=classification_data.get("target_document_reasoning")
            )
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"問題分類完成: intent={classification.intent}, "
                f"confidence={classification.confidence:.2f}, "
                f"time={processing_time:.2f}s"
            )
            
            # 記錄日誌
            if db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"問題分類: {classification.intent}",
                    source="service.question_classifier.classify",
                    user_id=user_id,
                    details={
                        "question": question[:100],
                        "intent": classification.intent,
                        "confidence": classification.confidence,
                        "strategy": classification.suggested_strategy,
                        "processing_time": processing_time,
                        "api_calls_estimate": classification.estimated_api_calls
                    }
                )
            
            # 置信度檢查 - 確保模糊問題被識別
            # 正確邏輯: 有對話歷史時，AI應該更確定，因此要求更高的置信度
            effective_threshold = self.config.confidence_threshold  # 默認 0.8
            
            # 如果有對話歷史，實際上應該**提高**置信度要求
            # 因為有更多上下文信息，AI應該能給出更確定的判斷
            # 但為了平滑過渡，暫時保持相同標準
            if conversation_history and len(conversation_history) > 0:
                # 保持相同標準，不降低也不提高
                logger.info(f"有對話歷史，維持置信度閾值: {effective_threshold:.2f}")
            
            if classification.confidence < effective_threshold:
                logger.warning(
                    f"分類置信度低於閾值 ({classification.confidence:.2f} < {effective_threshold:.2f}), "
                    f"需要澄清"
                )
                # 如果置信度低,改為 clarification_needed
                if classification.intent not in [QuestionIntent.GREETING, QuestionIntent.CHITCHAT]:
                    classification.intent = QuestionIntent.CLARIFICATION_NEEDED
                    classification.suggested_strategy = "ask_clarification"
                    logger.info(f"置信度不足,改為需要澄清")
            else:
                logger.info(f"置信度{classification.confidence:.2f}足夠,保持意圖{classification.intent}")
            
            return classification
            
        except Exception as e:
            logger.error(f"問題分類發生錯誤: {e}", exc_info=True)
            if db is not None:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"問題分類錯誤: {str(e)}",
                    source="service.question_classifier.classify_error",
                    user_id=user_id,
                    details={"question": question[:100], "error": str(e)}
                )
            return self._get_fallback_classification(question, f"分類錯誤: {str(e)}")
    
    def _get_default_classification(self, question: str) -> QuestionClassification:
        """獲取默認分類(當分類器禁用時)"""
        return QuestionClassification(
            intent=QuestionIntent.DOCUMENT_SEARCH,
            confidence=0.5,
            reasoning="分類器已禁用,使用默認策略",
            requires_documents=True,
            requires_context=False,
            suggested_strategy="standard_search",
            query_complexity="moderate",
            estimated_api_calls=3
        )
    
    def _get_fallback_classification(self, question: str, reason: str) -> QuestionClassification:
        """獲取回退分類(當分類失敗時)"""
        # 使用簡單的規則判斷
        q_lower = question.lower().strip()
        q_len = len(question)
        
        # 寒暄判斷
        greetings = ["你好", "hi", "hello", "嗨", "哈囉", "早安", "午安", "晚安"]
        if any(g in q_lower for g in greetings) and q_len < 10:
            return QuestionClassification(
                intent=QuestionIntent.GREETING,
                confidence=0.8,
                reasoning=f"規則判斷: 寒暄問候 ({reason})",
                requires_documents=False,
                requires_context=False,
                suggested_strategy="direct_answer",
                query_complexity="simple",
                estimated_api_calls=1
            )
        
        # 模糊判斷
        vague_words = ["那個", "這個", "之前", "剛才", "的那個"]
        if any(v in question for v in vague_words) or q_len < 5:
            return QuestionClassification(
                intent=QuestionIntent.CLARIFICATION_NEEDED,
                confidence=0.7,
                reasoning=f"規則判斷: 問題模糊 ({reason})",
                requires_documents=False,
                requires_context=True,
                suggested_strategy="ask_clarification",
                query_complexity="simple",
                estimated_api_calls=2,
                clarification_question="能否更具體地說明您的問題?",
                suggested_responses=["詳細描述問題", "提供更多信息"]
            )
        
        # 默認為文檔搜索
        return QuestionClassification(
            intent=QuestionIntent.DOCUMENT_SEARCH,
            confidence=0.6,
            reasoning=f"規則回退判斷 ({reason})",
            requires_documents=True,
            requires_context=False,
            suggested_strategy="standard_search",
            query_complexity="moderate",
            estimated_api_calls=3
        )
    
    async def generate_clarification_question(
        self,
        original_question: str,
        ambiguity_reason: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> dict:
        """
        生成澄清問題(帶對話歷史)
        
        Args:
            original_question: 原始問題
            ambiguity_reason: 模糊的原因
            db: 數據庫連接
            user_id: 用戶ID
            conversation_id: 對話ID
            
        Returns:
            dict: 包含澄清問題和建議回答的字典
        """
        # 載入對話歷史
        conversation_history_text = ""
        if conversation_id and user_id and db is not None:
            from app.services.qa_workflow.unified_context_helper import unified_context_helper
            
            conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
                db=db,
                conversation_id=conversation_id,
                user_id=user_id,
                limit=10,  # 增加到10條，確保多輪澄清不丟失上下文
                max_content_length=1500  # 增加到1500，保留完整信息
            )
            
            if conversation_history_text:
                logger.info("生成澄清問題時已載入對話歷史")
        
        try:
            ai_request = AIRequest(
                task_type=TaskType.GENERATE_CLARIFICATION_QUESTION,
                content=original_question,
                model_preference=self.config.model,
                prompt_params={
                    "user_question": original_question,
                    "ambiguity_reason": ambiguity_reason,
                    "conversation_history": conversation_history_text or "無對話歷史"
                },
                user_id=user_id
            )
            
            response = await unified_ai_service_simplified.process_request(ai_request, db)
            
            if response.success and response.output_data:
                return response.output_data
            else:
                logger.error(f"生成澄清問題失敗: {response.error_message}")
                return {
                    "clarification_question": "能否請您提供更多細節?",
                    "reasoning": "AI生成失敗,使用默認澄清問題",
                    "suggested_responses": ["提供更多信息", "詳細說明"],
                    "missing_information": ["具體內容"]
                }
                
        except Exception as e:
            logger.error(f"生成澄清問題發生錯誤: {e}", exc_info=True)
            return {
                "clarification_question": "能否請您提供更多細節?",
                "reasoning": f"錯誤: {str(e)}",
                "suggested_responses": ["提供更多信息"],
                "missing_information": []
            }


# 創建全局實例
question_classifier_service = QuestionClassifierService()

