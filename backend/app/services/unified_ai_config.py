from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold
from dotenv import set_key, find_dotenv, load_dotenv
import os

from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# 這些函數從ai_config_service移植過來
DEFAULT_GOOGLE_AI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro", 
    "gemini-1.0-pro",
    "gemini-pro",
    "gemini-2.0-flash",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-pro-preview-05-06",
]

def _fetch_dynamic_google_models() -> Optional[List[str]]:
    """動態獲取可用的Google AI模型"""
    if not settings.GOOGLE_API_KEY:
        logger.info("GOOGLE_API_KEY is not configured. Cannot fetch dynamic Google AI models.")
        return None
    
    try:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        logger.info("Successfully configured Google AI for fetching models. Fetching models...")
        
        dynamic_models = []
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods and model.name.startswith("models/"):
                model_id = model.name.split("models/", 1)[-1]
                dynamic_models.append(model_id)
        
        if not dynamic_models:
            logger.warning("Dynamically fetched model list is empty. This might be unexpected.")
            return None
            
        logger.info(f"Successfully fetched dynamic Google AI models: {dynamic_models}")
        return sorted(list(set(dynamic_models)))
    except Exception as e:
        logger.error(f"Error fetching dynamic Google AI models: {e}", exc_info=True)
        return None

def get_google_ai_models() -> List[str]:
    """獲取Google AI模型列表"""
    logger.info("Attempting to get Google AI models list...")
    
    all_models_from_api = _fetch_dynamic_google_models()
    
    if all_models_from_api:
        preferred_models = []
        priority_order = [
            "gemini-2.5-pro-preview-05-06", "gemini-2.5-pro-preview-03-25", "gemini-2.5-pro-exp-03-25",
            "gemini-2.5-flash-preview-05-20", "gemini-2.5-flash-preview-04-17",
            "gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-2.0-flash-exp",
            "gemini-1.5-flash", "gemini-1.5-flash-002", "gemini-1.5-flash-001",
            "gemini-1.5-pro", "gemini-1.5-pro-002", "gemini-1.5-pro-001",
            "gemini-1.0-pro", "gemini-1.0-pro-vision-latest", "gemini-pro", "gemini-pro-vision",
        ]
        added_models = set()
        for model_name in priority_order:
            if model_name in all_models_from_api and model_name not in added_models:
                preferred_models.append(model_name)
                added_models.add(model_name)
        
        # Ensure models from DEFAULT_GOOGLE_AI_MODELS that are in the dynamic list are added
        for model in DEFAULT_GOOGLE_AI_MODELS:
            if model in all_models_from_api and model not in added_models:
                preferred_models.append(model)
                added_models.add(model)
        
        # Add any remaining models from DEFAULT_GOOGLE_AI_MODELS that were not in the dynamic list
        # but are defined in our defaults, ensuring they are available.
        for model in DEFAULT_GOOGLE_AI_MODELS:
            if model not in added_models:
                # We might want to check if these are *actually* available via a quick API call,
                # or trust our DEFAULT_GOOGLE_AI_MODELS list. For now, let's add them.
                # If they are not truly available, later calls using them will fail,
                # which is existing behavior for misconfigured models.
                # Or, only add them if all_models_from_api already contains *some* variant (e.g. preview)
                # For simplicity and to ensure user_global_preference for "gemini-2.5-flash" can be picked up
                # if it's in DEFAULT_GOOGLE_AI_MODELS even if not in dynamic list.
                preferred_models.append(model)
                added_models.add(model)
                logger.info(f"Added model '{model}' from DEFAULT_GOOGLE_AI_MODELS as it was not in the dynamic list or priority order but is a known default.")

        if preferred_models:
            logger.info(f"Using dynamically fetched and default Google AI models: {sorted(list(set(preferred_models)))}") # Sort and unique
            return sorted(list(set(preferred_models))) # Return unique sorted list
        else:
            logger.warning("Dynamic fetch succeeded but no preferred models found.")
            fallback_models = [model for model in all_models_from_api if model in DEFAULT_GOOGLE_AI_MODELS]
            if fallback_models:
                logger.info(f"Using fallback matched models: {fallback_models}")
                return sorted(fallback_models)
            else:
                logger.warning("No fallback matches found, using default list.")
                return DEFAULT_GOOGLE_AI_MODELS
    else:
        logger.warning("Failed to fetch dynamic Google AI models. Falling back to default list.")
        return DEFAULT_GOOGLE_AI_MODELS

