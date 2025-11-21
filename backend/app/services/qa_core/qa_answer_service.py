"""
QA答案生成服務

專門處理答案生成的各種場景
使用統一 AI 接口,支持用戶模型偏好
"""
import logging
import json
from typing import List, Optional, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import QueryRewriteResult, LLMContextDocument
from app.models.ai_models_simplified import AIDocumentAnalysisOutputDetail, AIGeneratedAnswerOutput
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified, AIResponse as UnifiedAIResponse

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class QAAnswerService:
    """QA答案生成服務"""
    
    async def generate_answer(
        self,
        db: AsyncIOMotorDatabase,
        original_query: str,
        documents_for_context: List[Any],
        query_rewrite_result: QueryRewriteResult,
        detailed_document_data: Optional[List[Dict[str, Any]]],
        ai_generated_query_reasoning: Optional[str],
        user_id: Optional[str],
        request_id: Optional[str],
        model_preference: Optional[str] = None,
        ensure_chinese_output: Optional[bool] = None,
        detailed_text_max_length: Optional[int] = None,
        max_chars_per_doc: Optional[int] = None,
        conversation_history: Optional[str] = None
    ) -> Tuple[str, int, float, List[LLMContextDocument]]:
        """
        生成最終答案
        
        保留原有的聚焦上下文邏輯和通用上下文邏輯
        
        Returns:
            Tuple[answer_text, tokens_used, confidence, contexts_used]
        """
        actual_contexts_for_llm: List[LLMContextDocument] = []
        context_parts = []
        
        log_details = {
            "num_docs": len(documents_for_context),
            "has_detailed_data": bool(detailed_document_data)
        }
        
        await log_event(
            db=db,
            level=LogLevel.DEBUG,
            message="組裝上下文以生成答案",
            source="service.qa_answer.generate",
            user_id=user_id,
            request_id=request_id,
            details=log_details
        )
        
        try:
            # === 聚焦上下文邏輯: 優先使用詳細資料 ===
            if detailed_document_data and len(detailed_document_data) > 0:
                logger.info(f"使用聚焦上下文: {len(detailed_document_data)} 個AI選中文件的詳細資料")
                
                for i, detail_item in enumerate(detailed_document_data):
                    doc_id = str(detail_item.get("_id", f"unknown_doc_{i}"))
                    detailed_data_str = json.dumps(detail_item, ensure_ascii=False, indent=2)
                    
                    context_preamble = f"智慧查詢文件 {doc_id} 的詳細資料:\n"
                    if i == 0 and ai_generated_query_reasoning:
                        context_preamble += f"AI 查詢推理: {ai_generated_query_reasoning}\n\n"
                    
                    context_preamble += f"查詢到的精準資料:\n{detailed_data_str}\n\n"
                    context_parts.append(context_preamble)
                    
                    actual_contexts_for_llm.append(LLMContextDocument(
                        document_id=doc_id,
                        content_used=detailed_data_str[:300],
                        source_type="ai_detailed_query"
                    ))
                
                logger.info(f"聚焦上下文: {len(context_parts)} 個詳細查詢結果")
            
            # === 通用上下文邏輯: 使用文件摘要 ===
            else:
                logger.info("使用通用上下文: 文件摘要")
                max_general_docs = 5
                
                for i, doc in enumerate(documents_for_context[:max_general_docs], 1):
                    doc_content = ""
                    content_source = "unknown"
                    doc_id_str = str(doc.id) if hasattr(doc, 'id') else f"unknown_doc_{i}"
                    
                    # 嘗試獲取 AI 分析的摘要
                    ai_summary = None
                    if hasattr(doc, 'analysis') and doc.analysis:
                        if hasattr(doc.analysis, 'ai_analysis_output') and \
                           isinstance(doc.analysis.ai_analysis_output, dict):
                            try:
                                analysis_output = AIDocumentAnalysisOutputDetail(**doc.analysis.ai_analysis_output)
                                if analysis_output.key_information and analysis_output.key_information.content_summary:
                                    ai_summary = analysis_output.key_information.content_summary
                                elif analysis_output.initial_summary:
                                    ai_summary = analysis_output.initial_summary
                            except (ValidationError, Exception):
                                pass
                    
                    # 選擇最佳內容來源
                    if ai_summary:
                        doc_content = ai_summary
                        content_source = "ai_summary"
                    elif hasattr(doc, 'extracted_text') and doc.extracted_text:
                        # 截斷過長文本
                        doc_content = doc.extracted_text[:1000]
                        if len(doc.extracted_text) > 1000:
                            doc_content += "..."
                        content_source = "extracted_text"
                    else:
                        doc_content = f"文件 '{getattr(doc, 'filename', 'N/A')}' 沒有可用內容"
                        content_source = "placeholder"
                    
                    actual_contexts_for_llm.append(LLMContextDocument(
                        document_id=doc_id_str,
                        content_used=doc_content[:300],
                        source_type=content_source
                    ))
                    
                    context_parts.append(
                        f"文件 {i} (ID: {doc_id_str}):\n{doc_content}"
                    )
                
                logger.info(f"通用上下文: {len(context_parts)} 個文件摘要")
            
            # 準備查詢
            query_for_answer = query_rewrite_result.rewritten_queries[0] \
                if query_rewrite_result.rewritten_queries else original_query
            
            # 構建清晰的上下文結構：明確分離對話歷史和當前文檔
            final_context_parts = []
            
            # 如果有對話歷史，添加到開頭並明確標註
            if conversation_history:
                final_context_parts.append(
                    f"=== 對話歷史（僅供理解問題背景，不要直接引用） ===\n{conversation_history}\n"
                    f"=== 對話歷史結束 ==="
                )
                logger.info("已添加對話歷史到上下文（明確標註）")
            
            # 添加當前檢索到的文檔
            if context_parts:
                final_context_parts.append(
                    f"\n=== 當前檢索到的文檔（請基於這些文檔回答） ===\n" +
                    "\n\n".join(context_parts) +
                    "\n=== 文檔結束 ==="
                )
                logger.info(f"已添加 {len(context_parts)} 個當前檢索文檔（明確標註）")
            
            # 調用統一 AI 服務生成答案
            logger.info(f"調用AI生成答案,使用模型偏好: {model_preference}")
            
            ai_response: UnifiedAIResponse = await unified_ai_service_simplified.generate_answer(
                user_question=query_for_answer,
                intent_analysis=query_rewrite_result.intent_analysis or "",
                document_context=final_context_parts,  # 使用重新組織的上下文
                db=db,
                model_preference=model_preference,  # 傳遞用戶模型偏好
                ai_ensure_chinese_output=ensure_chinese_output,
                detailed_text_max_length=detailed_text_max_length,
                max_chars_per_doc=max_chars_per_doc
            )
            
            tokens_used = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
            answer_text = "Error: AI服務未返回成功響應"
            confidence = 0.1
            
            if ai_response.success and ai_response.output_data:
                if isinstance(ai_response.output_data, AIGeneratedAnswerOutput):
                    answer_text = ai_response.output_data.answer_text
                else:
                    answer_text = f"Error: AI返回了意外格式"
                
                confidence = min(
                    0.9,
                    0.3 + (len(actual_contexts_for_llm) * 0.1) +
                    (0.1 if not answer_text.lower().startswith("error") else -0.2)
                )
                
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message="AI答案生成成功",
                    source="service.qa_answer.generate_success",
                    user_id=user_id,
                    request_id=request_id,
                    details={
                        "model_used": ai_response.model_used,
                        "answer_length": len(answer_text),
                        "tokens": tokens_used,
                        "confidence": confidence
                    }
                )
            else:
                error_msg = ai_response.error_message or "AI生成答案失敗"
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"AI答案生成失敗: {error_msg}",
                    source="service.qa_answer.generate_error",
                    user_id=user_id,
                    request_id=request_id,
                    details={"error": error_msg}
                )
                answer_text = f"抱歉,無法生成答案: {error_msg}"
            
            return answer_text, tokens_used, confidence, actual_contexts_for_llm
            
        except Exception as e:
            logger.error(f"生成答案時發生錯誤: {e}", exc_info=True)
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"生成答案異常: {str(e)}",
                source="service.qa_answer.generate_exception",
                user_id=user_id,
                request_id=request_id
            )
            return f"生成答案時發生內部錯誤: {str(e)}", 0, 0.0, actual_contexts_for_llm
    
    async def _fallback_basic_query(self, db: AsyncIOMotorDatabase, document) -> Dict[str, Any]:
        """回退基本查詢"""
        try:
            basic_projection = {
                "_id": 1,
                "filename": 1,
                "extracted_text": 1,
                "analysis.ai_analysis_output.key_information.content_summary": 1,
                "analysis.ai_analysis_output.key_information.semantic_tags": 1,
                "analysis.ai_analysis_output.key_information.key_concepts": 1
            }
            
            from app.services.qa_document_processor import remove_projection_path_collisions
            safe_projection = remove_projection_path_collisions(basic_projection)
            
            fetched_data = await db.documents.find_one(
                {"_id": document.id},
                projection=safe_projection
            )
            
            if fetched_data:
                def sanitize(data: Any) -> Any:
                    if isinstance(data, dict):
                        return {k: sanitize(v) for k, v in data.items()}
                    if isinstance(data, list):
                        return [sanitize(i) for i in data]
                    if isinstance(data, uuid.UUID):
                        return str(data)
                    return data
                
                return sanitize(fetched_data)
            
            return {}
            
        except Exception as e:
            logger.error(f"回退查詢失敗: {e}")
            return {}


# 創建全局實例
qa_answer_service = QAAnswerService()

