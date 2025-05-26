from typing import Union, Optional, List, Dict, Any, Tuple
import time
import json
from dataclasses import dataclass
from PIL import Image
import io
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging_utils import AppLogger
from app.models.ai_models_simplified import (
    AIPromptRequest, 
    TokenUsage, 
    AIImageAnalysisOutput,
    AITextAnalysisOutput,
    FlexibleIntermediateAnalysis,
    FlexibleKeyInformation,
    IntermediateAnalysisStep
)
from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType
from app.services.unified_ai_config import unified_ai_config, TaskType
import logging

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

@dataclass
class AIRequest:
    """統一的AI請求結構"""
    task_type: TaskType
    prompt_type: PromptType
    content: Union[str, bytes]  # 文本內容或圖片bytes
    variables: Dict[str, Any]  # 提示詞變量
    model_preference: Optional[str] = None
    mime_type: Optional[str] = None  # 圖片MIME類型
    custom_generation_params: Optional[Dict[str, Any]] = None
    # 新增穩定性控制
    force_stable_model: bool = True  # 強制使用穩定模型
    require_language_consistency: bool = True  # 要求語言一致性

@dataclass 
class AIResponse:
    """統一的AI響應結構"""
    success: bool
    content: Union[AITextAnalysisOutput, AIImageAnalysisOutput, str]
    token_usage: TokenUsage
    model_used: str
    processing_time: float
    error_message: Optional[str] = None