def verify_google_api_key(api_key_to_test: str) -> tuple[bool, str]:
    """驗證Google API密鑰"""
    if not api_key_to_test:
        return False, "API 金鑰不得為空"
    
    original_globally_configured_key = settings.GOOGLE_API_KEY

    try:
        logger.info(f"Attempting to verify Google API Key ending with ...{api_key_to_test[-4:] if len(api_key_to_test) > 4 else '****'}")
        genai.configure(api_key=api_key_to_test)
        
        test_model_id = DEFAULT_GOOGLE_AI_MODELS[0] if DEFAULT_GOOGLE_AI_MODELS else "gemini-1.0-pro"
        model = genai.GenerativeModel(test_model_id)
        
        model.generate_content(
            "Verify API Key", 
            generation_config=genai.types.GenerationConfig(max_output_tokens=5, temperature=0.0),
            request_options=genai.types.RequestOptions(timeout=10)
        )
        
        logger.info(f"Google API Key verification successful using model {test_model_id}.")
        return True, "API 金鑰驗證成功"
    except Exception as e:
        logger.error(f"Google API Key verification failed: {e}", exc_info=False)
        error_message = str(e)
        
        if ("API_KEY_INVALID" in error_message.upper() or 
            "API key not valid" in error_message or 
            (isinstance(e, genai.types.generation_types.StopCandidateException) and "AUTH" in str(e).upper())):
            return False, "API 金鑰無效。請檢查您的金鑰。"
        elif "PERMISSION_DENIED" in error_message.upper():
             return False, "API 金鑰權限不足，或目標 Google Cloud 專案未啟用 Generative Language API。"
        elif "QUOTA_EXCEEDED" in error_message.upper():
            return False, "已超出 Google AI API 配額。"
        elif isinstance(e, TimeoutError) or "DEADLINE_EXCEEDED" in error_message.upper():
            return False, "API 金鑰驗證超時，請檢查網路連線或 Google服務狀態。"
        
        return False, f"API 金鑰驗證失敗：{error_message}"
    finally:
        if original_globally_configured_key:
            genai.configure(api_key=original_globally_configured_key)
            logger.info("Restored original Google AI API Key configuration after verification test.")
        else:
            logger.info("No original Google AI API Key was configured; genai state might be affected by test key if not reconfigured elsewhere.")

def save_ai_api_key_to_env(api_key: str, key_name: str = "GOOGLE_API_KEY") -> bool:
    """保存API密鑰到.env文件"""
    try:
        env_path = find_dotenv(usecwd=True, raise_error_if_not_found=False)
        if not env_path:
            env_path = os.path.join(os.getcwd(), ".env")
            logger.info(f".env file not found, attempting to create at: {env_path}")
            with open(env_path, "a") as f:
                pass 
        
        logger.info(f"Attempting to save API key to .env path: {env_path}")
        set_key(env_path, key_name, api_key)
        load_dotenv(dotenv_path=env_path, override=True)
        
        if hasattr(settings, key_name):
            setattr(settings, key_name, api_key)
            logger.info(f"{key_name} saved to .env file. Live settings updated for {key_name}.")
        else:
            logger.warning(f"{key_name} saved to .env file, but attribute {key_name} not found in live settings object.")
        return True
    except Exception as e:
        logger.error(f"Error saving API key ({key_name}) to .env: {e}", exc_info=True)
        return False

