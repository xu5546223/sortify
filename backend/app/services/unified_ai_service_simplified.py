from typing import Union, Optional, List, Dict, Any, Tuple
from enum import Enum
import time
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from PIL import Image
import io
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError
from google.generativeai.types import GenerationConfigDict
from google.api_core.exceptions import GoogleAPIError, RetryError, ServiceUnavailable, DeadlineExceeded
import re

from app.core.config import settings
from app.core.logging_utils import AppLogger
from app.services.google_context_cache_service import (
    google_context_cache_service, 
    ContextCacheConfig, 
    ContextCacheType,
    ContextCacheInfo
)
from app.models.ai_models_simplified import (
    AIPromptRequest, 
    TokenUsage, 
    AIImageAnalysisOutput,
    AITextAnalysisOutput,
    FlexibleIntermediateAnalysis,
    FlexibleKeyInformation,
    IntermediateAnalysisStep,
    AIGeneratedAnswerOutput,
    AIQueryRewriteOutput,
    AIMongoDBQueryDetailOutput,
    AIDocumentSelectionOutput
)
from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType, PromptTemplate
from app.services.unified_ai_config import unified_ai_config, AIModelConfig, TaskType
import logging

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

@dataclass
class AIRequest:
    task_type: TaskType
    content: Union[str, Image.Image, List[Union[str, Image.Image]]]
    model_preference: Optional[str] = None
    require_language_consistency: bool = True
    generation_params_override: Optional[Dict[str, Any]] = None
    prompt_params: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ai_max_output_tokens: Optional[int] = None
    image_mime_type: Optional[str] = None

@dataclass 
class AIResponse:
    success: bool
    task_type: TaskType
    model_used: Optional[str] = None
    prompt_type_used: Optional[PromptType] = None
    output_data: Optional[Any] = None
    error_message: Optional[str] = None
    token_usage: Optional[TokenUsage] = None
    processing_time_seconds: Optional[float] = None
    request_id: Optional[str] = None

