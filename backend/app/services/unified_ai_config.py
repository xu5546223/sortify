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
    "gemini-2.5-flash",
    "gemini-2.5-pro",
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
        # 直接返回可用的API模型名稱，按優先級排序
        preferred_models = []
        
        # 定義模型優先級順序 - 從最新到最舊，優先選擇穩定版本
        priority_order = [
            # Gemini 2.5 系列（預覽版本）
            "gemini-2.5-pro-preview-05-06",
            "gemini-2.5-pro-preview-03-25", 
            "gemini-2.5-pro-exp-03-25",
            "gemini-2.5-flash-preview-05-20",
            "gemini-2.5-flash-preview-04-17",
            
            # Gemini 2.0 系列
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
            "gemini-2.0-flash-exp",
            
            # Gemini 1.5 系列
            "gemini-1.5-flash",
            "gemini-1.5-flash-002",
            "gemini-1.5-flash-001",
            "gemini-1.5-pro",
            "gemini-1.5-pro-002",
            "gemini-1.5-pro-001",
            
            # 舊版本
            "gemini-1.0-pro",
            "gemini-1.0-pro-vision-latest",
            "gemini-pro",
            "gemini-pro-vision",
        ]
        
        # 按優先級順序添加可用的模型（避免重複）
        added_models = set()
        for model_name in priority_order:
            if model_name in all_models_from_api and model_name not in added_models:
                preferred_models.append(model_name)
                added_models.add(model_name)
        
        # 添加其他在API中可用但不在優先級列表中的DEFAULT模型
        for model in DEFAULT_GOOGLE_AI_MODELS:
            if model in all_models_from_api and model not in added_models:
                preferred_models.append(model)
                added_models.add(model)
        
        if preferred_models:
            logger.info(f"Using dynamically fetched Google AI models: {preferred_models}")
            return preferred_models
        else:
            logger.warning("Dynamic fetch succeeded but no preferred models found.")
            # 回退：返回所有可用的DEFAULT模型
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
    stability_priority: bool = True  # 優先穩定性而非最新功能
    expected_token_range: tuple = (2000, 4000)  # 預期Token範圍
    token_variance_alert_threshold: float = 0.3  # 30%變異告警