class AIProvider(Enum):
    """AI服務提供商枚舉"""
    GOOGLE = "google"
    OPENAI = "openai"  # 未來擴展
    ANTHROPIC = "anthropic"  # 未來擴展

class TaskType(Enum):
    """AI任務類型枚舉"""
    TEXT_GENERATION = "text_generation"
    IMAGE_ANALYSIS = "image_analysis" 
    EMBEDDING = "embedding"
    CLASSIFICATION = "classification"
    QUERY_REWRITE = "query_rewrite"
    ANSWER_GENERATION = "answer_generation"
    MONGODB_DETAIL_QUERY_GENERATION = "mongodb_detail_query_generation"
    DOCUMENT_SELECTION_FOR_QUERY = "document_selection_for_query"
    CLUSTER_LABEL_GENERATION = "cluster_label_generation"  # 單個聚類標籤生成
    BATCH_CLUSTER_LABELS = "batch_cluster_labels"  # 批量聚類標籤生成

@dataclass
class AIModelConfig:
    """AI模型配置"""
    provider: AIProvider
    model_id: str
    display_name: str
    max_input_tokens: int
    max_output_tokens: int
    supports_images: bool = False
    supports_json_mode: bool = False
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    is_available: bool = True

@dataclass 
class GenerationParams:
    """生成參數配置"""
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 2048
    response_mime_type: Optional[str] = None
    safety_settings: Dict[HarmCategory, HarmBlockThreshold] = field(default_factory=dict)
    preferred_language: str = "zh-TW"  # 偏好語言
    enforce_language_consistency: bool = True  # 強制語言一致性

@dataclass
class TaskConfig:
    """任務專用配置"""
    task_type: TaskType
    preferred_models: List[str]
    generation_params: GenerationParams
    timeout_seconds: int = 30
    retry_attempts: int = 3
    expected_token_range: tuple = (2000, 4000)  # 預期Token範圍
    token_variance_alert_threshold: float = 0.3  # 30%變異告警