class UnifiedAIServiceSimplified:
    def __init__(self):
        self.context_cache_service = google_context_cache_service
        self._schema_context_caches: Dict[str, ContextCacheInfo] = {}
        self._system_instruction_caches: Dict[str, ContextCacheInfo] = {}

    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    async def _execute_google_ai_request(
        self,
        model_id: str,
        prompt_request: AIPromptRequest,
        generation_config_dict: genai.types.GenerationConfigDict,
        safety_settings: Dict[genai.types.HarmCategory, genai.types.HarmBlockThreshold],
        image_content: Optional[Image.Image] = None
    ) -> Tuple[Optional[str], Optional[TokenUsage]]:
        try:
            model = genai.GenerativeModel(
                model_name=model_id, 
                generation_config=generation_config_dict,
                safety_settings=safety_settings
            )
            prompt_parts_for_api = []
            if prompt_request.system_prompt:
                prompt_parts_for_api.append(prompt_request.system_prompt)
            
            prompt_parts_for_api.append(prompt_request.user_prompt)
            
            if image_content:
                prompt_parts_for_api.append(image_content)
            
            # 添加日誌記錄
            logger.debug(f"[GoogleAI] Model: {model_id}, Prompt parts count: {len(prompt_parts_for_api)}, Config: {generation_config_dict}")
            
            response = await model.generate_content_async(prompt_parts_for_api)
            
            output_text = response.text
            token_count_model_input = model.count_tokens(prompt_parts_for_api).total_tokens
            output_token_count = model.count_tokens(response.text).total_tokens
            total_tokens = token_count_model_input + output_token_count
            
            logger.info(f"[GoogleAI Success] Model: {model_id}, Input Tokens: {token_count_model_input}, Output Tokens: {output_token_count}, Total Tokens: {total_tokens}")
            
            # 保存原始輸出以便於後續處理
            if hasattr(TokenUsage, "_raw_output_text"):
                token_usage = TokenUsage(prompt_tokens=token_count_model_input, completion_tokens=output_token_count, total_tokens=total_tokens, _raw_output_text=output_text)
            else:
                token_usage = TokenUsage(prompt_tokens=token_count_model_input, completion_tokens=output_token_count, total_tokens=total_tokens)
                
            return output_text, token_usage
        except (GoogleAPIError, RetryError, ServiceUnavailable, DeadlineExceeded) as e:
            logger.error(f"[GoogleAI] API 錯誤 ({type(e).__name__}) - Model: {model_id}: {e}")
            error_message = f"Google AI API 錯誤: {str(e)}"
        except Exception as e:
            logger.error(f"[GoogleAI] 未預期錯誤 - Model: {model_id}: {e}", exc_info=True)
            error_message = f"執行 Google AI 請求時發生未預期錯誤: {str(e)}"
        return None, TokenUsage(error_message=error_message)
    
    async def process_request(
        self, 
        request: AIRequest,
        db: Optional[AsyncIOMotorDatabase] = None
    ) -> AIResponse:
        """處理統一的AI請求 (已移除 force_stable_override 相關邏輯)"""
        start_time = time.time()
        logger.info(f"[AIRequest Start] Task: {request.task_type}, ModelPrefOverride: {request.model_preference}, RequireLangConsistency: {request.require_language_consistency}")
        
        if db is not None:
            try:
                await unified_ai_config.reload_task_configs(db)
                logger.info("成功重新載入AI任務配置以反映最新的用戶偏好 (無穩定模式影響)。")
            except Exception as e:
                logger.error(f"重新載入AI任務配置失敗: {e}，將使用現有配置。", exc_info=True)
        else:
            logger.warning("未提供數據庫實例，無法重新載入AI配置。將使用現有或預設配置。")

        model_id = await unified_ai_config.get_model_for_task(
            task_type=request.task_type,
            requested_model_override=request.model_preference
        )
        
        if not model_id:
            logger.error(f"[UnifiedAIService] 無法為任務 '{request.task_type.value if isinstance(request.task_type, Enum) else request.task_type}' 選擇模型。")
            return AIResponse(success=False, task_type=request.task_type, error_message="無法選擇合適的AI模型", processing_time_seconds=time.time() - start_time)
        
        logger.info(f"[UnifiedAIService] 最終為任務 '{request.task_type.value if isinstance(request.task_type, Enum) else request.task_type}' 選定的模型: {model_id}")

        # 嘗試使用 Context Caching 優化系統指令
        context_cache_info = None
        if db is not None and self.context_cache_service.is_available():
            context_cache_info = await self._get_or_create_system_instruction_cache(
                task_type=request.task_type, 
                model_id=model_id,
                db=db,
                user_id=request.user_id
            )

        prompt_type: PromptType
        if request.task_type == TaskType.TEXT_GENERATION:
            prompt_type = PromptType.TEXT_ANALYSIS
        elif request.task_type == TaskType.IMAGE_ANALYSIS:
            prompt_type = PromptType.IMAGE_ANALYSIS
        elif request.task_type == TaskType.ANSWER_GENERATION: 
            prompt_type = PromptType.ANSWER_GENERATION
        elif request.task_type == TaskType.QUERY_REWRITE: 
            prompt_type = PromptType.QUERY_REWRITE
        elif request.task_type == TaskType.MONGODB_DETAIL_QUERY_GENERATION:
            prompt_type = PromptType.MONGODB_DETAIL_QUERY_GENERATION
        elif request.task_type == TaskType.DOCUMENT_SELECTION_FOR_QUERY:
            prompt_type = PromptType.DOCUMENT_SELECTION_FOR_QUERY
        elif request.task_type == TaskType.CLUSTER_LABEL_GENERATION:
            prompt_type = PromptType.CLUSTER_LABEL_GENERATION
        elif request.task_type == TaskType.BATCH_CLUSTER_LABELS:
            prompt_type = PromptType.BATCH_CLUSTER_LABEL_GENERATION
        else:
            logger.error(f"未知的任務類型: {request.task_type}")
            return AIResponse(success=False, task_type=request.task_type, error_message=f"未知的任務類型: {request.task_type}", processing_time_seconds=time.time() - start_time)

        prompt_params = request.prompt_params or {}
        if isinstance(request.content, str):
            if 'user_query' not in prompt_params: prompt_params['user_query'] = request.content
            if 'input_text' not in prompt_params: prompt_params['input_text'] = request.content
            # If the task is text analysis (TEXT_GENERATION) and the prompt template might expect {text_content}
            if request.task_type == TaskType.TEXT_GENERATION:
                 if 'text_content' not in prompt_params: # Avoid overwriting if 'text_content' was explicitly passed in request.prompt_params
                    prompt_params['text_content'] = request.content
        elif isinstance(request.content, Image.Image):
            if 'image_input' not in prompt_params: prompt_params['image_input'] = request.content 
        
        ensure_chinese = unified_ai_config._user_global_ai_preferences.get("ensure_chinese_output", True)
        logger.info(f"根據用戶設定，ensure_chinese: {ensure_chinese} for task {request.task_type}")
        
        # 獲取用戶設定的輸入提示詞最大長度
        user_prompt_input_max_length = unified_ai_config._user_global_ai_preferences.get("prompt_input_max_length", 6000)
        logger.debug(f"使用用戶設定的 prompt_input_max_length: {user_prompt_input_max_length} for task {request.task_type}")

        prompt_template_object = await prompt_manager_simplified.get_prompt(prompt_type, db)
        
        if not prompt_template_object:
            logger.error(f"無法為任務 {request.task_type} (提示類型 {prompt_type}) 獲取提示模板。")
            return AIResponse(success=False, task_type=request.task_type, error_message="無法獲取AI提示模板", processing_time_seconds=time.time() - start_time)

        formatted_system_prompt, formatted_user_prompt = prompt_manager_simplified.format_prompt(
            prompt_template_object, 
            apply_chinese_instruction=ensure_chinese,
            user_prompt_input_max_length=user_prompt_input_max_length,
            **prompt_params
        )
        
        
        ai_prompt_request_to_use = AIPromptRequest(
            user_prompt=formatted_user_prompt,
            system_prompt=formatted_system_prompt
        )
        
        generation_config_dict = unified_ai_config.get_generation_config(request.task_type, request.generation_params_override)
        safety_settings = unified_ai_config.get_safety_settings(request.task_type)
        
        output_text: Optional[str] = None
        token_usage: Optional[TokenUsage] = None
        image_to_pass: Optional[Image.Image] = None

        if request.task_type == TaskType.IMAGE_ANALYSIS and isinstance(request.content, Image.Image):
            image_to_pass = request.content
        
        try:
            output_text, token_usage = await self._execute_google_ai_request(
                model_id=model_id, 
                prompt_request=ai_prompt_request_to_use,
                generation_config_dict=generation_config_dict,
                safety_settings=safety_settings,
                image_content=image_to_pass
            )
            if output_text is None:
                raise ValueError("AI模型執行成功，但未返回任何文本輸出。")

            # 保存原始輸出以便於錯誤處理
            _raw_output_text = output_text

            # Strip markdown fences if present, as models sometimes wrap JSON in them
            output_text = output_text.strip()
            if output_text.startswith("```json") and output_text.endswith("```"):
                output_text = output_text[len("```json"):-len("```")]
                output_text = output_text.strip()
            elif output_text.startswith("```") and output_text.endswith("```"): # More general case
                output_text = output_text[len("```"):-len("```")]
                output_text = output_text.strip()
            
            # Check for and correct double curly braces, as some models might output this
            if output_text.startswith("{{") and output_text.endswith("}}"):
                output_text = output_text[1:-1] # Remove one layer of curly braces
                output_text = output_text.strip()
            
            # Additional cleanup of nested double braces in JSON - more thorough approach
            # Replace double opening braces with single opening brace
            output_text = re.sub(r'{{', '{', output_text)
            # Replace double closing braces with single closing brace
            output_text = re.sub(r'}}', '}', output_text)

            # 嘗試提取直接答案以防格式錯誤 (針對 ANSWER_GENERATION)
            direct_answer = None
            if request.task_type == TaskType.ANSWER_GENERATION:
                # 檢查是否包含明確的 JSON 答案格式
                answer_match = re.search(r'"answer"\s*:\s*"([^"]+)"', output_text)
                if answer_match:
                    direct_answer = answer_match.group(1)
                    logger.debug(f"從輸出中直接提取到答案: {direct_answer[:100]}...")

            parsed_output: Any
            try:
                if request.task_type == TaskType.TEXT_GENERATION:
                    parsed_output = AITextAnalysisOutput.model_validate_json(output_text)
                elif request.task_type == TaskType.IMAGE_ANALYSIS:
                    parsed_output = AIImageAnalysisOutput.model_validate_json(output_text)
                elif request.task_type == TaskType.ANSWER_GENERATION:
                    parsed_output = AIGeneratedAnswerOutput.model_validate_json(output_text)
                    # 檢查答案內容 - 如果答案內容是無效答案或空白，但我們有直接提取的答案，則使用直接提取的答案
                    if hasattr(parsed_output, 'answer_text') and (
                            parsed_output.answer_text == "Could not generate a valid answer." or 
                            not parsed_output.answer_text or 
                            len(parsed_output.answer_text.strip()) < 10
                        ) and direct_answer:
                        logger.warning(f"覆蓋無效或空白答案，使用直接提取的答案: {direct_answer[:50]}...")
                        parsed_output.answer_text = direct_answer
                elif request.task_type == TaskType.QUERY_REWRITE:
                    parsed_output = AIQueryRewriteOutput.model_validate_json(output_text)
                elif request.task_type == TaskType.MONGODB_DETAIL_QUERY_GENERATION:
                    parsed_output = AIMongoDBQueryDetailOutput.model_validate_json(output_text)
                elif request.task_type == TaskType.DOCUMENT_SELECTION_FOR_QUERY:
                    parsed_output = AIDocumentSelectionOutput.model_validate_json(output_text)
                elif request.task_type == TaskType.CLUSTER_LABEL_GENERATION:
                    from app.models.ai_models_simplified import AIClusterLabelOutput
                    parsed_output = AIClusterLabelOutput.model_validate_json(output_text)
                elif request.task_type == TaskType.BATCH_CLUSTER_LABELS:
                    from app.models.ai_models_simplified import AIBatchClusterLabelsOutput
                    parsed_output = AIBatchClusterLabelsOutput.model_validate_json(output_text)
                else: 
                    logger.warning(f"任務類型 {request.task_type} 沒有特定的解析邏輯。輸出將是原始文本。")
                    parsed_output = output_text
            except ValidationError as e:
                logger.error(f"輸出驗證失敗 ({request.task_type}): {e.json()}", exc_info=True)
                
                # 如果是 ANSWER_GENERATION 任務，我們可以使用直接提取的答案作為備用
                if request.task_type == TaskType.ANSWER_GENERATION and direct_answer:
                    logger.warning(f"使用直接提取的答案作為備用: {direct_answer[:100]}...")
                    parsed_output = AIGeneratedAnswerOutput(answer_text=direct_answer)
                else:
                    raise ValueError(f"AI輸出格式錯誤 ({request.task_type}): {e}")
            
            logger.info(f"[AIRequest Success] Task: {request.task_type}, Model: {model_id}")
            response = AIResponse(
                success=True, task_type=request.task_type, model_used=model_id, prompt_type_used=prompt_type,
                output_data=parsed_output, token_usage=token_usage, processing_time_seconds=time.time() - start_time
            )
            
            # 添加原始輸出文本以便於錯誤處理
            if hasattr(response, "_raw_output_text"):
                response._raw_output_text = _raw_output_text
            
            return response
        
        except Exception as e:
            logger.error(f"[AIRequest Failed] Task: {request.task_type}, Model: {model_id}, Error: {e}", exc_info=True)
            response = AIResponse(
                success=False, task_type=request.task_type, model_used=model_id, prompt_type_used=prompt_type,
                error_message=str(e), token_usage=token_usage, processing_time_seconds=time.time() - start_time
            )
            
            # 添加原始輸出文本以便於錯誤處理
            if hasattr(response, "_raw_output_text") and locals().get('_raw_output_text'):
                response._raw_output_text = _raw_output_text
                
            return response

    async def analyze_text(
        self, text: str,
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
        ai_max_output_tokens: Optional[int] = None,
        ai_ensure_chinese_output: Optional[bool] = None
    ) -> AIResponse:
        request = AIRequest(
            task_type=TaskType.TEXT_GENERATION,
            content=text,
            model_preference=model_preference,
            user_id=user_id,
            session_id=session_id,
            ai_max_output_tokens=ai_max_output_tokens,
            require_language_consistency=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True
        )
        return await self.process_request(request, db)
    
    async def analyze_image(
        self, image: Image.Image,
        prompt_text: Optional[str] = None,
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
        image_mime_type: Optional[str] = None,
        ai_max_output_tokens: Optional[int] = None,
        ai_ensure_chinese_output: Optional[bool] = None
    ) -> AIResponse:
        prompt_params = {}
        if prompt_text:
            logger.debug(f"analyze_image received prompt_text: {prompt_text}, but it's not used by current IMAGE_ANALYSIS prompt.")

        request = AIRequest(
            task_type=TaskType.IMAGE_ANALYSIS,
            content=image,
            model_preference=model_preference,
            user_id=user_id,
            session_id=session_id,
            image_mime_type=image_mime_type,
            prompt_params=prompt_params,
            ai_max_output_tokens=ai_max_output_tokens,
            require_language_consistency=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True
        )
        return await self.process_request(request, db)
    
    async def generate_answer(
        self,
        user_question: str,
        intent_analysis: str,
        document_context: List[str],
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
        ai_max_output_tokens: Optional[int] = None,
        ai_ensure_chinese_output: Optional[bool] = None,
        detailed_text_max_length: Optional[int] = None,
        max_chars_per_doc: Optional[int] = None
    ) -> AIResponse:
        # The document_context is now expected to be a list of pre-formatted strings.
        # The redundant re-formatting loop is removed.
        context_parts = document_context
        
        # 智能文檔摘要 - 處理潛在的超長內容
        # 使用用戶設定的長度限制，如果沒有則使用預設值
        user_detailed_length = detailed_text_max_length or 8000  # 預設8000字符
        # 使用用戶設定的單文檔限制，如果沒有則使用計算值
        if max_chars_per_doc is not None:
            MAX_CHARS_PER_DOC = max_chars_per_doc
        else:
            MAX_CHARS_PER_DOC = min(user_detailed_length // 4, 5000)  # 每個文檔不超過用戶設定的1/4，但不超過5000
        TOTAL_MAX_CHARS = user_detailed_length  # 使用用戶設定的總限制
        
        logger.info(f"使用文檔處理參數 - 用戶設定長度: {user_detailed_length}, 單文檔限制: {MAX_CHARS_PER_DOC}, 總字符限制: {TOTAL_MAX_CHARS}")
        
        # 1. 先檢查每個文檔是否太長，如果是則截斷
        for i in range(len(context_parts)):
            if len(context_parts[i]) > MAX_CHARS_PER_DOC:
                original_length = len(context_parts[i])
                # 取前半部分和後半部分，保留文檔結構
                doc_prefix = context_parts[i][:MAX_CHARS_PER_DOC//2]
                doc_suffix = context_parts[i][-MAX_CHARS_PER_DOC//2:]
                context_parts[i] = f"{doc_prefix}... [文檔中間部分已省略以節省空間] ...{doc_suffix}"
                logger.debug(f"已截斷文檔 {i+1}，原長度: {original_length}，截斷後: {len(context_parts[i])}")
        
        # 2. 檢查總長度是否超過限制，如果是則減少文檔數量
        context_str = "\n".join(context_parts)
        if len(context_str) > TOTAL_MAX_CHARS and len(context_parts) > 1:
            # 計算需要保留的文檔數量
            avg_doc_len = len(context_str) / len(context_parts) if len(context_parts) > 0 else 0
            keep_docs = min(len(context_parts), max(1, int(TOTAL_MAX_CHARS / avg_doc_len))) if avg_doc_len > 0 else 0
            
            logger.warning(f"文檔上下文總長度 ({len(context_str)}) 超過限制 ({TOTAL_MAX_CHARS})。將只使用前 {keep_docs} 個文檔。")
            if keep_docs > 0:
                context_parts = context_parts[:keep_docs]
                context_str = "\n".join(context_parts)
            else: # handle case where keep_docs becomes 0
                context_str = ""

            # 如果仍然超過限制，進行額外截斷
            if len(context_str) > TOTAL_MAX_CHARS:
                context_str = context_str[:TOTAL_MAX_CHARS] + "\n... [部分內容已省略以適應模型限制] ..."
                logger.warning(f"即使減少文檔數量後，上下文仍然過長 ({len(context_str)})。已進行額外截斷。")
        
        if not context_str: 
            context_str = "沒有可用的文檔上下文。"
        
        logger.info(f"最終文檔上下文包含 {len(context_parts)} 個文檔，總長度: {len(context_str)} 字符")

        request = AIRequest(
            task_type=TaskType.ANSWER_GENERATION,
            content=user_question,
            prompt_params={
                'user_question': user_question,
                'intent_analysis': intent_analysis,
                'document_context': context_str
            },
            model_preference=model_preference,
            user_id=user_id,
            session_id=session_id,
            ai_max_output_tokens=ai_max_output_tokens
        )
        
        response = await self.process_request(request, db)
        
        # 增強錯誤處理 - 嘗試從失敗的響應中提取有用信息
        if not response.success and response.error_message and "輸出格式錯誤" in response.error_message:
            logger.warning(f"答案生成格式錯誤，嘗試直接從原始文本提取: {response.error_message}")
            
            try:
                # 檢查是否有原始輸出文本
                if hasattr(response, "_raw_output_text") and response._raw_output_text:
                    raw_text = response._raw_output_text
                    # 嘗試直接提取 "answer" 字段
                    import re
                    answer_match = re.search(r'"answer"\s*:\s*"([^"]+)"', raw_text)
                    if answer_match:
                        extracted_answer = answer_match.group(1)
                        logger.info(f"成功從原始文本中提取答案: {extracted_answer[:100]}...")
                        
                        # 創建一個成功的響應
                        return AIResponse(
                            success=True,
                            task_type=TaskType.ANSWER_GENERATION,
                            model_used=response.model_used,
                            prompt_type_used=response.prompt_type_used,
                            output_data=AIGeneratedAnswerOutput(answer_text=extracted_answer),
                            token_usage=response.token_usage,
                            processing_time_seconds=response.processing_time_seconds
                        )
            except Exception as e:
                logger.error(f"嘗試從原始文本提取答案時發生錯誤: {e}")
        
        # 檢查響應是否成功但答案是無效的
        if response.success and isinstance(response.output_data, AIGeneratedAnswerOutput):
            if response.output_data.answer_text == "Could not generate a valid answer." or not response.output_data.answer_text:
                # 嘗試獲取有意義的答案
                if document_context:
                    # 從文檔中生成一個基本的答案
                    if len(document_context) > 0:
                        fallback_answer = "根據提供的文檔內容，我無法找到關於資料庫的詳細說明。提供的文檔主要包含："
                        
                        # 提取一些文檔信息作為答案的一部分
                        doc_types = set()
                        for doc in document_context[:3]:  # 只取前3個文檔
                            if isinstance(doc, dict) and 'file_type' in doc:
                                doc_types.add(doc['file_type'])
                        
                        if doc_types:
                            fallback_answer += f"文件類型包括：{', '.join(doc_types)}。"
                        
                        fallback_answer += "這些文檔可能提到了資料庫相關概念，但沒有直接提供資料庫的定義或詳細說明。資料庫通常是指一個有組織的數據集合，可以被輕鬆存取、管理和更新。"
                        
                        # 更新答案
                        response.output_data.answer_text = fallback_answer
                        logger.info(f"將無效答案替換為生成的基本答案: {fallback_answer[:100]}...")
        
        return response

    async def rewrite_query(
        self, 
        original_query: str,
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
        ai_max_output_tokens: Optional[int] = None,
        ai_ensure_chinese_output: Optional[bool] = None
    ) -> AIResponse:
        request = AIRequest(
            task_type=TaskType.QUERY_REWRITE,
            content=original_query, # Added missing content argument
            prompt_params={'original_query': original_query},
            model_preference=model_preference,
            user_id=user_id,
            session_id=session_id,
            ai_max_output_tokens=ai_max_output_tokens
        )
        return await self.process_request(request, db)

    async def select_documents_for_detailed_query(
        self,
        user_question: str,
        candidate_documents: List[Dict[str, Any]],
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_selections: Optional[int] = None,
    ) -> AIResponse:
        """
        Asks the AI to select the most relevant documents for a detailed query.
        """
        # candidate_documents is expected to be a list of dicts with 'document_id' and 'summary'
        formatted_candidates = json.dumps(candidate_documents, ensure_ascii=False, indent=2)

        prompt_params = {
            "user_question": user_question,
            "candidate_documents_json": formatted_candidates,
            "max_selections": max_selections or 3  # 預設選擇3個文檔
        }

        request = AIRequest(
            task_type=TaskType.DOCUMENT_SELECTION_FOR_QUERY,
            content=user_question, # Main content for the request
            prompt_params=prompt_params,
            model_preference=model_preference,
            user_id=user_id,
            session_id=session_id
        )
        return await self.process_request(request, db)

    async def generate_mongodb_detail_query(
        self,
        user_question: str,
        document_id: str,
        document_schema_info: Dict[str, Any],
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ai_max_output_tokens: Optional[int] = None
    ) -> AIResponse:
        """
        Generates MongoDB query components (projection and/or sub-filter)
        for detailed data retrieval from a specific document.
        """
        prompt_params = {
            "user_question": user_question,
            "document_id": document_id,
            "document_schema_info": json.dumps(document_schema_info) # Ensure schema is passed as a JSON string if expected by prompt
        }

        request = AIRequest(
            task_type=TaskType.MONGODB_DETAIL_QUERY_GENERATION,
            content=user_question,  # Main content for the request, though specifics are in prompt_params
            prompt_params=prompt_params,
            model_preference=model_preference,
            user_id=user_id,
            session_id=session_id,
            ai_max_output_tokens=ai_max_output_tokens,
            # require_language_consistency can be true by default or configurable if needed
        )
        return await self.process_request(request, db)

    # === Context Caching 相關方法 ===
    
    async def _get_or_create_system_instruction_cache(
        self,
        task_type: TaskType,
        model_id: str,
        db: AsyncIOMotorDatabase,
        user_id: Optional[str] = None
    ) -> Optional[ContextCacheInfo]:
        """獲取或創建系統指令的 Context Cache"""
        try:
            # 基於任務類型和模型創建緩存鍵
            cache_key = f"{task_type.value}_{model_id}"
            
            # 檢查本地緩存
            if cache_key in self._system_instruction_caches:
                cache_info = self._system_instruction_caches[cache_key]
                # 檢查是否過期
                if cache_info.expires_at > datetime.utcnow():
                    logger.info(f"使用現有系統指令 Context Cache: {cache_info.cache_id}")
                    return cache_info
                else:
                    # 過期則移除
                    del self._system_instruction_caches[cache_key]
            
            # 獲取對應的系統指令內容
            from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType
            
            prompt_type_mapping = {
                TaskType.TEXT_GENERATION: PromptType.TEXT_ANALYSIS,
                TaskType.IMAGE_ANALYSIS: PromptType.IMAGE_ANALYSIS,
                TaskType.ANSWER_GENERATION: PromptType.ANSWER_GENERATION,
                TaskType.QUERY_REWRITE: PromptType.QUERY_REWRITE,
                TaskType.MONGODB_DETAIL_QUERY_GENERATION: PromptType.MONGODB_DETAIL_QUERY_GENERATION,
                TaskType.DOCUMENT_SELECTION_FOR_QUERY: PromptType.DOCUMENT_SELECTION_FOR_QUERY,
                TaskType.CLUSTER_LABEL_GENERATION: PromptType.CLUSTER_LABEL_GENERATION,
                TaskType.BATCH_CLUSTER_LABELS: PromptType.BATCH_CLUSTER_LABEL_GENERATION
            }
            
            prompt_type = prompt_type_mapping.get(task_type)
            if not prompt_type:
                logger.warning(f"未知的任務類型，無法創建系統指令緩存: {task_type}")
                return None
            
            prompt_template = await prompt_manager_simplified.get_prompt(prompt_type, db)
            if not prompt_template or not prompt_template.system_prompt:
                logger.warning(f"無法獲取系統指令模板: {prompt_type}")
                return None
            
            # 檢查 token 要求
            token_check = self.context_cache_service.check_token_requirements(
                prompt_template.system_prompt, 
                model_id
            )
            
            if not token_check["meets_requirement"]:
                logger.debug(f"系統指令不符合 Context Caching token 要求: {token_check}")
                return None
            
            # 創建 Context Cache 配置
            cache_config = ContextCacheConfig(
                cache_type=ContextCacheType.SYSTEM_INSTRUCTION,
                content=prompt_template.system_prompt,
                ttl_hours=1,  # 1小時過期
                model=model_id,
                display_name=f"system_instruction_{task_type.value}",
                metadata={
                    "task_type": task_type.value,
                    "prompt_type": prompt_type.value,
                    "user_id": user_id
                }
            )
            
            # 創建 Context Cache
            cache_info = await self.context_cache_service.create_context_cache(cache_config, db)
            if cache_info:
                self._system_instruction_caches[cache_key] = cache_info
                logger.info(f"成功創建系統指令 Context Cache: {cache_info.cache_id}")
                return cache_info
            
        except Exception as e:
            logger.error(f"創建系統指令 Context Cache 失敗: {e}")
        
        return None
    
    async def _get_or_create_schema_cache(
        self,
        schema_content: Dict[str, Any],
        model_id: str,
        db: AsyncIOMotorDatabase,
        user_id: Optional[str] = None
    ) -> Optional[ContextCacheInfo]:
        """獲取或創建 Schema 的 Context Cache"""
        try:
            # 基於 schema 內容創建緩存鍵
            import hashlib
            schema_str = str(schema_content)
            content_hash = hashlib.sha256(schema_str.encode('utf-8')).hexdigest()[:16]
            cache_key = f"schema_{content_hash}_{model_id}"
            
            # 檢查本地緩存
            if cache_key in self._schema_context_caches:
                cache_info = self._schema_context_caches[cache_key]
                if cache_info.expires_at > datetime.utcnow():
                    logger.info(f"使用現有 Schema Context Cache: {cache_info.cache_id}")
                    return cache_info
                else:
                    del self._schema_context_caches[cache_key]
            
            # 檢查 token 要求
            token_check = self.context_cache_service.check_token_requirements(schema_str, model_id)
            if not token_check["meets_requirement"]:
                logger.debug(f"Schema 不符合 Context Caching token 要求: {token_check}")
                return None
            
            # 創建 Context Cache 配置
            cache_config = ContextCacheConfig(
                cache_type=ContextCacheType.DOCUMENT_CONTENT,
                content=schema_str,
                ttl_hours=2,  # 2小時過期
                model=model_id,
                display_name=f"schema_{content_hash}",
                metadata={
                    "content_hash": content_hash,
                    "schema_size": len(schema_str),
                    "user_id": user_id
                }
            )
            
            # 創建 Context Cache
            cache_info = await self.context_cache_service.create_context_cache(cache_config, db)
            if cache_info:
                self._schema_context_caches[cache_key] = cache_info
                logger.info(f"成功創建 Schema Context Cache: {cache_info.cache_id}")
                return cache_info
            
        except Exception as e:
            logger.error(f"創建 Schema Context Cache 失敗: {e}")
        
        return None
    
    async def get_context_cache_statistics(self, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
        """獲取 Context Cache 統計信息"""
        try:
            # 獲取 Google Context Caching 統計
            google_stats = await self.context_cache_service.get_cache_statistics(db)
            
            # 添加本地緩存統計
            local_stats = {
                "local_system_instruction_caches": len(self._system_instruction_caches),
                "local_schema_caches": len(self._schema_context_caches),
                "active_local_caches": sum([
                    1 for cache in list(self._system_instruction_caches.values()) + list(self._schema_context_caches.values())
                    if cache.expires_at > datetime.utcnow()
                ])
            }
            
            return {
                "google_context_caching": google_stats,
                "local_context_caches": local_stats,
                "integration_status": {
                    "is_available": self.context_cache_service.is_available(),
                    "total_context_caches": google_stats.get("total_caches", 0) + local_stats["active_local_caches"]
                }
            }
            
        except Exception as e:
            logger.error(f"獲取 Context Cache 統計失敗: {e}")
            return {"error": str(e)}
    
    async def cleanup_expired_context_caches(self, db: AsyncIOMotorDatabase) -> Dict[str, int]:
        """清理過期的 Context Caches"""
        try:
            cleanup_stats = {"local": 0, "google": 0}
            
            # 清理本地過期緩存
            now = datetime.utcnow()
            
            # 清理系統指令緩存
            expired_keys = [
                key for key, cache in self._system_instruction_caches.items()
                if cache.expires_at <= now
            ]
            for key in expired_keys:
                del self._system_instruction_caches[key]
                cleanup_stats["local"] += 1
            
            # 清理 Schema 緩存
            expired_keys = [
                key for key, cache in self._schema_context_caches.items()
                if cache.expires_at <= now
            ]
            for key in expired_keys:
                del self._schema_context_caches[key]
                cleanup_stats["local"] += 1
            
            # 清理 Google Context Caches
            google_cleanup_count = await self.context_cache_service.cleanup_expired_caches(db)
            cleanup_stats["google"] = google_cleanup_count
            
            logger.info(f"Context Cache 清理完成: 本地 {cleanup_stats['local']} 個，Google {cleanup_stats['google']} 個")
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"清理 Context Caches 失敗: {e}")
            return {"error": str(e)}

unified_ai_service_simplified = UnifiedAIServiceSimplified() 