class UnifiedAIConfig:
    """統一的AI配置管理器"""
    
    def __init__(self):
        self._models: Dict[str, AIModelConfig] = {}
        self._task_configs: Dict[TaskType, TaskConfig] = {}
        self._current_provider = AIProvider.GOOGLE
        # 新增：儲存從資料庫讀取的用戶AI偏好
        self._user_global_ai_preferences: Dict[str, Any] = {
            "model": None,
            "force_stable_model": True, # 預設值
            "ensure_chinese_output": True, # 預設值
            "max_output_tokens": None # 新增預設值
        }
        self._initialize_default_configs()
    
    def _initialize_default_configs(self):
        """初始化預設配置"""
        # 初始化Google模型配置
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
        
        # 初始化任務配置
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
        # 從 self._user_global_ai_preferences 獲取用戶偏好模型，如果不存在或無效，則使用環境變數的預設值
        user_preferred_model_from_db = self._user_global_ai_preferences.get("model")
        
        if user_preferred_model_from_db and user_preferred_model_from_db in self._models:
            user_preferred_model = user_preferred_model_from_db
            logger.info(f"初始化任務配置時，使用來自DB的用戶偏好模型: {user_preferred_model}")
        else:
            user_preferred_model = settings.DEFAULT_AI_MODEL
            logger.info(f"初始化任務配置時，DB中無有效用戶偏好模型或模型不存在，回退到預設模型: {user_preferred_model} (DB值: {user_preferred_model_from_db})")

        # 構建偏好模型列表：用戶偏好模型優先，然後是其他可用模型
        def get_preferred_models_for_task(supports_images: bool = False) -> List[str]:
            preferred = []
            
            # 首先添加用戶偏好模型（如果適合任務）
            if user_preferred_model in self._models:
                model_config = self._models[user_preferred_model]
                if not supports_images or model_config.supports_images:
                    preferred.append(user_preferred_model)
            
            # 然後添加其他適合的模型
            for model_id in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
                if model_id not in preferred and model_id in self._models:
                    model_config = self._models[model_id]
                    if not supports_images or model_config.supports_images:
                        preferred.append(model_id)
            
            return preferred if preferred else ["gemini-1.5-flash"]  # 最後的後備選擇
        
        # 文本生成任務配置
        self._task_configs[TaskType.TEXT_GENERATION] = TaskConfig(
            task_type=TaskType.TEXT_GENERATION,
            preferred_models=get_preferred_models_for_task(supports_images=False),
            generation_params=GenerationParams(
                temperature=settings.AI_TEMPERATURE,
                top_p=settings.AI_TOP_P,
                top_k=settings.AI_TOP_K,
                max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
            ),
            timeout_seconds=30,
            retry_attempts=3
        )
        
        # 圖片分析任務配置
        self._task_configs[TaskType.IMAGE_ANALYSIS] = TaskConfig(
            task_type=TaskType.IMAGE_ANALYSIS,
            preferred_models=get_preferred_models_for_task(supports_images=True),
            generation_params=GenerationParams(
                temperature=settings.AI_TEMPERATURE,
                top_p=settings.AI_TOP_P,
                top_k=settings.AI_TOP_K,
                max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS_IMAGE,
                response_mime_type="application/json",
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
            ),
            timeout_seconds=45,
            retry_attempts=2
        )
    
    async def get_preferred_model_for_task(
        self, 
        task_type: TaskType,
        # db: Optional[AsyncIOMotorDatabase] = None, # 不再總是需要DB，因為偏好已載入
        user_preference_override: Optional[str] = None # 允許外部調用覆蓋DB中設定的模型
    ) -> Optional[str]:
        """獲取任務的首選模型"""
        try:
            # 1. 優先使用外部傳入的 user_preference_override
            if user_preference_override and user_preference_override in self._models:
                model_config_override = self._models[user_preference_override]
                if self._is_model_suitable_for_task(model_config_override, task_type):
                    logger.debug(f"使用外部覆蓋模型: {user_preference_override} 適用於任務 {task_type.value}")
                    return user_preference_override
            
            # 2. 使用內部存儲的用戶全局偏好模型 (已通過 reload_task_configs 從 DB 或 env 載入)
            user_preferred_model_from_global_prefs = self._user_global_ai_preferences.get("model")
            logger.debug(f"[GetPrefModel Step 2] Global pref model from self._user_global_ai_preferences: '{user_preferred_model_from_global_prefs}'")
            if user_preferred_model_from_global_prefs and user_preferred_model_from_global_prefs in self._models:
                model_config_global = self._models[user_preferred_model_from_global_prefs]
                logger.debug(f"[GetPrefModel Step 2] Model config for '{user_preferred_model_from_global_prefs}': supports_images={model_config_global.supports_images}, is_available={model_config_global.is_available}")
                is_suitable = self._is_model_suitable_for_task(model_config_global, task_type)
                logger.debug(f"[GetPrefModel Step 2] Is '{user_preferred_model_from_global_prefs}' suitable for task '{task_type.value}'? {is_suitable}")
                if is_suitable:
                    logger.info(f"選用[全局偏好模型]: {user_preferred_model_from_global_prefs} (適用於任務 {task_type.value})")
                    return user_preferred_model_from_global_prefs
                else:
                    logger.debug(f"[GetPrefModel Step 2] Global pref model '{user_preferred_model_from_global_prefs}' is NOT suitable for task '{task_type.value}'.")
            else:
                logger.debug(f"[GetPrefModel Step 2] Global pref model '{user_preferred_model_from_global_prefs}' not found in self._models or is None.")
            
            # 3. 使用任務配置中定義的偏好模型列表 (這些列表也應該在 reload_task_configs 中被用戶偏好影響)
            task_config = self._task_configs.get(task_type)
            if task_config:
                for model_id in task_config.preferred_models:
                    if model_id in self._models and self._models[model_id].is_available:
                        if self._is_model_suitable_for_task(self._models[model_id], task_type):
                            logger.debug(f"使用任務配置模型: {model_id} 適用於任務 {task_type.value}")
                            return model_id
            
            # 4. 如果上述都沒有，但全局偏好中有模型（即使不適合任務，作為最後手段，如果沒有更合適的）
            #    這一步可能需要重新考慮，通常應該返回 None 如果沒有適合的模型
            if user_preferred_model_from_global_prefs and user_preferred_model_from_global_prefs in self._models:
                logger.debug(f"回退到全局偏好模型 (可能不完全適合任務): {user_preferred_model_from_global_prefs}")
                return user_preferred_model_from_global_prefs
            
            # 5. 返回第一個可用的且適合任務的模型 (作為最後的後備)
            available_models = self.list_available_models(task_type=task_type)
            if available_models:
                logger.debug(f"回退到第一個可用且適合任務的模型: {available_models[0].model_id}")
                return available_models[0].model_id
                
            logger.warning(f"沒有找到適用於任務 {task_type.value} 的偏好模型。")
            return None
        
        except Exception as e:
            logger.error(f"獲取首選模型失敗: {e}")
            # 使用已儲存的全局偏好模型或最終後備
            return self._user_global_ai_preferences.get("model") or "gemini-1.5-flash"
    
    def _is_model_suitable_for_task(self, model_config: AIModelConfig, task_type: TaskType) -> bool:
        """檢查模型是否適合指定任務"""
        if task_type == TaskType.IMAGE_ANALYSIS:
            return model_config.supports_images
        return True
    
    async def _get_user_model_preference(
        self, 
        db: AsyncIOMotorDatabase
    ) -> Dict[str, Any]: # 返回包含完整偏好的字典
        """從資料庫獲取用戶全局AI偏好 (模型, force_stable, ensure_chinese, max_output_tokens)"""
        default_prefs = {
            "model": settings.DEFAULT_AI_MODEL, # 從環境變數讀取基礎模型偏好
            "force_stable_model": True, # 預設為 True
            "ensure_chinese_output": True, # 預設為 True
            "max_output_tokens": settings.AI_MAX_OUTPUT_TOKENS # 從全局配置獲取預設最大Token
        }
        try:
            config_doc = await db.system_config.find_one({"_id": "main_system_settings"})
            if config_doc and "ai_service" in config_doc and isinstance(config_doc["ai_service"], dict):
                ai_settings_db = config_doc["ai_service"]
                
                # 獲取原始值
                raw_model_pref = ai_settings_db.get("model") # 可能為 None, 'None' string, or actual model string
                force_stable_pref = ai_settings_db.get("force_stable_model", default_prefs["force_stable_model"])
                ensure_chinese_pref = ai_settings_db.get("ensure_chinese_output", default_prefs["ensure_chinese_output"])
                max_tokens_pref = ai_settings_db.get("max_output_tokens") # 新增獲取
                
                # 處理 model_pref
                processed_model_pref = default_prefs["model"] # 預設值
                if isinstance(raw_model_pref, str) and raw_model_pref != 'None':
                    processed_model_pref = raw_model_pref # 使用DB中的有效模型名稱
                elif raw_model_pref is None: # 如果DB中明確是null/None，則表示不指定模型，應使用環境變數預設或任務預設
                    processed_model_pref = None # 或者 default_prefs["model"]，取決於 None 的確切含義
                    logger.debug(f"Model preference from DB is Python None. Effective model preference will be None (task/global default will apply).")
                elif raw_model_pref == 'None': # 如果是字串 'None'
                    processed_model_pref = None # 視為 Python None
                    logger.debug(f"Model preference from DB was string 'None', converting to Python None. Effective model preference will be None.")
                # 如果 raw_model_pref 是其他非字串類型且非 None，則堅持使用 default_prefs["model"]

                # 確保布林值被正確處理
                if not isinstance(force_stable_pref, bool):
                    force_stable_pref = default_prefs["force_stable_model"]
                if not isinstance(ensure_chinese_pref, bool):
                    ensure_chinese_pref = default_prefs["ensure_chinese_output"]

                logger.debug(f"從資料庫獲取用戶AI偏好: model_raw='{raw_model_pref}', model_processed='{processed_model_pref}', force_stable={force_stable_pref}, ensure_chinese={ensure_chinese_pref}")
                
                user_prefs = {
                    "model": processed_model_pref,
                    "force_stable_model": force_stable_pref,
                    "ensure_chinese_output": ensure_chinese_pref,
                    "max_output_tokens": int(max_tokens_pref) if max_tokens_pref is not None else default_prefs["max_output_tokens"] # 新增處理
                }
                logger.info(f"從資料庫加載的用戶AI偏好: {user_prefs}")
                return user_prefs
            else:
                logger.info("資料庫中未找到AI服務設定，將使用全局預設AI偏好。")
                return default_prefs
        except Exception as e:
            logger.error(f"獲取用戶模型偏好失敗: {e}")
            return default_prefs
    
    def get_generation_config(
        self, 
        task_type: TaskType, 
        custom_params: Optional[Dict[str, Any]] = None
    ) -> genai.types.GenerationConfigDict:
        """獲取指定任務的生成配置，並允許自定義參數覆蓋。"""
        
        base_config_dict = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
        }

        task_specific_dict = {}
        current_task_config = self._task_configs.get(task_type)
        
        # 從用戶偏好或任務配置或全局配置獲取 max_output_tokens
        user_max_tokens = self._user_global_ai_preferences.get("max_output_tokens")
        
        default_max_tokens_for_task = settings.AI_MAX_OUTPUT_TOKENS # 通用預設
        if task_type == TaskType.IMAGE_ANALYSIS:
            default_max_tokens_for_task = settings.AI_MAX_OUTPUT_TOKENS_IMAGE
        elif current_task_config:
            default_max_tokens_for_task = current_task_config.generation_params.max_output_tokens
            
        # 優先順序: custom_params -> user_pref -> task_config -> global_settings
        # effective_max_tokens 會在下面 merged_config_dict.update(custom_params) 時被 custom_params 覆蓋 (如果有的話)
        # 如果 custom_params 沒有，則使用 user_max_tokens (如果存在且有效)
        # 否則使用 default_max_tokens_for_task
        effective_max_tokens = default_max_tokens_for_task # 先設定一個基礎預設值
        if user_max_tokens is not None and isinstance(user_max_tokens, int) and user_max_tokens > 0:
            effective_max_tokens = user_max_tokens
            logger.debug(f"應用用戶設定的 max_output_tokens: {user_max_tokens} (任務類型: {task_type.value})")
        elif current_task_config: # 如果用戶沒設，但任務有設
             effective_max_tokens = current_task_config.generation_params.max_output_tokens

        if current_task_config: # 從 TaskConfig 獲取預設參數
            task_specific_dict["temperature"] = current_task_config.generation_params.temperature
            task_specific_dict["max_output_tokens"] = effective_max_tokens # 使用計算後的 effective_max_tokens
            if current_task_config.generation_params.response_mime_type:
                 task_specific_dict["response_mime_type"] = current_task_config.generation_params.response_mime_type
            # top_p, top_k 等也可以從 current_task_config.generation_params 獲取
        else: # 如果沒有特定任務配置，提供一些通用預設值
            task_specific_dict["max_output_tokens"] = effective_max_tokens # 即使沒有task_config，也使用計算後的effective_max_tokens
            if task_type == TaskType.IMAGE_ANALYSIS:
                task_specific_dict["temperature"] = 0.4
                # max_output_tokens 已在上面處理
            elif task_type == TaskType.TEXT_GENERATION:
                task_specific_dict["temperature"] = 0.8
                # max_output_tokens 已在上面處理
            # ... 其他 TaskType 的預設 ...

        # 合併配置：基礎 -> 任務特定
        merged_config_dict = {**base_config_dict, **task_specific_dict}

        # 根據全局用戶偏好調整語言相關設定
        if self._user_global_ai_preferences.get("ensure_chinese_output", True):
            # 這裡的設定依賴於 GenerationParams 的實際意義
            # 以及 Google API 是否有直接控制輸出語言的參數。
            # 假設我們的 GenerationParams.preferred_language 和 enforce_language_consistency
            # 是我們在提示工程中會用到的。
            # merged_config_dict['preferred_language'] = "zh-TW" # 示例
            # merged_config_dict['enforce_language_consistency'] = True # 示例
            logger.debug(f"應用中文輸出偏好設定於任務 {task_type.value}")
            # 注意：Google GenAI 的 GenerationConfigDict 可能不直接包含這些自定義語言欄位。
            # 這些更可能影響 prompt 的構建，或者需要在更上層的服務邏輯中處理。
            # 暫時，我們只記錄這個意圖。

        if custom_params: # 自定義參數具有最高優先級
            merged_config_dict.update(custom_params)

        logger.debug(f"為任務類型 '{task_type.value if isinstance(task_type, Enum) else task_type}' 生成的AI配置: {merged_config_dict}")
        return genai.types.GenerationConfigDict(**merged_config_dict)

    def get_safety_settings(self, task_type: TaskType) -> Dict[HarmCategory, HarmBlockThreshold]:
        """獲取安全設定"""
        task_config = self._task_configs.get(task_type)
        if task_config and task_config.generation_params.safety_settings:
            return task_config.generation_params.safety_settings
        
        # 預設安全設定
        return {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
    
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
                # 可以添加更多參數更新邏輯
            
            logger.info(f"任務配置已更新: {task_type}")
            return True
        
        except Exception as e:
            logger.error(f"更新任務配置失敗: {e}")
            return False

    async def reload_task_configs(self, db: Optional[AsyncIOMotorDatabase] = None) -> bool:
        """重新載入任務配置以應用新的用戶偏好設定"""
        try:
            if db is not None:
                self._user_global_ai_preferences = await self._get_user_model_preference(db)
            else:
                 # 如果沒有DB，則使用目前的內部預設或上次從env初始化的值
                logger.warning("reload_task_configs 在沒有 DB 實例的情況下被調用，可能無法獲取最新的用戶DB設定。")
                # 維持 self._user_global_ai_preferences 不變或用env重新初始化
                self._user_global_ai_preferences["model"] = settings.DEFAULT_AI_MODEL
                # force_stable_model 和 ensure_chinese_output 保持其在 __init__ 或上次 DB 讀取時的狀態

            user_preferred_model = self._user_global_ai_preferences.get("model")
            
            logger.info(f"重新載入任務配置，使用全局AI偏好: {self._user_global_ai_preferences}")
            
            # 構建偏好模型列表的輔助函數
            def get_preferred_models_for_task(supports_images: bool = False) -> List[str]:
                preferred = []
                
                # 首先添加用戶偏好模型（如果適合任務）
                if user_preferred_model and user_preferred_model in self._models:
                    model_config = self._models[user_preferred_model]
                    if not supports_images or model_config.supports_images:
                        preferred.append(user_preferred_model)
                
                # 然後添加其他適合的模型作為後備
                for model_id in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
                    if model_id not in preferred and model_id in self._models:
                        model_config = self._models[model_id]
                        if not supports_images or model_config.supports_images:
                            preferred.append(model_id)
                
                return preferred if preferred else ["gemini-1.5-flash"]  # 最後的後備選擇
            
            # 更新文本生成任務的偏好模型
            if TaskType.TEXT_GENERATION in self._task_configs:
                self._task_configs[TaskType.TEXT_GENERATION].preferred_models = get_preferred_models_for_task(supports_images=False)
            
            # 更新圖片分析任務的偏好模型
            if TaskType.IMAGE_ANALYSIS in self._task_configs:
                self._task_configs[TaskType.IMAGE_ANALYSIS].preferred_models = get_preferred_models_for_task(supports_images=True)
            
            logger.info("任務配置重新載入完成")
            return True
        
        except Exception as e:
            logger.error(f"重新載入任務配置失敗: {e}")
            return False

    async def get_stable_model_for_task(
        self, 
        task_type: TaskType,
        # db: Optional[AsyncIOMotorDatabase] = None, # 不再需要DB參數，因為偏好已載入
        force_stability_override: Optional[bool] = None # 允許外部調用覆蓋DB設定
    ) -> Optional[str]:
        """獲取穩定的模型，優先考慮一致性而非最新功能"""
        try:
            # 穩定性優先的模型列表 (經過驗證的穩定模型)
            stable_models_priority = [
                "gemini-1.5-flash",      # 最穩定
                "gemini-1.5-pro",       # 穩定且功能豐富
                "gemini-2.0-flash",     # 新一代穩定版
                "gemini-1.0-pro",       # 經典穩定版
            ]
            
            # 決定是否強制穩定
            should_force_stability = self._user_global_ai_preferences.get("force_stable_model", True)
            if force_stability_override is not None:
                should_force_stability = force_stability_override # 外部覆蓋優先

            task_config = self._task_configs.get(task_type)
            # 即使任務本身不優先穩定，如果全局設定或覆蓋要求穩定，則依然優先穩定
            if not should_force_stability:
                # 如果不要求穩定性優先，使用常規邏輯 (常規邏輯內部也應該考慮用戶偏好的模型)
                return await self.get_preferred_model_for_task(task_type, user_preference_override=None)
            
            # 選擇第一個可用的穩定模型
            for model_id in stable_models_priority:
                if model_id in self._models and self._models[model_id].is_available:
                    model_config = self._models[model_id]
                    if self._is_model_suitable_for_task(model_config, task_type):
                        logger.info(f"選擇穩定模型 {model_id} 用於任務 {task_type.value} (強制穩定: {should_force_stability})")
                        return model_id
            
            # 如果沒有穩定模型可用，回退到常規選擇
            logger.warning(f"沒有穩定模型可用 (強制穩定: {should_force_stability})，回退到常規模型選擇")
            return await self.get_preferred_model_for_task(task_type, user_preference_override=None)
        
        except Exception as e:
            logger.error(f"獲取穩定模型失敗: {e}")
            return self._user_global_ai_preferences.get("model") or "gemini-1.5-flash"  # 最後的安全選擇

# 全局AI配置管理器實例
unified_ai_config = UnifiedAIConfig() 