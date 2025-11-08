"""
統一 AI 服務的流式輸出擴展

為 unified_ai_service_simplified 添加流式生成功能
"""
import logging
from typing import List, Optional, AsyncGenerator
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.ai.unified_ai_config import unified_ai_config, TaskType
from app.services.ai.prompt_manager_simplified import prompt_manager_simplified, PromptType
from app.models.ai_models_simplified import AIPromptRequest

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


async def generate_answer_stream(
    user_question: str,
    intent_analysis: str,
    document_context: List[str],
    model_preference: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    db: Optional[AsyncIOMotorDatabase] = None,
    ai_max_output_tokens: Optional[int] = None,
    detailed_text_max_length: Optional[int] = None,
    max_chars_per_doc: Optional[int] = None
) -> AsyncGenerator[str, None]:
    """
    流式生成答案，逐塊輸出內容
    
    Args:
        user_question: 用戶問題
        intent_analysis: 意圖分析
        document_context: 文檔上下文列表
        model_preference: 模型偏好
        user_id: 用戶ID
        session_id: 會話ID
        db: 數據庫連接
        ai_max_output_tokens: 最大輸出token數
        detailed_text_max_length: 詳細文本最大長度
        max_chars_per_doc: 每個文檔最大字符數
        
    Yields:
        str: 生成的答案文本塊
    """
    try:
        # 使用與 generate_answer 相同的文檔處理邏輯
        context_parts = document_context
        
        user_detailed_length = detailed_text_max_length or 8000
        if max_chars_per_doc is not None:
            MAX_CHARS_PER_DOC = max_chars_per_doc
        else:
            MAX_CHARS_PER_DOC = min(user_detailed_length // 4, 5000)
        TOTAL_MAX_CHARS = user_detailed_length
        
        logger.info(f"[Stream] 使用文檔處理參數 - 單文檔限制: {MAX_CHARS_PER_DOC}, 總字符限制: {TOTAL_MAX_CHARS}")
        
        # 處理文檔上下文
        for i in range(len(context_parts)):
            if len(context_parts[i]) > MAX_CHARS_PER_DOC:
                doc_prefix = context_parts[i][:MAX_CHARS_PER_DOC//2]
                doc_suffix = context_parts[i][-MAX_CHARS_PER_DOC//2:]
                context_parts[i] = f"{doc_prefix}... [文檔中間部分已省略] ...{doc_suffix}"
        
        context_str = "\n".join(context_parts)
        if len(context_str) > TOTAL_MAX_CHARS and len(context_parts) > 1:
            avg_doc_len = len(context_str) / len(context_parts) if len(context_parts) > 0 else 0
            keep_docs = min(len(context_parts), max(1, int(TOTAL_MAX_CHARS / avg_doc_len))) if avg_doc_len > 0 else 0
            
            if keep_docs > 0:
                context_parts = context_parts[:keep_docs]
                context_str = "\n".join(context_parts)
            else:
                context_str = ""
            
            if len(context_str) > TOTAL_MAX_CHARS:
                context_str = context_str[:TOTAL_MAX_CHARS] + "\n... [部分內容已省略] ..."
        
        if not context_str:
            context_str = "沒有可用的文檔上下文。"
        
        logger.info(f"[Stream] 最終文檔上下文包含 {len(context_parts)} 個文檔，總長度: {len(context_str)} 字符")
        
        # 獲取模型配置
        if db is not None:
            await unified_ai_config.reload_task_configs(db)
        
        model_id = await unified_ai_config.get_model_for_task(
            task_type=TaskType.ANSWER_GENERATION,
            requested_model_override=model_preference
        )
        
        if not model_id:
            yield "[錯誤] 無法選擇合適的AI模型"
            return
        
        logger.info(f"[Stream] 使用模型: {model_id}")
        
        # 準備提示詞 - 使用專門的流式提示詞（Markdown 格式）
        prompt_template = await prompt_manager_simplified.get_prompt(PromptType.ANSWER_GENERATION_STREAM, db)
        if not prompt_template:
            yield "[錯誤] 無法獲取提示模板"
            return
        
        ensure_chinese = unified_ai_config._user_global_ai_preferences.get("ensure_chinese_output", True)
        user_prompt_input_max_length = unified_ai_config._user_global_ai_preferences.get("prompt_input_max_length", 6000)
        
        formatted_system_prompt, formatted_user_prompt = prompt_manager_simplified.format_prompt(
            prompt_template,
            apply_chinese_instruction=ensure_chinese,
            user_prompt_input_max_length=user_prompt_input_max_length,
            user_question=user_question,
            intent_analysis=intent_analysis,
            document_context=context_str
        )
        
        ai_prompt_request = AIPromptRequest(
            user_prompt=formatted_user_prompt,
            system_prompt=formatted_system_prompt
        )
        
        generation_config_dict = unified_ai_config.get_generation_config(TaskType.ANSWER_GENERATION)
        safety_settings = unified_ai_config.get_safety_settings(TaskType.ANSWER_GENERATION)
        
        # 流式生成答案
        logger.info(f"[Stream] 開始流式生成答案")
        full_text = ""
        
        async for chunk in unified_ai_service_simplified._execute_google_ai_request_stream(
            model_id=model_id,
            prompt_request=ai_prompt_request,
            generation_config_dict=generation_config_dict,
            safety_settings=safety_settings
        ):
            # AI 現在直接輸出 Markdown，無需解析 JSON
            # 直接傳遞原始 chunk
            full_text += chunk
            yield chunk
        
        logger.info(f"[Stream] 流式生成答案完成，總長度: {len(full_text)} 字符")
        
    except Exception as e:
        logger.error(f"[Stream] 流式生成答案失敗: {e}", exc_info=True)
        yield f"[錯誤] 生成答案時發生錯誤: {str(e)}"


# 將方法添加到 unified_ai_service_simplified 實例
unified_ai_service_simplified.generate_answer_stream = generate_answer_stream

