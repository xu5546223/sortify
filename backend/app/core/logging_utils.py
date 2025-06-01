import inspect
from typing import Optional, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.log_models import LogLevel, LogEntryCreate
from ..crud import crud_logs
from urllib.parse import urlparse # Added for MONGODB_URL masking
# 考慮加入標準庫的 logging，用於備份日誌或記錄 logging_utils 本身的錯誤
import logging

# 標準庫 logger，用於 logging_utils.py 內部日誌
module_logger = logging.getLogger(__name__)

SENSITIVE_KEYS = [
    "password", "token", "secret", "api_key", "credentials",
    "MONGODB_URL", "SECRET_KEY", "GOOGLE_API_KEY",
    "access_token", "refresh_token"
]

# Keys for which mask_string_part should be applied
STRING_MASK_TARGET_KEYS = [
    "GOOGLE_API_KEY", "access_token", "refresh_token", "api_key" # Add other keys if needed
]

def mask_string_part(value: str, unmasked_prefix_len: int = 4, unmasked_suffix_len: int = 4) -> str:
    """Masks the middle part of a string."""
    if not isinstance(value, str):
        return value # Or raise an error, depending on desired handling
    if len(value) <= unmasked_prefix_len + unmasked_suffix_len:
        return "[MASKED]" # String too short to mask meaningfully, mask entirely
    prefix = value[:unmasked_prefix_len]
    suffix = value[-unmasked_suffix_len:]
    return f"{prefix}[...]{suffix}"

def mask_sensitive_data(data: Any) -> Any:
    """Recursively masks sensitive data in dictionaries and lists."""
    if isinstance(data, dict):
        masked_dict = {}
        for key, value in data.items():
            if key in SENSITIVE_KEYS:
                if key == "MONGODB_URL" and isinstance(value, str):
                    try:
                        parsed_url = urlparse(value)
                        if parsed_url.password:
                            masked_url = parsed_url._replace(netloc=f"{parsed_url.username}:[MASKED]@{parsed_url.hostname}")
                            masked_dict[key] = masked_url.geturl()
                        else:
                            masked_dict[key] = "[MASKED]" # Or mask_string_part if preferred for the whole URL
                    except Exception: # Fallback if URL parsing fails
                        masked_dict[key] = "[MASKED]"
                elif key in STRING_MASK_TARGET_KEYS and isinstance(value, str):
                    masked_dict[key] = mask_string_part(value)
                else:
                    masked_dict[key] = "[MASKED]"
            else:
                masked_dict[key] = mask_sensitive_data(value)
        return masked_dict
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    else:
        return data