class UnifiedAIConfig:
    """統一的AI配置管理器"""
    
    def __init__(self):
        self._models: Dict[str, AIModelConfig] = {}
        self._task_configs: Dict[TaskType, TaskConfig] = {}
        self._current_provider = AIProvider.GOOGLE
        self._user_global_ai_preferences: Dict[str, Any] = {
            "model": None,
            "ensure_chinese_output": True,
            "max_output_tokens": None,
            "prompt_input_max_length": 6000  # 默認輸入提示詞最大長度
        }
        self._initialize_default_configs()
    
    def _initialize_default_configs(self):
        """初始化預設配置"""
        google_models = get_google_ai_models()
        for model_id in google_models:
            self._models[model_id] = AIModelConfig(
                provider=AIProvider.GOOGLE,
                model_id=model_id,
                display_name=model_id,
                max_input_tokens=self._get_model_max_input(model_id),
                max_output_tokens=self._get_model_max_output(model_id),
                supports_images=self._model_supports_images(model_id),
                supports_json_mode=True,
                is_available=True
            )
        
        self._initialize_task_configs()
    
    def _get_model_max_input(self, model_id: str) -> int:
        """獲取模型最大輸入Token數"""
        if "gemini-1.5" in model_id:
            return 1000000  # Gemini 1.5 支持1M tokens
        elif "gemini-2" in model_id:
            return 2000000  # Gemini 2.0 更大容量
        else:
            return 30720    # 預設值
    
    def _get_model_max_output(self, model_id: str) -> int:
        """獲取模型最大輸出Token數"""
        if "pro" in model_id:
            return 8192
        else:
            return 4096
    
    def _model_supports_images(self, model_id: str) -> bool:
        """檢查模型是否支持圖片"""
        # Gemini 1.5、2.0 和 2.5 系列支持圖片
        return any(x in model_id for x in ["1.5", "2.0", "2.5"])
    
    def _initialize_task_configs(self):
        """初始化任務配置"""
        user_preferred_model_from_db = self._user_global_ai_preferences.get("model")
        user_preferred_model = user_preferred_model_from_db if user_preferred_model_from_db and user_preferred_model_from_db in self._models else settings.DEFAULT_AI_MODEL
        if user_preferred_model != user_preferred_model_from_db : logger.info(f"初始化任務配置時，DB中無有效用戶偏好模型 ('{user_preferred_model_from_db}') 或模型不存在，回退到預設模型: {user_preferred_model}")
        else: logger.info(f"初始化任務配置時，使用來自DB的用戶偏好模型: {user_preferred_model}")

        def get_preferred_models_for_task_init(supports_images: bool = False) -> List[str]:
            preferred = []
            if user_preferred_model and user_preferred_model in self._models:
                model_cfg = self._models[user_preferred_model]
                if not supports_images or model_cfg.supports_images: preferred.append(user_preferred_model)
            for model_id in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
                if model_id not in preferred and model_id in self._models:
                    model_cfg = self._models[model_id]
                    if not supports_images or model_cfg.supports_images: preferred.append(model_id)
            return preferred if preferred else ["gemini-1.5-flash"]
        
        common_safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
        self._task_configs[TaskType.TEXT_GENERATION] = TaskConfig(
            task_type=TaskType.TEXT_GENERATION, preferred_models=get_preferred_models_for_task_init(False),
            generation_params=GenerationParams(temperature=settings.AI_TEMPERATURE, top_p=settings.AI_TOP_P, top_k=settings.AI_TOP_K,
                                           max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS, response_mime_type="application/json",
                                           safety_settings=common_safety_settings), timeout_seconds=30, retry_attempts=3)
        self._task_configs[TaskType.IMAGE_ANALYSIS] = TaskConfig(
            task_type=TaskType.IMAGE_ANALYSIS, preferred_models=get_preferred_models_for_task_init(True),
            generation_params=GenerationParams(temperature=settings.AI_TEMPERATURE, top_p=settings.AI_TOP_P, top_k=settings.AI_TOP_K,
                                           max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS_IMAGE, response_mime_type="application/json",
                                           safety_settings=common_safety_settings), timeout_seconds=45, retry_attempts=2)

        # New Task Configuration for Document Selection
        self._task_configs[TaskType.DOCUMENT_SELECTION_FOR_QUERY] = TaskConfig(
            task_type=TaskType.DOCUMENT_SELECTION_FOR_QUERY,
            preferred_models=get_preferred_models_for_task_init(False), # Does not require image support
            generation_params=GenerationParams(
                temperature=0.2, # Low temperature for deterministic selection
                top_p=settings.AI_TOP_P,
                top_k=settings.AI_TOP_K,
                max_output_tokens=512, # Max tokens for a list of IDs
                response_mime_type="application/json",
                safety_settings=common_safety_settings
            ),
            timeout_seconds=20,
            retry_attempts=2
        )
        
        # Configuration for MongoDB Detail Query Generation
        self._task_configs[TaskType.MONGODB_DETAIL_QUERY_GENERATION] = TaskConfig(
            task_type=TaskType.MONGODB_DETAIL_QUERY_GENERATION,
            preferred_models=get_preferred_models_for_task_init(False), # Does not require image support
            generation_params=GenerationParams(
                temperature=0.3, # Lower temperature for more deterministic query generation
                top_p=settings.AI_TOP_P,
                top_k=settings.AI_TOP_K,
                max_output_tokens=1024, # Max tokens for query components
                response_mime_type="application/json",
                safety_settings=common_safety_settings
            ),
            timeout_seconds=25,
            retry_attempts=2
        )
        
        # Configuration for Cluster Label Generation
        self._task_configs[TaskType.CLUSTER_LABEL_GENERATION] = TaskConfig(
            task_type=TaskType.CLUSTER_LABEL_GENERATION,
            preferred_models=get_preferred_models_for_task_init(False), # Does not require image support
            generation_params=GenerationParams(
                temperature=0.5, # Medium temperature for creative but consistent naming
                top_p=settings.AI_TOP_P,
                top_k=settings.AI_TOP_K,
                max_output_tokens=512, # Max tokens for cluster label and description
                response_mime_type="application/json",
                safety_settings=common_safety_settings
            ),
            timeout_seconds=30,
            retry_attempts=3
        )
    
    def _is_model_suitable_for_task(self, model_config: AIModelConfig, task_type: TaskType) -> bool:
        """檢查模型是否適合指定任務"""
        if task_type == TaskType.IMAGE_ANALYSIS: return model_config.supports_images
        return True
    
    async def _get_user_model_preference(self, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
        """從資料庫獲取用戶全局AI偏好 (模型, ensure_chinese, max_output_tokens, prompt_input_max_length)"""
        default_prefs = {
            "model": settings.DEFAULT_AI_MODEL,
            "ensure_chinese_output": True,
            "max_output_tokens": settings.AI_MAX_OUTPUT_TOKENS,
            "prompt_input_max_length": 6000
        }
        try:
            config_doc = await db.system_config.find_one({"_id": "main_system_settings"})
            if config_doc and "ai_service" in config_doc and isinstance(config_doc["ai_service"], dict):
                ai_settings_db = config_doc["ai_service"]
                
                raw_model_pref = ai_settings_db.get("model")
                ensure_chinese_pref = ai_settings_db.get("ensure_chinese_output", default_prefs["ensure_chinese_output"])
                max_tokens_pref = ai_settings_db.get("max_output_tokens")
                prompt_input_max_length_pref = ai_settings_db.get("prompt_input_max_length")
                
                processed_model_pref = default_prefs["model"]
                if isinstance(raw_model_pref, str) and raw_model_pref != 'None': processed_model_pref = raw_model_pref
                elif raw_model_pref is None: processed_model_pref = None; logger.debug("Model preference from DB is Python None.")
                elif raw_model_pref == 'None': processed_model_pref = None; logger.debug("Model preference from DB was string 'None'.")

                user_prefs = {
                    "model": processed_model_pref,
                    "ensure_chinese_output": ensure_chinese_pref,
                    "max_output_tokens": int(max_tokens_pref) if max_tokens_pref is not None else default_prefs["max_output_tokens"],
                    "prompt_input_max_length": int(prompt_input_max_length_pref) if prompt_input_max_length_pref is not None else default_prefs["prompt_input_max_length"]
                }
                logger.info(f"從資料庫加載的用戶AI偏好 (無穩定模式): {user_prefs}")
                return user_prefs
            else: logger.info("資料庫中未找到AI服務設定,將使用全局預設AI偏好 (無穩定模式)。"); return default_prefs
        except Exception as e: logger.error(f"獲取用戶模型偏好失敗: {e}"); return default_prefs
    
    def get_generation_config(self, task_type: TaskType, custom_params: Optional[Dict[str, Any]] = None) -> genai.types.GenerationConfigDict:
        """獲取指定任務的生成配置，並允許自定義參數覆蓋。"""
        
        base_config_dict = {"temperature": 0.7, "top_p": 0.95, "top_k": 40}
        task_specific_dict = {}
        current_task_config = self._task_configs.get(task_type)
        user_max_tokens = self._user_global_ai_preferences.get("max_output_tokens")
        default_max_tokens_for_task = settings.AI_MAX_OUTPUT_TOKENS
        if task_type == TaskType.IMAGE_ANALYSIS: default_max_tokens_for_task = settings.AI_MAX_OUTPUT_TOKENS_IMAGE
        elif current_task_config: default_max_tokens_for_task = current_task_config.generation_params.max_output_tokens
        effective_max_tokens = default_max_tokens_for_task
        if user_max_tokens is not None and isinstance(user_max_tokens, int) and user_max_tokens > 0: effective_max_tokens = user_max_tokens; logger.debug(f"應用用戶設定的 max_output_tokens: {user_max_tokens} (任務: {task_type.value if isinstance(task_type, Enum) else task_type})")
        elif current_task_config: effective_max_tokens = current_task_config.generation_params.max_output_tokens
        if current_task_config:
            task_specific_dict["temperature"] = current_task_config.generation_params.temperature
            task_specific_dict["max_output_tokens"] = effective_max_tokens
            if current_task_config.generation_params.response_mime_type: task_specific_dict["response_mime_type"] = current_task_config.generation_params.response_mime_type
        else: 
            task_specific_dict["max_output_tokens"] = effective_max_tokens
            if task_type == TaskType.IMAGE_ANALYSIS: task_specific_dict["temperature"] = 0.4
            elif task_type == TaskType.TEXT_GENERATION: task_specific_dict["temperature"] = 0.8
        merged_config_dict = {**base_config_dict, **task_specific_dict}
        if self._user_global_ai_preferences.get("ensure_chinese_output", True): logger.debug(f"應用中文輸出偏好設定於任務 {task_type.value if isinstance(task_type, Enum) else task_type}")
        if custom_params: merged_config_dict.update(custom_params)
        logger.debug(f"為任務類型 '{task_type.value if isinstance(task_type, Enum) else task_type}' 生成的AI配置: {merged_config_dict}")
        final_generation_config = {}
        allowed_google_config_keys = ["temperature", "top_p", "top_k", "max_output_tokens", "candidate_count", "stop_sequences", "response_mime_type"]
        for key, value in merged_config_dict.items():
            if key in allowed_google_config_keys: final_generation_config[key] = value
        return genai.types.GenerationConfigDict(**final_generation_config)

    def get_safety_settings(self, task_type: TaskType) -> Dict[HarmCategory, HarmBlockThreshold]:
        """獲取安全設定"""
        task_config = self._task_configs.get(task_type)
        if task_config and task_config.generation_params.safety_settings: return task_config.generation_params.safety_settings
        return {HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE, HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE, HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,}
    
    def get_model_config(self, model_id: str) -> Optional[AIModelConfig]:
        """獲取模型配置"""
        return self._models.get(model_id)
    
    def list_available_models(self, task_type: Optional[TaskType] = None) -> List[AIModelConfig]:
        """列出可用模型"""
        models = [m for m in self._models.values() if m.is_available]
        
        if task_type:
            # 過濾適合特定任務的模型
            models = [m for m in models if self._is_model_suitable_for_task(m, task_type)]
        
        return sorted(models, key=lambda x: x.display_name)
    
    async def verify_and_save_api_key(self, api_key: str) -> tuple[bool, str]:
        """驗證並保存API金鑰"""
        is_valid, message = verify_google_api_key(api_key)
        
        if is_valid:
            success = save_ai_api_key_to_env(api_key)
            if success:
                # 重新配置genai
                genai.configure(api_key=api_key)
                # 更新settings
                settings.GOOGLE_API_KEY = api_key
                return True, "API金鑰驗證並保存成功"
            else:
                return False, "API金鑰驗證成功但保存失敗"
        
        return False, message
    
    async def update_task_config(
        self, 
        task_type: TaskType, 
        config_updates: Dict[str, Any]
    ) -> bool:
        """更新任務配置"""
        try:
            if task_type not in self._task_configs:
                logger.error(f"未知的任務類型: {task_type}")
                return False
            
            task_config = self._task_configs[task_type]
            
            # 更新偏好模型
            if "preferred_models" in config_updates:
                task_config.preferred_models = config_updates["preferred_models"]
            
            # 更新生成參數
            if "generation_params" in config_updates:
                gen_params = config_updates["generation_params"]
                if "temperature" in gen_params:
                    task_config.generation_params.temperature = gen_params["temperature"]
                if "max_output_tokens" in gen_params:
                    task_config.generation_params.max_output_tokens = gen_params["max_output_tokens"]
            
            logger.info(f"任務配置已更新: {task_type}")
            return True
        
        except Exception as e:
            logger.error(f"更新任務配置失敗: {e}")
            return False

    async def reload_task_configs(self, db: Optional[AsyncIOMotorDatabase] = None) -> bool:
        """重新載入任務配置以應用新的用戶偏好設定"""
        try:
            if db is not None: self._user_global_ai_preferences = await self._get_user_model_preference(db)
            else: 
                logger.warning("reload_task_configs 在沒有 DB 實例的情況下被調用。用戶設定可能不是最新的。")
                # 如果沒有DB，至少使用一個合理的預設，而不是依賴可能未初始化的 user_global_ai_preferences
                self._user_global_ai_preferences = {
                    "model": settings.DEFAULT_AI_MODEL,
                    "ensure_chinese_output": True,
                    "max_output_tokens": settings.AI_MAX_OUTPUT_TOKENS,
                    "prompt_input_max_length": 6000
                }

            user_preferred_model_from_db = self._user_global_ai_preferences.get("model")

            # 新增：映射通用名稱到具體的預覽版名稱
            model_mapping = {
                "gemini-2.5-flash": "gemini-2.5-flash-preview-05-20",
                "gemini-2.5-pro": "gemini-2.5-pro-preview-05-06",
                "gemini-1.5-pro": "gemini-1.5-pro-latest", # 假設 "gemini-1.5-pro-latest" 是我們在 DEFAULT_GOOGLE_AI_MODELS 中使用的 ID
                "gemini-1.5-flash": "gemini-1.5-flash-latest" # 假設 "gemini-1.5-flash-latest" 是我們在 DEFAULT_GOOGLE_AI_MODELS 中使用的 ID
                # 如果 DEFAULT_GOOGLE_AI_MODELS 使用的是 "gemini-1.5-pro" 和 "gemini-1.5-flash"，則不需要這兩條映射
            }
            
            # 校驗映射目標是否存在於 self._models (確保映射到的是系統已知的模型)
            # 並更新 DEFAULT_GOOGLE_AI_MODELS 以匹配這些映射目標，如果它們還沒完全一致
            # 例如, 確保 "gemini-1.5-pro-latest" 在 DEFAULT_GOOGLE_AI_MODELS 中 (如果它是映射目標)
            # 為了簡化，這裡假設 DEFAULT_GOOGLE_AI_MODELS 已經包含了正確的映射目標ID

            if user_preferred_model_from_db in model_mapping:
                mapped_model = model_mapping[user_preferred_model_from_db]
                # 只有當映射後的模型存在於系統已知的模型列表 (_models) 中時才進行更新
                if mapped_model in self._models:
                    original_pref = user_preferred_model_from_db
                    self._user_global_ai_preferences["model"] = mapped_model
                    logger.info(f"用戶偏好模型 '{original_pref}' 已映射到系統已知的具體版本 '{mapped_model}'")
                else:
                    logger.warning(f"用戶偏好模型 '{user_preferred_model_from_db}' 的映射目標 '{mapped_model}' 未在系統配置中找到。將保留原始偏好或回退。")
            
            # 更新後，user_preferred_model 將使用 self._user_global_ai_preferences 中可能已被映射的值
            user_preferred_model = self._user_global_ai_preferences.get("model")
            
            logger.info(f"重新載入任務配置，使用全局AI偏好 (無穩定模式): {self._user_global_ai_preferences}")
            
            def get_preferred_models_for_task_reload(supports_images: bool = False) -> List[str]:
                preferred = []
                if user_preferred_model and user_preferred_model in self._models:
                    model_cfg = self._models[user_preferred_model]
                    if not supports_images or model_cfg.supports_images: preferred.append(user_preferred_model)
                for model_id in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
                    if model_id not in preferred and model_id in self._models:
                        model_cfg = self._models[model_id]
                        if not supports_images or model_cfg.supports_images: preferred.append(model_id)
                return preferred if preferred else ["gemini-1.5-flash"]
            
            if TaskType.TEXT_GENERATION in self._task_configs: self._task_configs[TaskType.TEXT_GENERATION].preferred_models = get_preferred_models_for_task_reload(False)
            if TaskType.IMAGE_ANALYSIS in self._task_configs: self._task_configs[TaskType.IMAGE_ANALYSIS].preferred_models = get_preferred_models_for_task_reload(True)
            # Add MONGODB_DETAIL_QUERY_GENERATION to the reload logic
            if TaskType.MONGODB_DETAIL_QUERY_GENERATION in self._task_configs: self._task_configs[TaskType.MONGODB_DETAIL_QUERY_GENERATION].preferred_models = get_preferred_models_for_task_reload(False)
            # Add DOCUMENT_SELECTION_FOR_QUERY to the reload logic
            if TaskType.DOCUMENT_SELECTION_FOR_QUERY in self._task_configs: self._task_configs[TaskType.DOCUMENT_SELECTION_FOR_QUERY].preferred_models = get_preferred_models_for_task_reload(False)
            
            logger.info("任務配置重新載入完成 (無穩定模式影響)")
            return True
        
        except Exception as e:
            logger.error(f"重新載入任務配置失敗: {e}")
            return False

    async def get_model_for_task(
        self,
        task_type: TaskType,
        requested_model_override: Optional[str] = None,
    ) -> Optional[str]:
        """
        為指定任務選擇最合適的AI模型 (已移除穩定模式考量)。
        優先級順序:
        1. API請求中的模型覆蓋 (requested_model_override)
        2. 用戶全局偏好中的模型 (model from _user_global_ai_preferences)
        3. 任務配置中的預設偏好模型列表
        4. 全局後備可用模型
        """
        
        log_prefix = f"[ModelSelV2][Task:{task_type.value if isinstance(task_type, Enum) else task_type}]"
        user_global_model = self._user_global_ai_preferences.get("model")

        def _try_select_model(model_id_to_check: Optional[str], source_description: str) -> Optional[str]:
            if model_id_to_check and model_id_to_check in self._models and self._models[model_id_to_check].is_available:
                model_cfg = self._models[model_id_to_check]
                if self._is_model_suitable_for_task(model_cfg, task_type):
                    logger.info(f"{log_prefix} 選用來自 '{source_description}' 的模型: {model_id_to_check}")
                    return model_id_to_check
                else: logger.debug(f"{log_prefix} '{source_description}' 模型 '{model_id_to_check}' 不適用於任務，跳過。")
            elif model_id_to_check: logger.debug(f"{log_prefix} '{source_description}' 模型 '{model_id_to_check}' 不可用或不存在於配置中，跳過。")
            return None

        selected_model = _try_select_model(requested_model_override, "API請求覆蓋")
        if selected_model: return selected_model

        selected_model = _try_select_model(user_global_model, "用戶全局偏好")
        if selected_model: return selected_model
        
        task_config = self._task_configs.get(task_type)
        if task_config:
            for model_id in task_config.preferred_models:
                selected_model = _try_select_model(model_id, "任務配置偏好列表")
                if selected_model: return selected_model
        
        all_available_suitable_models = self.list_available_models(task_type=task_type)
        if all_available_suitable_models:
            # For backup, just pick the first one that is suitable and available.
            # _is_model_suitable_for_task and is_available is already checked by list_available_models.
            backup_model_id = all_available_suitable_models[0].model_id
            logger.info(f"{log_prefix} 選用來自 全局後備列表 的模型: {backup_model_id}")
            return backup_model_id
        
        logger.error(f"{log_prefix} 無法為任務找到任何適用模型。")
        return None

# 全局AI配置管理器實例
unified_ai_config = UnifiedAIConfig() 