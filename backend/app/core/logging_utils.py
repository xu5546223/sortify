import inspect
from typing import Optional, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.log_models import LogLevel, LogEntryCreate
from ..crud import crud_logs
# 考慮加入標準庫的 logging，用於備份日誌或記錄 logging_utils 本身的錯誤
import logging

# 標準庫 logger，用於 logging_utils.py 內部日誌
module_logger = logging.getLogger(__name__)

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
    """
    actual_module_name = module_name
    actual_func_name = func_name

    if auto_fill_caller_info:
        # 預設情況下，直接調用 log_event 的是第2層堆疊，
        # get_caller_info 內部會再上一層，所以 depth=2 應指向 log_event 的調用者。
        # caller_depth_offset 允許外部調用者根據其封裝層級進行調整。
        auto_module, auto_function = await get_caller_info(depth=2 + caller_depth_offset)
        if actual_module_name is None:
            actual_module_name = auto_module
        if actual_func_name is None:
            actual_func_name = auto_function
            
    log_data = LogEntryCreate(
        level=level,
        message=message,
        source=source,
        module=actual_module_name,
        function=actual_func_name,
        user_id=user_id,
        device_id=device_id,
        request_id=request_id,
        details=details
    )
    try:
        await crud_logs.create_log_entry(db, log_data)
    except Exception as e:
        # 如果資料庫日誌記錄失敗，使用標準 logger 記錄到控制台/檔案作為備援
        module_logger.critical(
            f"Failed to save log entry to database: {e}. Original log: {log_data.model_dump_json()}",
            exc_info=True
        ) 