class AppLogger:
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        if not self.logger.handlers: # 避免重複添加 handlers
            ch = logging.StreamHandler()
            ch.setLevel(level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

    def get_logger(self) -> logging.Logger:
        return self.logger

async def get_caller_info(depth: int = 2):
    """輔助函數，獲取調用者的模組和函數名稱。"""
    try:
        frame = inspect.currentframe()
        # 向上追溯堆疊幀以找到真正的調用者
        for _ in range(depth):
            if frame.f_back:
                frame = frame.f_back
            else:
                break # 如果堆疊不夠深，則停止
        
        module_obj = inspect.getmodule(frame)
        module_name = module_obj.__name__ if module_obj else None
        function_name = frame.f_code.co_name
        return module_name, function_name
    except Exception as e:
        module_logger.error(f"Error getting caller info: {e}", exc_info=True)
        return "unknown_module", "unknown_function" # 提供一個回退值

async def log_event(
    db: AsyncIOMotorDatabase,
    level: LogLevel,
    message: str,
    source: Optional[str] = None,       # 例如："documents_api", "system_service"
    module_name: Optional[str] = None,  # 如果為 None，將嘗試自動填充
    func_name: Optional[str] = None,    # 如果為 None，將嘗試自動填充
    user_id: Optional[str] = None,
    device_id: Optional[str] = None,
    request_id: Optional[str] = None,   # 用於追蹤跨越多個服務的請求
    details: Optional[Dict[str, Any]] = None,
    auto_fill_caller_info: bool = True, # 是否自動填充模組和函數名
    caller_depth_offset: int = 0 # 調整堆疊追溯的深度
):
    """
    創建一個日誌條目並將其儲存到資料庫。
    如果 db is None，則使用標準 Python logger (module_logger) 記錄到控制台/檔案。
    """
    # Handle db=None case first by logging to console/file
    if db is None:
        level_mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        std_log_level = level_mapping.get(level, logging.INFO) # Default to INFO

        # Mask details before logging to console if db is None
        # This ensures sensitive data is masked even for non-DB logs if details are provided.
        console_details_to_log = mask_sensitive_data(details) if details else None

        log_message_for_console = f"{message}"
        if source:
            log_message_for_console = f"[{source}] {log_message_for_console}"
        # Auto-fill caller info for console logs if not provided and auto_fill is true
        actual_module_for_console = module_name
        actual_func_for_console = func_name
        if auto_fill_caller_info:
            auto_module_c, auto_function_c = await get_caller_info(depth=2 + caller_depth_offset)
            if actual_module_for_console is None: actual_module_for_console = auto_module_c
            if actual_func_for_console is None: actual_func_for_console = auto_function_c

        if actual_module_for_console and actual_func_for_console:
             log_message_for_console = f"({actual_module_for_console}.{actual_func_for_console}) {log_message_for_console}"
        elif actual_module_for_console:
             log_message_for_console = f"({actual_module_for_console}) {log_message_for_console}"


        if console_details_to_log: # Use masked details for console
            log_message_for_console += f" | Details: {console_details_to_log}"
        if request_id:
            log_message_for_console += f" | Request ID: {request_id}"
        if user_id:
            log_message_for_console += f" | User ID: {user_id}"
        if device_id: # Added device_id to console log
            log_message_for_console += f" | Device ID: {device_id}"

        module_logger.log(std_log_level, log_message_for_console)
        return # Important: return here to bypass database logging attempt

    # Existing database logging logic if db is not None
    actual_module_name = module_name
    actual_func_name = func_name

    if auto_fill_caller_info:
        auto_module, auto_function = await get_caller_info(depth=2 + caller_depth_offset)
        if actual_module_name is None:
            actual_module_name = auto_module
        if actual_func_name is None:
            actual_func_name = auto_function

    masked_details = mask_sensitive_data(details) if details else None
            
    log_data = LogEntryCreate(
        level=level,
        message=message,
        source=source,
        module=actual_module_name,
        function=actual_func_name,
        user_id=user_id,
        device_id=device_id,
        request_id=request_id,
        details=masked_details # Use masked details
    )
    try:
        await crud_logs.create_log_entry(db, log_data)
    except Exception as e:
        # 如果資料庫日誌記錄失敗，使用標準 logger 記錄到控制台/檔案作為備援
        # Ensure log_data for fallback also uses masked_details by re-serializing or constructing a new dict
        fallback_log_dict = log_data.model_dump()
        # No need to explicitly set details again as log_data was created with masked_details
        # fallback_log_dict["details"] = masked_details # This line is redundant

        module_logger.critical(
            f"Failed to save log entry to database: {e}. Original log: {fallback_log_dict}",
            exc_info=True
        )

if __name__ == "__main__":
    # Test cases for mask_sensitive_data
    test_data_1 = {
        "username": "test_user",
        "password": "supersecretpassword",
        "email": "user@example.com",
        "auth_token": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "refresh_token": "defdefdefdefdefdefdefdefdefdefdefdefdefdefdefdefdefdef"
        }
    }
    print(f"Original 1: {test_data_1}")
    print(f"Masked 1: {mask_sensitive_data(test_data_1)}")

    test_data_2 = {
        "config": {
            "api_key": "abcdef1234567890abcdef1234567890",
            "SECRET_KEY": "another-very-long-secret-key-to-be-masked",
            "MONGODB_URL": "mongodb://user:password123@host:port/db?options"
        },
        "other_info": "this is fine"
    }
    print(f"Original 2: {test_data_2}")
    print(f"Masked 2: {mask_sensitive_data(test_data_2)}")

    test_data_3 = {
        "user_list": [
            {"id": 1, "credentials": {"token": "user1_token_value_long_enough"}},
            {"id": 2, "password": "user2_password"}
        ],
        "GOOGLE_API_KEY": "AIzaSyCHappyKey12345VeryLongKeyABCXYZ"
    }
    print(f"Original 3: {test_data_3}")
    print(f"Masked 3: {mask_sensitive_data(test_data_3)}")

    test_data_4 = {
        "short_api_key": "short", # Will be fully masked by mask_string_part
        "normal_key": "this_is_a_normal_key_but_targetted",
        "MONGODB_URL_no_pass": "mongodb://user@host:port/db?options"
    }
    # Add normal_key to STRING_MASK_TARGET_KEYS for this test
    STRING_MASK_TARGET_KEYS.append("normal_key")
    SENSITIVE_KEYS.append("short_api_key") # Ensure it's considered sensitive
    SENSITIVE_KEYS.append("normal_key")

    print(f"Original 4: {test_data_4}")
    print(f"Masked 4: {mask_sensitive_data(test_data_4)}")

    test_data_5 = {
        "nested_list": [
            [{"password": "nested_password_1"}],
            {"details": {"secret": "deep_secret"}}
        ]
    }
    print(f"Original 5: {test_data_5}")
    print(f"Masked 5: {mask_sensitive_data(test_data_5)}")

    test_data_6 = "just a string"
    print(f"Original 6: {test_data_6}")
    print(f"Masked 6: {mask_sensitive_data(test_data_6)}")

    test_data_7 = None
    print(f"Original 7: {test_data_7}")
    print(f"Masked 7: {mask_sensitive_data(test_data_7)}")

    test_data_8 = {
        "api_key": "apikeyprefix1234567890apikey" # Test mask_string_part
    }
    print(f"Original 8: {test_data_8}")
    print(f"Masked 8: {mask_sensitive_data(test_data_8)}")