class UnifiedAIServiceSimplified:
    """簡化的統一AI服務管理器 - 專注於靈活結構"""
    
    def __init__(self):
        self._configure_genai()
    
    def _configure_genai(self):
        """配置Google Generative AI"""
        if settings.GOOGLE_API_KEY:
            try:
                genai.configure(api_key=settings.GOOGLE_API_KEY)
                logger.info("Google Generative AI SDK 配置成功")
            except Exception as e:
                logger.error(f"Google Generative AI SDK 配置失敗: {e}")
        else:
            logger.warning("GOOGLE_API_KEY 未設定，AI功能將受限")
    
    async def process_request(
        self, 
        request: AIRequest,
        db: Optional[AsyncIOMotorDatabase] = None
    ) -> AIResponse:
        """處理統一的AI請求"""
        start_time = time.time()
        logger.info(f"[AIRequest Start] Task: {request.task_type}, ModelPref: {request.model_preference}, ForceStable: {request.force_stable_model}, RequireLangConsistency: {request.require_language_consistency}")
        
        # 在處理請求前，重新載入最新的用戶AI偏好設定
        if db is not None:
            try:
                await unified_ai_config.reload_task_configs(db)
                logger.info("成功重新載入AI任務配置以反映最新的用戶偏好。")
            except Exception as e:
                logger.error(f"重新載入AI任務配置失敗: {e}，將使用現有配置。", exc_info=True)
        else:
            logger.warning("未提供數據庫實例，無法重新載入AI任務配置，將使用現有配置。")

        try:
            # 檢查API Key
            if not settings.GOOGLE_API_KEY:
                return self._create_error_response(
                    request.task_type,
                    "API Key未設定",
                    0,
                    time.time() - start_time
                )
            
            # 選擇模型 - 優先使用穩定模型
            if request.force_stable_model:
                model_id = await unified_ai_config.get_stable_model_for_task(
                    request.task_type, force_stability_override=True
                )
            else:
                model_id = await unified_ai_config.get_preferred_model_for_task(
                    request.task_type, user_preference_override=request.model_preference
                )
            
            if not model_id:
                return self._create_error_response(
                    request.task_type,
                    "未找到可用的AI模型",
                    0,
                    time.time() - start_time
                )
            
            logger.info(f"選用模型: {model_id} (穩定模式: {request.force_stable_model})")
            
            # 獲取提示詞
            prompt_template = await prompt_manager_simplified.get_prompt(request.prompt_type, db)
            if not prompt_template:
                return self._create_error_response(
                    request.task_type,
                    "未找到對應的提示詞模板",
                    0,
                    time.time() - start_time
                )
            
            # 格式化提示詞
            system_prompt, user_prompt = prompt_manager_simplified.format_prompt(
                prompt_template, **request.variables
            )
            
            # 增強提示詞以確保語言一致性
            if request.require_language_consistency:
                # 在提示詞中明確要求使用繁體中文
                language_instruction = "\\n\\n重要: 請使用繁體中文進行分析和回答。所有描述、分析步驟和結論都應該用繁體中文表達。"
                system_prompt += language_instruction
                logger.info(f"[AIRequest SystemPrompt] Language consistency enabled. System prompt modified for Chinese output. Length: {len(system_prompt)}")
            else:
                logger.info(f"[AIRequest SystemPrompt] Language consistency disabled. System prompt NOT modified for Chinese output. Length: {len(system_prompt)}")
            
            # 根據任務類型調用相應的處理方法
            if request.task_type == TaskType.TEXT_GENERATION:
                return await self._process_text_request(
                    system_prompt, user_prompt, model_id, request, start_time
                )
            elif request.task_type == TaskType.IMAGE_ANALYSIS:
                return await self._process_image_request(
                    system_prompt, user_prompt, model_id, request, start_time
                )
            else:
                return self._create_error_response(
                    request.task_type,
                    f"不支持的任務類型: {request.task_type}",
                    0,
                    time.time() - start_time
                )
        
        except Exception as e:
            logger.error(f"處理AI請求失敗: {e}", exc_info=True)
            return self._create_error_response(
                request.task_type,
                f"處理請求時發生錯誤: {str(e)}",
                0,
                time.time() - start_time
            )
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _process_text_request(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        request: AIRequest,
        start_time: float
    ) -> AIResponse:
        """處理文本生成請求 - 簡化版本"""
        logger.info(f"[{request.task_type}/{model_id}] Entering _process_text_request. Attempt: {self._process_text_request.retry.statistics.get('attempt_number', 1) if hasattr(self._process_text_request, 'retry') else 'N/A'}")
        try:
            model = genai.GenerativeModel(model_id)
            
            # 構建內容
            contents = []
            if system_prompt:
                contents.append(system_prompt)
            contents.append(user_prompt)
            logger.debug(f"[{request.task_type}/{model_id}] Contents for AI model prepared for text request.")
            
            # 獲取生成配置
            generation_config = unified_ai_config.get_generation_config(
                request.task_type, request.custom_generation_params
            )
            safety_settings = unified_ai_config.get_safety_settings(request.task_type)
            logger.debug(f"[{request.task_type}/{model_id}] Generation config and safety settings obtained for text request.")
            
            logger.info(f"[{request.task_type}/{model_id}] 使用模型 {model_id} 處理文本請求. Calling generate_content_async.")
            
            # 調用AI模型
            response = await model.generate_content_async(
                contents,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            logger.info(f"[{request.task_type}/{model_id}] model.generate_content_async completed for text request.")
            logger.debug(f"[{request.task_type}/{model_id}] Raw AI Response object (text request): {response}")
            if response.candidates:
                logger.debug(f"[{request.task_type}/{model_id}] Response (text request) has {len(response.candidates)} candidates. First candidate finish_reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
            else:
                logger.warning(f"[{request.task_type}/{model_id}] Response (text request) has NO candidates.")
            if response.prompt_feedback:
                 logger.debug(f"[{request.task_type}/{model_id}] Response (text request) prompt_feedback: {response.prompt_feedback}")
            
            # 提取回應文本
            logger.info(f"[{request.task_type}/{model_id}] Calling _extract_response_text for text request.")
            generated_text = self._extract_response_text(response, model_id, "文本生成")
            logger.info(f"[{request.task_type}/{model_id}] _extract_response_text completed for text request. Extracted text (first 100 chars): '{generated_text[:100]}...' BARE ")

            # 新增：在嘗試Pydantic解析前，預先清理和轉義JSON字符串內容
            logger.debug(f"[{request.task_type}/{model_id}] Pre-cleaning generated_text before Pydantic validation (text request). Original (first 200 chars): {generated_text[:200]}")
            generated_text = self._pre_sanitize_json_string(generated_text, "文本生成", model_id)
            logger.debug(f"[{request.task_type}/{model_id}] Post-sanitization (text request) (first 200 chars): {generated_text[:200]}")
            
            model_content_for_response: Any # 用於 AIResponse 的 content

            if request.prompt_type == PromptType.QUERY_REWRITE:
                logger.info(f"[{request.task_type}/{model_id}] Parsing output for QUERY_REWRITE as JSON dictionary.")
                try:
                    parsed_dict = json.loads(generated_text)
                    if not isinstance(parsed_dict, dict):
                        logger.error(f"[{request.task_type}/{model_id}] QUERY_REWRITE output parsed but is not a dictionary. Type: {type(parsed_dict)}. Falling back to text.")
                        model_content_for_response = generated_text # Fallback to raw text
                    else:
                        logger.info(f"[{request.task_type}/{model_id}] Successfully parsed QUERY_REWRITE output as dictionary.")
                        model_content_for_response = parsed_dict # 查詢重寫的 content 直接是解析後的 dict
                except json.JSONDecodeError as jde:
                    logger.error(f"[{request.task_type}/{model_id}] Failed to parse QUERY_REWRITE output as JSON: {jde}. Falling back to raw text.")
                    model_content_for_response = generated_text # Fallback to raw text
            
            elif request.prompt_type == PromptType.ANSWER_GENERATION: # 新增的處理分支
                logger.info(f"[{request.task_type}/{model_id}] Parsing output for ANSWER_GENERATION as JSON containing 'answer' key.")
                try:
                    parsed_json = json.loads(generated_text)
                    if isinstance(parsed_json, dict) and "answer" in parsed_json:
                        answer_str = parsed_json["answer"]
                        if isinstance(answer_str, str):
                            logger.info(f"[{request.task_type}/{model_id}] Successfully extracted 'answer' from JSON: {answer_str[:100]}...")
                            model_content_for_response = answer_str # AIResponse.content 將是答案字符串
                        else:
                            logger.error(f"[{request.task_type}/{model_id}] 'answer' field in JSON is not a string. Type: {type(answer_str)}. Falling back to raw text.")
                            model_content_for_response = generated_text # Fallback
                    else:
                        logger.error(f"[{request.task_type}/{model_id}] Failed to find 'answer' key in parsed JSON or parsed_json is not a dict. Parsed type: {type(parsed_json)}. Falling back to raw text.")
                        model_content_for_response = generated_text # Fallback
                except json.JSONDecodeError as jde:
                    logger.error(f"[{request.task_type}/{model_id}] Failed to parse ANSWER_GENERATION output as JSON: {jde}. Falling back to raw text.")
                    model_content_for_response = generated_text # Fallback
            
            else: # 其他文本分析任務，仍使用 AITextAnalysisOutput
                logger.info(f"[{request.task_type}/{model_id}] Parsing structured output for {request.prompt_type} with Pydantic AITextAnalysisOutput.")
                try:
                    parsed_output_model = AITextAnalysisOutput.model_validate_json(generated_text)
                    parsed_output_model.model_used = model_id
                    logger.info("成功解析為靈活結構格式 (AITextAnalysisOutput)")
                    model_content_for_response = parsed_output_model
                except ValidationError as ve:
                    logger.warning(f"靈活結構解析失敗 (AITextAnalysisOutput)，嘗試智能修復: {ve}")
                    repaired_successfully = False
                    try:
                        potential_key_info_dict = json.loads(generated_text)
                        if isinstance(potential_key_info_dict, dict) and \
                           not all(k in potential_key_info_dict for k in ["initial_summary", "content_type", "key_information", "intermediate_analysis"]):
                            
                            logger.info(f"[{request.task_type}/{model_id}] AI response seems to be a direct key_information payload. Attempting to wrap it into AITextAnalysisOutput.")

                            if "content_type" not in potential_key_info_dict:
                                potential_key_info_dict["content_type"] = "未知類型 (自動修復)"
                                logger.warning(f"[{request.task_type}/{model_id}] Missing 'content_type' in direct key_information payload, defaulted.")
                            
                            if "content_summary" not in potential_key_info_dict:
                                summary_candidate = potential_key_info_dict.get("intent_analysis", 
                                                                            potential_key_info_dict.get("description", 
                                                                                                        "內容摘要未提供 (自動修復)"))
                                potential_key_info_dict["content_summary"] = summary_candidate[:300]
                                logger.warning(f"[{request.task_type}/{model_id}] Missing 'content_summary' in direct key_information payload, defaulted using other fields.")

                            fki_instance = FlexibleKeyInformation(**potential_key_info_dict)
                            
                            initial_summary_for_output = fki_instance.content_summary
                            if not initial_summary_for_output or len(initial_summary_for_output.strip()) < 5:
                                if "intent_analysis" in potential_key_info_dict and isinstance(potential_key_info_dict["intent_analysis"], str):
                                    initial_summary_for_output = potential_key_info_dict["intent_analysis"]
                                elif "main_topic_or_title" in potential_key_info_dict and isinstance(potential_key_info_dict["main_topic_or_title"], str):
                                     initial_summary_for_output = potential_key_info_dict["main_topic_or_title"]
                                else:
                                     initial_summary_for_output = "分析結果需要修復 (自動包裝)"
                            
                            parsed_output_model = AITextAnalysisOutput(
                                initial_summary=initial_summary_for_output,
                                content_type=fki_instance.content_type or "未知類型 (自動包裝)",
                                intermediate_analysis=FlexibleIntermediateAnalysis(
                                    analysis_approach="自動包裝",
                                    key_observations=[],
                                    reasoning_steps=[],
                                    confidence_factors={}
                                ),
                                key_information=fki_instance,
                                model_used=model_id
                            )
                            logger.info(f"[{request.task_type}/{model_id}] Successfully wrapped direct key_information payload into AITextAnalysisOutput.")
                            repaired_successfully = True
                            model_content_for_response = parsed_output_model # Assign here
                        
                        if not repaired_successfully: # Ensure this is checked after the direct key_info attempt block
                            # This means it wasn't a direct key_information payload or the wrapping failed before assignment
                            logger.info(f"[{request.task_type}/{model_id}] Proceeding with _smart_repair_text_output as it was not a direct key_information or wrapping failed.")
                            parsed_output_model = self._smart_repair_text_output(generated_text, model_id, ve)
                            if not parsed_output_model.key_information:
                                parsed_output_model.key_information = FlexibleKeyInformation()
                            model_content_for_response = parsed_output_model
                            # repaired_successfully = True # No longer needed here as we assign model_content_for_response

                    except Exception as repair_ex:
                        logger.error(f"智能修復過程中發生錯誤: {repair_ex}", exc_info=True)
                        parsed_output_model = self._emergency_repair_text_output(generated_text, model_id, ve)
                        if not parsed_output_model.key_information:
                                parsed_output_model.key_information = FlexibleKeyInformation()
                        model_content_for_response = parsed_output_model
                    
                    # Ensure model_content_for_response is assigned if an exception occurred above
                    # and it fell through the initial try for AITextAnalysisOutput.model_validate_json
                    if 'model_content_for_response' not in locals():
                        logger.error("Critical: model_content_for_response not assigned after Pydantic validation and repair attempts. Using minimal output.")
                        model_content_for_response = self._create_minimal_text_output(generated_text, model_id, ve)

            # 計算Token用量
            token_usage = await self._calculate_token_usage(model, contents, generated_text)
            
            processing_time = time.time() - start_time
            
            return AIResponse(
                success=True,
                content=model_content_for_response, 
                token_usage=token_usage,
                model_used=model_id,
                processing_time=processing_time
            )
        
        except Exception as e:
            logger.error(f"文本請求處理失敗: {e}")
            return self._create_error_response(
                request.task_type,
                str(e),
                0,
                time.time() - start_time,
                model_id
            )
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _process_image_request(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        request: AIRequest,
        start_time: float
    ) -> AIResponse:
        """處理圖片分析請求 - 簡化版本"""
        logger.info(f"[{request.task_type}/{model_id}] Entering _process_image_request. Attempt: {self._process_image_request.retry.statistics.get('attempt_number', 1) if hasattr(self._process_image_request, 'retry') else 'N/A'}")
        try:
            model = genai.GenerativeModel(model_id)
            
            # 處理圖片
            try:
                logger.debug(f"[{request.task_type}/{model_id}] Opening image from bytes.")
                image_pil = Image.open(io.BytesIO(request.content))
                logger.debug(f"[{request.task_type}/{model_id}] Image opened successfully.")
            except Exception as img_err:
                logger.error(f"[{request.task_type}/{model_id}] 無法打開圖片: {img_err}")
                raise ValueError(f"圖片數據無效: {img_err}")
            
            # 構建內容
            contents = [system_prompt, image_pil]
            logger.debug(f"[{request.task_type}/{model_id}] Contents for AI model prepared.")
            
            # 獲取生成配置
            generation_config = unified_ai_config.get_generation_config(
                request.task_type, request.custom_generation_params
            )
            safety_settings = unified_ai_config.get_safety_settings(request.task_type)
            logger.debug(f"[{request.task_type}/{model_id}] Generation config and safety settings obtained.")
            
            logger.info(f"[{request.task_type}/{model_id}] 使用模型 {model_id} 處理圖片分析請求. Calling generate_content_async.")
            
            # 調用AI模型
            response = await model.generate_content_async(
                contents,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            logger.info(f"[{request.task_type}/{model_id}] model.generate_content_async completed.")
            logger.debug(f"[{request.task_type}/{model_id}] Raw AI Response object: {response}") # 記錄原始響應對象的簡要信息
            if response.candidates:
                logger.debug(f"[{request.task_type}/{model_id}] Response has {len(response.candidates)} candidates. First candidate finish_reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
            else:
                logger.warning(f"[{request.task_type}/{model_id}] Response has NO candidates.")
            if response.prompt_feedback:
                 logger.debug(f"[{request.task_type}/{model_id}] Response prompt_feedback: {response.prompt_feedback}")
            
            # 提取回應文本
            logger.info(f"[{request.task_type}/{model_id}] Calling _extract_response_text.")
            generated_text = self._extract_response_text(response, model_id, "圖片分析")
            logger.info(f"[{request.task_type}/{model_id}] _extract_response_text completed. Extracted text (first 100 chars): '{generated_text[:100]}...' BARE ")
            
            # 新增：在嘗試Pydantic解析前，預先清理和轉義JSON字符串內容
            logger.debug(f"[{request.task_type}/{model_id}] Pre-cleaning generated_text before Pydantic validation. Original (first 200 chars): {generated_text[:200]}")
            generated_text = self._pre_sanitize_json_string(generated_text, "圖片分析", model_id)
            logger.debug(f"[{request.task_type}/{model_id}] Post-sanitization (first 200 chars): {generated_text[:200]}")
            
            # 解析結構化輸出 - 統一使用靈活結構
            logger.info(f"[{request.task_type}/{model_id}] Parsing structured output with Pydantic.")
            try:
                parsed_output = AIImageAnalysisOutput.model_validate_json(generated_text)
                parsed_output.model_used = model_id
                logger.info("成功解析為靈活結構格式")
            except ValidationError as ve:
                logger.warning(f"靈活結構解析失敗，嘗試智能修復: {ve}")
                parsed_output = self._smart_repair_image_output(generated_text, model_id, ve)
            
            # 計算Token使用量
            token_usage = await self._calculate_token_usage(
                model, contents, generated_text
            )
            
            processing_time = time.time() - start_time
            
            return AIResponse(
                success=True,
                content=parsed_output,
                token_usage=token_usage,
                model_used=model_id,
                processing_time=processing_time
            )
        
        except Exception as e:
            logger.error(f"圖片請求處理失敗: {e}")
            return self._create_error_response(
                request.task_type,
                str(e),
                0,
                time.time() - start_time,
                model_id
            )
    
    def _smart_repair_text_output(self, generated_text: str, model_id: str, validation_error: ValidationError) -> AITextAnalysisOutput:
        """智能修復文本分析輸出 - 增強版本"""
        try:
            # 嘗試清理和解析JSON
            cleaned_text = self._clean_json_text(generated_text)
            parsed_json = json.loads(cleaned_text)
            
            # 智能修復靈活結構
            repaired_json = self._repair_flexible_structure(parsed_json, "text")
            
            return AITextAnalysisOutput(**repaired_json)
            
        except Exception as repair_error:
            logger.error(f"文本智能修復失敗: {repair_error}")
            # 如果JSON修復失敗，使用緊急修復策略
            return self._emergency_repair_text_output(generated_text, model_id, validation_error)
    
    def _emergency_repair_text_output(self, generated_text: str, model_id: str, validation_error: ValidationError) -> AITextAnalysisOutput:
        """緊急修復策略：文本分析版本"""
        logger.warning("使用緊急修復策略處理嚴重損壞的文本分析JSON")
        
        # 嘗試從破損的JSON中提取有用信息
        extracted_info = self._extract_info_from_broken_json(generated_text)
        
        # 創建基於靈活結構的修復結果
        repaired_key_info = {
            "content_type": extracted_info.get("content_type", "JSON解析失敗的文本"),
            "content_summary": extracted_info.get("description", f"AI分析失敗，原始回應長度: {len(generated_text)}"),
            "semantic_tags": ["JSON錯誤", "需要重新分析"],
            "searchable_keywords": ["json_error", "parse_failed"],
            "knowledge_domains": ["錯誤處理"],
            "dynamic_fields": {
                "original_response_fragment": generated_text[:200],
                "error_type": "JSON解析失敗",
                "recovery_method": "緊急修復"
            },
            "confidence_level": "low",
            "quality_assessment": "緊急修復結果",
            "processing_notes": f"原始ValidationError: {str(validation_error)[:100]}"
        }
        
        return AITextAnalysisOutput(
            initial_summary=extracted_info.get("description", f"AI回應解析失敗。原始回應: {generated_text[:150]}..."),
            content_type="Error/EmergencyRepair",
            intermediate_analysis={
                "analysis_approach": "緊急修復",
                "key_observations": ["JSON格式嚴重損壞"],
                "reasoning_steps": [{
                    "step": "緊急處理",
                    "reasoning": "所有標準修復方法都失敗",
                    "evidence": f"ValidationError: {str(validation_error)[:50]}"
                }],
                "confidence_factors": {"uncertainty": "緊急修復，可信度極低"}
            },
            key_information=repaired_key_info,
            model_used=model_id,
            error_message=f"JSON解析失敗，已使用緊急修復: {str(validation_error)[:100]}"
        )
    
    def _smart_repair_image_output(self, generated_text: str, model_id: str, validation_error: ValidationError) -> AIImageAnalysisOutput:
        """智能修復圖片分析輸出 - 增強版本"""
        try:
            # 嘗試清理和解析JSON
            cleaned_text = self._clean_json_text(generated_text)
            parsed_json = json.loads(cleaned_text)
            
            # 智能修復靈活結構
            repaired_json = self._repair_flexible_structure(parsed_json, "image")
            
            return AIImageAnalysisOutput(**repaired_json)
            
        except Exception as repair_error:
            logger.error(f"智能修復失敗: {repair_error}")
            # 如果JSON修復失敗，使用緊急修復策略
            return self._emergency_repair_image_output(generated_text, model_id, validation_error)
    
    def _emergency_repair_image_output(self, generated_text: str, model_id: str, validation_error: ValidationError) -> AIImageAnalysisOutput:
        """緊急修復策略：當所有JSON修復都失敗時使用"""
        logger.warning("使用緊急修復策略處理嚴重損壞的JSON")
        
        # 嘗試從破損的JSON中提取有用信息
        extracted_info = self._extract_info_from_broken_json(generated_text)
        
        # 創建基於靈活結構的修復結果
        repaired_key_info = {
            "content_type": extracted_info.get("content_type", "JSON解析失敗的圖片"),
            "content_summary": extracted_info.get("description", f"AI分析失敗，原始回應長度: {len(generated_text)}"),
            "semantic_tags": ["JSON錯誤", "需要重新分析"],
            "searchable_keywords": ["json_error", "parse_failed"],
            "knowledge_domains": ["錯誤處理"],
            "dynamic_fields": {
                "original_response_fragment": generated_text[:200],
                "error_type": "JSON解析失敗",
                "recovery_method": "緊急修復",
                "extracted_text_fragment": extracted_info.get("extracted_text", "無法提取")[:100]
            },
            "confidence_level": "low",
            "quality_assessment": "緊急修復結果",
            "processing_notes": f"原始ValidationError: {str(validation_error)[:100]}"
        }
        
        return AIImageAnalysisOutput(
            initial_description=extracted_info.get("description", f"AI回應解析失敗。原始回應: {generated_text[:150]}..."),
            extracted_text=extracted_info.get("extracted_text"),
            content_type="Error/EmergencyRepair",
            intermediate_analysis={
                "analysis_approach": "緊急修復",
                "key_observations": ["JSON格式嚴重損壞"],
                "reasoning_steps": [{
                    "step": "緊急處理",
                    "reasoning": "所有標準修復方法都失敗",
                    "evidence": f"ValidationError: {str(validation_error)[:50]}"
                }],
                "confidence_factors": {"uncertainty": "緊急修復，可信度極低"}
            },
            key_information=repaired_key_info,
            model_used=model_id,
            error_message=f"JSON解析失敗，已使用緊急修復: {str(validation_error)[:100]}"
        )
    
    def _extract_info_from_broken_json(self, text: str) -> Dict[str, str]:
        """從破損的JSON中提取可用信息"""
        import re
        
        extracted = {}
        
        # 嘗試提取描述
        desc_patterns = [
            r'"initial_description":\s*"([^"]*)"',
            r'"description":\s*"([^"]*)"',
            r'"initial_summary":\s*"([^"]*)"'
        ]
        for pattern in desc_patterns:
            match = re.search(pattern, text)
            if match:
                extracted["description"] = match.group(1)
                break
        
        # 嘗試提取extracted_text
        text_patterns = [
            r'"extracted_text":\s*"([^"]*)"',
            r'"text_content":\s*"([^"]*)"'
        ]
        for pattern in text_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                # 取前300字符，避免過長
                extracted["extracted_text"] = match.group(1)[:300]
                break
        
        # 嘗試提取內容類型
        type_patterns = [
            r'"content_type":\s*"([^"]*)"',
            r'"type":\s*"([^"]*)"'
        ]
        for pattern in type_patterns:
            match = re.search(pattern, text)
            if match:
                extracted["content_type"] = match.group(1)
                break
        
        return extracted
    
    def _clean_json_text(self, text: str) -> str:
        """增強的JSON文本清理和修復機制"""
        import re
        
        logger.debug(f"Entering _clean_json_text. Original text (first 300): {text[:300]}...")
        cleaned = text.strip()
        
        # 0. 預處理：確保基本的字符串轉義 (調用 _pre_sanitize_json_string)
        # 這一步應該在 Pydantic 驗證之前完成，但如果在智能修復流程中再次調用 clean_json_text，
        # 確保字符串內容的清潔仍然是好的。
        # 然而，重覆調用可能導致過度轉義或佔位符問題，需小心。
        # 鑑於 _pre_sanitize_json_string 已經在 _process_image/text_request 中調用，
        # 這裡我們可以選擇性地再次調用，或者假設它已經處理了基本的字符串內容轉義。
        # 為避免複雜性，暫時不在這裡重覆調用 _pre_sanitize_json_string，
        # 假設它主要解決控制字符問題，而 _clean_json_text 專注於結構問題。
        # cleaned = self._pre_sanitize_json_string(cleaned)
        
        # 1. 找到JSON大致邊界 (嘗試去除前後無用的字符)
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        
        # 備用：如果找不到 '{' 和 '}'，嘗試 '[' 和 ']'
        # Try to use {} boundaries first
        if not (start_idx == -1 or end_idx == -1 or end_idx < start_idx):
            cleaned = cleaned[start_idx:end_idx+1]
        else:
            # {} were not found or invalid, try []
            start_idx_arr = cleaned.find('[')
            end_idx_arr = cleaned.rfind(']')
            if start_idx_arr != -1 and end_idx_arr != -1 and end_idx_arr > start_idx_arr:
                logger.debug("JSON seems to be an array, using [ and ] for boundary.")
                # Use array boundaries for slicing
                cleaned = cleaned[start_idx_arr:end_idx_arr+1]
            else:
                # Neither {} nor [] found or valid. Log and do not slice.
                logger.warning("Could not find valid JSON object {} or array [] boundaries.")
                # 'cleaned' remains unchanged by this boundary logic
        
        # 2. 修復常見的JSON結構問題 (重複幾次以處理嵌套問題或連鎖效應)
        for i in range(3): # 迭代修復，例如移除多餘逗號後可能導致新的懸空逗號
            original_cleaned_before_pass = cleaned
            logger.debug(f"Clean pass {i+1}. Text before pass (first 300): {cleaned[:300]}")
            
            # 2a. 移除尾隨逗號 (在物件和陣列末尾)
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned) # \1 引用第一個捕獲組 (} or ])
            
            # 2b. 修復鍵之後缺少值的情況 (例如 "key": , 或 "key": })
            cleaned = re.sub(r'(\"[^\"\\\\]*(?:\\\\.[^\"\\\\]*)*\")\s*:\s*(?=[,}\]])', r'\1: null', cleaned)
            
            # 2c. 嘗試處理 "key": (然後是EOF) 的情況
            match_dangling_key = re.search(r'(\"[^\"\\\\]*(?:\\\\.[^\"\\\\]*)*\")\s*:\s*$', cleaned.strip())
            if match_dangling_key:
                logger.warning(f"Detected dangling key at the end: {match_dangling_key.group(1)}. Appending 'null'.")
                cleaned = cleaned.strip() + "null"
            
            # 2d. 再次移除可能由上一步修復引入的尾隨逗號 (例如 "key": null, })
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
            
            # 2f. 修復缺少逗號的情況 (例如 "value1" "value2" -> "value1", "value2")
            cleaned = re.sub(r'(?<=[a-zA-Z0-9}\]])\"\\s*\"(?=[a-zA-Z0-9{])', r'\",\"', cleaned)
            
            if cleaned == original_cleaned_before_pass:
                logger.debug(f"Clean pass {i+1} made no changes, breaking early.")
                break # 如果一輪沒有變化，提前結束迭代
            else:
                logger.debug(f"Clean pass {i+1} made changes. Text after pass: {cleaned[:300]}")
        
        # 3. 平衡括號 (確保所有開啟的 {, [, 都已關閉)
        open_braces = cleaned.count('{')
        close_braces = cleaned.count('}')
        open_brackets = cleaned.count('[')
        close_brackets = cleaned.count(']')
        
        if open_braces > close_braces:
            cleaned += '}' * (open_braces - close_braces)
            logger.debug(f"Added {open_braces - close_braces} missing closing braces '}}'.")
        elif close_braces > open_braces:
            # 如果關閉的比開啟的多，通常是更嚴重的結構問題，可能前面移除了不該移除的
            logger.warning(f"More closing braces ('}}') than opening ones ({close_braces} > {open_braces}). JSON might be malformed.")
        
        if open_brackets > close_brackets:
            cleaned += ']' * (open_brackets - close_brackets)
            logger.debug(f"Added {open_brackets - close_brackets} missing closing brackets ']'.")
        elif close_brackets > open_brackets:
            logger.warning(f"More closing brackets (']') than opening ones ({close_brackets} > {open_brackets}). JSON might be malformed.")
        
        # 4. 最後嘗試確保它至少以 { 或 [ 開頭並以 } 或 ] 結尾 (如果它是對象或數組)
        #    這一部分比較粗略，之前的邊界檢測更精準
        # if not cleaned.startswith( ('{', '[') ) and cleaned.endswith( ('}', ']') ):
            # pass # 避免錯誤地添加，依賴之前的邊界檢測
        
        logger.debug(f"Exiting _clean_json_text. Final cleaned text (first 300): {cleaned[:300]}...")
        return cleaned
    
    def _repair_flexible_structure(self, parsed_json: Dict, analysis_type: str) -> Dict:
        """修復為靈活結構格式"""
        
        # 確保基本欄位存在
        if analysis_type == "image":
            base_fields = {
                'initial_description': parsed_json.get('initial_description', '分析結果需要修復'),
                'extracted_text': parsed_json.get('extracted_text', None),
                'content_type': parsed_json.get('content_type', '未分類內容'),
            }
        else:  # text
            base_fields = {
                'initial_summary': parsed_json.get('initial_summary', '分析結果需要修復'),
                'content_type': parsed_json.get('content_type', '未分類內容'),
            }
        
        # 修復intermediate_analysis為靈活結構
        intermediate = parsed_json.get('intermediate_analysis', {})
        if isinstance(intermediate, str):
            intermediate = {
                "analysis_approach": "字符串內容自動修復",
                "key_observations": [intermediate[:200] if len(intermediate) > 200 else intermediate],
                "reasoning_steps": [{
                    "step": "格式修復",
                    "reasoning": "原始內容為字符串格式",
                    "evidence": "自動轉換處理"
                }],
                "confidence_factors": {"uncertainty": "格式修復後的結果"}
            }
        elif isinstance(intermediate, list):
            # 如果是舊的列表格式，轉換為靈活結構
            intermediate = {
                "analysis_approach": "列表格式轉換",
                "key_observations": [item.get('text_fragment', '') for item in intermediate if isinstance(item, dict)],
                "reasoning_steps": [{
                    "step": item.get('potential_field', '未知步驟'),
                    "reasoning": item.get('reasoning', '無推理說明'),
                    "evidence": item.get('text_fragment', '無證據')
                } for item in intermediate if isinstance(item, dict)],
                "confidence_factors": {"uncertainty": "從舊格式轉換"}
            }
        
        base_fields['intermediate_analysis'] = intermediate
        
        # 修復key_information為靈活結構
        key_info = parsed_json.get('key_information', {})
        flexible_key_info = self._convert_to_flexible_key_info(key_info, parsed_json)
        base_fields['key_information'] = flexible_key_info
        
        # 添加模型信息
        base_fields['model_used'] = parsed_json.get('model_used', 'unknown')
        base_fields['error_message'] = f"格式已智能修復並轉換為靈活結構"
        
        return base_fields
    
    def _convert_to_flexible_key_info(self, key_info: Dict, full_json: Dict) -> Dict:
        """將任何格式的key_information轉換為靈活結構"""
        
        flexible = {
            # 核心必填欄位
            "content_type": key_info.get('content_type') or full_json.get('content_type', '未知類型'),
            "content_summary": (
                key_info.get('content_summary') or 
                full_json.get('initial_description', '') or 
                full_json.get('initial_summary', '')
            )[:200],  # 限制長度
            
            # 語意搜索優化欄位
            "semantic_tags": key_info.get('semantic_tags', []) or [],
            "searchable_keywords": key_info.get('searchable_keywords', []) or [],
            "knowledge_domains": key_info.get('knowledge_domains', []) or [],
            
            # 智能選填欄位
            "extracted_entities": key_info.get('extracted_entities'),
            "main_topics": key_info.get('main_topics'),
            "key_concepts": key_info.get('key_concepts'),
            "action_items": key_info.get('action_items'),
            "dates_mentioned": key_info.get('dates_mentioned'),
            "amounts_mentioned": key_info.get('amounts_mentioned'),
            
            # 內容特性欄位
            "document_purpose": key_info.get('document_purpose'),
            "note_structure": key_info.get('note_structure'),
            "thinking_patterns": key_info.get('thinking_patterns'),
            "business_context": key_info.get('business_context'),
            "legal_context": key_info.get('legal_context'),
            
            # 動態欄位 - 收集所有其他信息
            "dynamic_fields": self._collect_dynamic_fields(key_info),
            
            # 分析品質指標
            "confidence_level": key_info.get('confidence_level', 'medium'),
            "quality_assessment": key_info.get('quality_assessment', '智能修復'),
            "processing_notes": key_info.get('processing_notes', '已轉換為靈活結構格式')
        }
        
        return flexible
    
    def _collect_dynamic_fields(self, key_info: Dict) -> Dict[str, Any]:
        """收集動態欄位"""
        # 預設欄位列表
        predefined_fields = {
            'content_type', 'content_summary', 'semantic_tags', 'searchable_keywords',
            'knowledge_domains', 'extracted_entities', 'main_topics', 'key_concepts',
            'action_items', 'dates_mentioned', 'amounts_mentioned', 'document_purpose',
            'note_structure', 'thinking_patterns', 'business_context', 'legal_context',
            'confidence_level', 'quality_assessment', 'processing_notes'
        }
        
        dynamic_fields = {}
        for key, value in key_info.items():
            if key not in predefined_fields and value is not None:
                dynamic_fields[key] = value
        
        return dynamic_fields
    
    def _create_minimal_text_output(self, generated_text: str, model_id: str, error: ValidationError) -> AITextAnalysisOutput:
        """創建最小化的文本分析輸出"""
        return AITextAnalysisOutput(
            initial_summary=f"分析失敗，原始回應: {generated_text[:150]}...",
            content_type="Error/ParseFailed",
            intermediate_analysis={
                "analysis_approach": "錯誤處理",
                "key_observations": ["JSON解析失敗"],
                "reasoning_steps": [],
                "confidence_factors": {"uncertainty": "解析錯誤"}
            },
            key_information={
                "content_type": "Error/ParseFailed",
                "content_summary": "AI回應解析失敗",
                "semantic_tags": ["錯誤", "解析失敗"],
                "searchable_keywords": ["error", "parse_failed"],
                "knowledge_domains": [],
                "dynamic_fields": {"original_response": generated_text[:100]},
                "confidence_level": "low",
                "quality_assessment": "解析失敗",
                "processing_notes": f"ValidationError: {str(error)[:100]}"
            },
            model_used=model_id,
            error_message=f"JSON解析失敗: {str(error)[:100]}"
        )
    
    def _create_minimal_image_output(self, generated_text: str, model_id: str, error: ValidationError) -> AIImageAnalysisOutput:
        """創建最小化的圖片分析輸出"""
        return AIImageAnalysisOutput(
            initial_description=f"分析失敗，原始回應: {generated_text[:150]}...",
            extracted_text=None,
            content_type="Error/ParseFailed",
            intermediate_analysis={
                "analysis_approach": "錯誤處理",
                "key_observations": ["JSON解析失敗"],
                "reasoning_steps": [],
                "confidence_factors": {"uncertainty": "解析錯誤"}
            },
            key_information={
                "content_type": "Error/ParseFailed",
                "content_summary": "AI回應解析失敗",
                "semantic_tags": ["錯誤", "解析失敗"],
                "searchable_keywords": ["error", "parse_failed"],
                "knowledge_domains": [],
                "dynamic_fields": {"original_response": generated_text[:100]},
                "confidence_level": "low",
                "quality_assessment": "解析失敗",
                "processing_notes": f"ValidationError: {str(error)[:100]}"
            },
            model_used=model_id,
            error_message=f"JSON解析失敗: {str(error)[:100]}"
        )
    
    def _extract_response_text(self, response: genai.types.GenerateContentResponse, model_id: str, task_name: str) -> str:
        try:
            logger.error(f"!!! LOUD ENTRY _extract_response_text for {task_name}/{model_id}. Response type: {type(response)} !!!")

            if not hasattr(response, 'candidates'):
                logger.error(f"!!! LOUD _extract_response_text: Response object for {task_name}/{model_id} has NO 'candidates' attribute.")
                return "ERROR_RESPONSE_HAS_NO_CANDIDATES_ATTRIBUTE"

            if not response.candidates: # Checks if the list is empty or None
                logger.error(f"!!! LOUD _extract_response_text: 'candidates' list is empty or None for {task_name}/{model_id}.")
                prompt_feedback_msg = "No prompt_feedback found."
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    prompt_feedback_msg = f"Prompt feedback: {response.prompt_feedback}"
                logger.warning(f"[{task_name}/{model_id}] {prompt_feedback_msg} for empty/None candidates.")
                return "ERROR_CANDIDATES_LIST_IS_EMPTY_OR_NONE"
            
            logger.error(f"!!! LOUD _extract_response_text: Processing {len(response.candidates)} candidates for {task_name}/{model_id}.")
            
            all_parts_text = []
            candidate_idx = 0
            for candidate in response.candidates:
                logger.error(f"!!! LOUD Processing candidate {candidate_idx} for {task_name}/{model_id}. Candidate type: {type(candidate)}")
                
                candidate_text_parts = []
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                    part_idx = 0
                    for part in candidate.content.parts:
                        logger.error(f"!!! LOUD Processing part {part_idx} of candidate {candidate_idx}. Part type: {type(part)}")
                        if hasattr(part, "text") and part.text is not None:
                            candidate_text_parts.append(part.text)
                            logger.error(f"!!! LOUD Appended text from part {part_idx} of cand {candidate_idx}. Length: {len(part.text)}. Text (first 70): {part.text[:70]}")
                        else:
                            logger.warning(f"[{task_name}/{model_id}] Part {part_idx} of cand {candidate_idx} has no text attribute or text is None.")
                        part_idx += 1
                else:
                    logger.warning(f"[{task_name}/{model_id}] Candidate {candidate_idx} (type: {type(candidate)}) has no 'content', or 'content.parts' is missing/empty.")

                finish_reason_str = "NOT_AVAILABLE"
                if hasattr(candidate, 'finish_reason') and candidate.finish_reason:
                    try:
                        reason_name = candidate.finish_reason.name
                        reason_value = candidate.finish_reason.value
                        finish_reason_str = f"{reason_name} ({reason_value})"
                        logger.error(f"!!! LOUD [{task_name}/{model_id}] Cand {candidate_idx} FINISH_REASON: {finish_reason_str} !!!")
                        if reason_name == "MAX_TOKENS":
                            logger.warning(f"[{task_name}/{model_id}] Cand {candidate_idx} FINISHED DUE TO MAX_TOKENS.")
                        elif reason_name in ["SAFETY", "RECITATION", "OTHER"]:
                             logger.warning(f"[{task_name}/{model_id}] Cand {candidate_idx} finished due to {reason_name}.")
                    except Exception as e_fr:
                        logger.error(f"!!! LOUD Error accessing finish_reason details for cand {candidate_idx}: {type(e_fr).__name__} - {e_fr}")
                        finish_reason_str = f"ERROR_ACCESSING_FINISH_REASON ({type(e_fr).__name__})"
                else:
                    logger.error(f"!!! LOUD [{task_name}/{model_id}] Cand {candidate_idx} has no 'finish_reason' attribute or it's None.")
                
                all_parts_text.extend(candidate_text_parts)
                candidate_idx += 1
            
            final_generated_text = "".join(all_parts_text)
            logger.error(f"!!! LOUD _extract_response_text for {task_name}/{model_id} RETURNING text (first 100): {final_generated_text[:100]}")
            return final_generated_text

        except Exception as e_extract:
            logger.error(f"!!! LOUD CRITICAL EXCEPTION in _extract_response_text for {task_name}/{model_id}: {type(e_extract).__name__} - {e_extract} !!!", exc_info=True)
            return f"ERROR_IN_EXTRACT_RESPONSE_TEXT__{type(e_extract).__name__}"
    
    def _pre_sanitize_json_string(self, text: str, task_name: str, model_id: str) -> str:
        logger.error(f"!!! LOUD ENTERING _pre_sanitize_json_string for {task_name}/{model_id}. Input text (first 100): {text[:100]}")
        
        if not isinstance(text, str):
            logger.error(f"!!! LOUD _pre_sanitize: Input text is not a string, it's {type(text)}. Returning original.")
            return text # Or handle error appropriately

        original_text_for_logging = text[:300] # Log a snippet for before and after
        
        stripped_text = text.strip()
        modified_prefix_suffix = False

        if stripped_text.startswith("```json"):
            stripped_text = stripped_text[7:] # Remove ```json
            logger.error(f"!!! LOUD _pre_sanitize: Stripped leading '```json'. Text now (first 100): {stripped_text[:100]}")
            modified_prefix_suffix = True
        elif stripped_text.startswith("```"):
            stripped_text = stripped_text[3:] # Remove ```
            logger.error(f"!!! LOUD _pre_sanitize: Stripped leading '```'. Text now (first 100): {stripped_text[:100]}")
            modified_prefix_suffix = True
        
        # Ensure it's stripped again before checking endswith, in case of internal newlines
        current_stripped_for_suffix = stripped_text.strip()
        if current_stripped_for_suffix.endswith("```"):
            # Remove trailing ``` and then strip any whitespace that might have been before it
            stripped_text = current_stripped_for_suffix[:-3].strip() 
            logger.error(f"!!! LOUD _pre_sanitize: Stripped trailing '```'. Text now (first 100): {stripped_text[:100]}")
            modified_prefix_suffix = True
        else:
            # If no specific ``` suffix, ensure the text is at least stripped from outer whitespace
            stripped_text = current_stripped_for_suffix


        # Other cleaning steps (like newline replacement, specific regex for full block)
        # are currently omitted to focus on prefix/suffix stripping.
        # The regex re.match(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", text, re.DOTALL | re.IGNORECASE)
        # would be good if the block is complete, but fails on truncation.
        # The current prefix/suffix stripping is more direct for truncated cases.

        text_to_return = stripped_text
        
        # Log if any significant modification occurred based on the prefix/suffix stripping or overall stripping.
        # Compare with the initial `text.strip()` vs final `text_to_return.strip()`
        if text.strip() != text_to_return.strip(): # A more general check if any stripping happened
             logger.error(f"!!! LOUD _pre_sanitize_json_string MODIFIED text for {task_name}/{model_id}. Result (first 100): {text_to_return[:100]}")
        else:
             logger.error(f"!!! LOUD _pre_sanitize_json_string DID NOT significantly modify text for {task_name}/{model_id}. Output (first 100): {text_to_return[:100]}")
        
        return text_to_return
    
    async def _calculate_token_usage(
        self, 
        model, 
        contents: List[Any], 
        generated_text: str
    ) -> TokenUsage:
        """計算Token使用量"""
        try:
            # 計算輸入Token
            prompt_tokens_response = await model.count_tokens_async(contents)
            prompt_tokens = prompt_tokens_response.total_tokens
            
            # 計算輸出Token
            completion_tokens_response = await model.count_tokens_async(generated_text)
            completion_tokens = completion_tokens_response.total_tokens
            
            return TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        
        except Exception as e:
            logger.error(f"計算Token使用量失敗: {e}")
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    
    def _create_error_response(
        self,
        task_type: TaskType,
        error_message: str,
        total_tokens: int,
        processing_time: float,
        model_used: str = "unknown"
    ) -> AIResponse:
        """創建錯誤響應"""
        if task_type == TaskType.TEXT_GENERATION:
            error_content = AITextAnalysisOutput(
                initial_summary=f"處理失敗: {error_message}",
                content_type="Error/Processing",
                intermediate_analysis={
                    "analysis_approach": "錯誤處理",
                    "key_observations": [error_message],
                    "reasoning_steps": [],
                    "confidence_factors": {"uncertainty": "處理失敗"}
                },
                key_information={
                    "content_type": "Error/Processing",
                    "content_summary": error_message,
                    "semantic_tags": ["錯誤"],
                    "searchable_keywords": ["error"],
                    "knowledge_domains": [],
                    "dynamic_fields": {},
                    "confidence_level": "low",
                    "quality_assessment": "處理失敗",
                    "processing_notes": error_message
                },
                model_used=model_used,
                error_message=error_message
            )
        else:  # IMAGE_ANALYSIS
            error_content = AIImageAnalysisOutput(
                initial_description=f"處理失敗: {error_message}",
                extracted_text=None,
                content_type="Error/Processing",
                intermediate_analysis={
                    "analysis_approach": "錯誤處理",
                    "key_observations": [error_message],
                    "reasoning_steps": [],
                    "confidence_factors": {"uncertainty": "處理失敗"}
                },
                key_information={
                    "content_type": "Error/Processing",
                    "content_summary": error_message,
                    "semantic_tags": ["錯誤"],
                    "searchable_keywords": ["error"],
                    "knowledge_domains": [],
                    "dynamic_fields": {},
                    "confidence_level": "low",
                    "quality_assessment": "處理失敗",
                    "processing_notes": error_message
                },
                model_used=model_used,
                error_message=error_message
            )
        
        return AIResponse(
            success=False,
            content=error_content,
            token_usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=total_tokens),
            model_used=model_used,
            processing_time=processing_time,
            error_message=error_message
        )
    
    # 便利方法
    async def analyze_text(
        self,
        text_content: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None,
        force_stable: bool = True,
        ensure_chinese_output: bool = True
    ) -> AIResponse:
        """分析文本內容"""
        request = AIRequest(
            task_type=TaskType.TEXT_GENERATION,
            prompt_type=PromptType.TEXT_ANALYSIS,
            content=text_content,
            variables={"text_content": text_content},
            model_preference=model_preference,
            force_stable_model=force_stable,
            require_language_consistency=ensure_chinese_output
        )
        return await self.process_request(request, db)
    
    async def analyze_image(
        self,
        image_data: bytes,
        image_mime_type: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None,
        force_stable: bool = True,
        ensure_chinese_output: bool = True
    ) -> AIResponse:
        """分析圖片內容"""
        request = AIRequest(
            task_type=TaskType.IMAGE_ANALYSIS,
            prompt_type=PromptType.IMAGE_ANALYSIS,
            content=image_data,
            variables={"image_mime_type": image_mime_type},
            model_preference=model_preference,
            mime_type=image_mime_type,
            force_stable_model=force_stable,
            require_language_consistency=ensure_chinese_output
        )
        return await self.process_request(request, db)
    
    async def rewrite_query(
        self,
        original_query: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None,
        force_stable: bool = True
    ) -> AIResponse:
        """重寫查詢"""
        request = AIRequest(
            task_type=TaskType.TEXT_GENERATION,
            prompt_type=PromptType.QUERY_REWRITE,
            content=original_query,
            variables={"original_query": original_query},
            model_preference=model_preference,
            force_stable_model=force_stable,
            require_language_consistency=True
        )
        return await self.process_request(request, db)
    
    async def generate_answer(
        self,
        user_question: str,
        intent_analysis: str,
        document_context: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None,
        force_stable: bool = True
    ) -> AIResponse:
        """生成答案"""
        request = AIRequest(
            task_type=TaskType.TEXT_GENERATION,
            prompt_type=PromptType.ANSWER_GENERATION,
            content=user_question,
            variables={
                "user_question": user_question,
                "intent_analysis": intent_analysis,
                "document_context": document_context
            },
            model_preference=model_preference,
            force_stable_model=force_stable,
            require_language_consistency=True
        )
        return await self.process_request(request, db)

    # 新增方法：允許直接傳入 system 和 user prompts
    async def analyze_with_prompts_and_parse_json(
        self,
        system_prompt: str,
        user_prompt: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        model_preference: Optional[str] = None, # 允許指定模型偏好
        force_stable: bool = True, # 默認強制穩定模型
        custom_generation_params: Optional[Dict[str, Any]] = None, # 允許自定義生成參數
        # output_model_schema: Optional[Type[BaseModel]] = None # 暫時移除，因為我們依賴 AITextAnalysisOutput
    ) -> AIResponse:
        """使用指定的 system 和 user prompts 分析文本，並期望返回結構化JSON。"""
        start_time = time.time()
        task_type = TaskType.TEXT_GENERATION # 此方法專用於文本生成/分析

        try:
            if not settings.GOOGLE_API_KEY:
                return self._create_error_response(
                    task_type, "API Key未設定", 0, time.time() - start_time
                )

            # 選擇模型
            if force_stable:
                model_id = await unified_ai_config.get_stable_model_for_task(
                    task_type, force_stability_override=True
                )
            else:
                model_id = await unified_ai_config.get_preferred_model_for_task(
                    task_type, user_preference_override=model_preference
                )
            
            if not model_id:
                return self._create_error_response(
                    task_type, "未找到可用的AI模型", 0, time.time() - start_time
                )

            logger.info(f"選用模型 (analyze_with_prompts): {model_id} (穩定模式: {force_stable})")

            # 直接使用傳入的 system_prompt 和 user_prompt
            # 語言一致性應由調用方在準備 prompts 時處理，或在此處根據需要添加
            # (為簡化，此處不重複添加 language_instruction，假設調用方已處理或不需要)

            # 複用 _process_text_request 的核心邏輯，但傳入已準備好的 prompts
            # 構造一個最小化的 AIRequest 對象以傳遞必要的參數
            pseudo_request = AIRequest(
                task_type=task_type,
                prompt_type=PromptType.TEXT_ANALYSIS, # 或一個更通用的類型
                content=user_prompt, # content 欄位在此上下文中主要用於 token 計算等
                variables={}, # 因為 prompts 已格式化
                model_preference=model_preference,
                custom_generation_params=custom_generation_params,
                force_stable_model=force_stable,
                require_language_consistency=False # 假設調用方已處理語言
            )
            
            # 注意： _process_text_request 內部會再次構建 contents
            # 我們可以直接調用更底層的 AI 交互邏輯，或者讓 _process_text_request 處理
            # 為保持一致性和複用現有重試邏輯，我們仍調用 _process_text_request

            return await self._process_text_request(
                system_prompt=system_prompt, # 直接傳遞
                user_prompt=user_prompt,     # 直接傳遞
                model_id=model_id,
                request=pseudo_request,      # 傳遞構造的請求對象
                start_time=start_time
            )

        except Exception as e:
            logger.error(f"analyze_with_prompts_and_parse_json 失敗: {e}", exc_info=True)
            return self._create_error_response(
                task_type,
                f"處理請求時發生錯誤: {str(e)}",
                0,
                time.time() - start_time
            )

# 創建簡化的全局實例
unified_ai_service_simplified = UnifiedAIServiceSimplified() 