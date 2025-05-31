import logging
from typing import Dict, Any
from copilotkit import CopilotKitRemoteEndpoint, Action as CopilotAction
# 假設 FastAPI app 實例和版本資訊可以從 main 或 config 獲取（如果需要的話）
# from .main import app # 避免循環導入，如果需要 app 的屬性，考慮其他方式傳遞或從 config 讀取

# 獲取一個日誌記錄器實例
# 您可以選擇傳入 main.py 中的 std_logger，或者在這裡重新獲取
# 為了簡單起見，我們先在這裡獲取一個。如果需要與 main.py 一致的日誌行為，則需要調整。
copilot_logger = logging.getLogger(__name__)
if not copilot_logger.hasHandlers():
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

# --- 範例 Action: 從後端獲取專案資訊 ---
async def get_sortify_project_details(category: str) -> Dict[str, Any]:
    """
    一個範例 Action，根據分類從 Sortify 後端獲取專案細節。
    在實際應用中，這裡會包含您的業務邏輯，例如查詢資料庫。
    """
    copilot_logger.info(f"CopilotKit Action 'get_sortify_project_details' called with category: {category}")
    # 注意：如果 Action 需要訪問 app.version 或其他 app 實例的屬性，
    # 您需要找到一種方法來安全地訪問它們，例如通過配置或依賴注入，而不是直接導入 app。
    # 為了演示，我們暫時移除對 app.version 的直接依賴，或者假設它從其他地方獲取。
    # app_version = "0.1.0" # 假設的版本
    # app_description = "Sortify AI Assistant Backend" # 假設的描述
    
    if category.lower() == "status":
        return {"projectName": "Sortify", "status": "進行中", "progress": "75%", "nextMilestone": "使用者身份驗證模組完成"}
    elif category.lower() == "team":
        return {"projectName": "Sortify", "teamSize": 5, "lead": "AI Assistant", "members": ["Developer A", "Developer B"]}
    elif category.lower() == "version":
        # 如果要獲取 app.version，需要一種安全的方式。暫時返回固定值或從配置讀取。
        from .core.config import settings # 假設 settings 可以提供版本信息
        # 這裡假設 settings 有一個 APP_VERSION 和 APP_DESCRIPTION，如果沒有，您需要相應調整
        app_version = getattr(settings, 'APP_VERSION', 'N/A')
        app_description = getattr(settings, 'APP_DESCRIPTION', 'N/A')
        return {"projectName": "Sortify", "version": app_version, "description": app_description}
    else:
        return {"error": f"未知的查詢分類: {category}. 可用分類: status, team, version."}

# 將函式包裝成 CopilotKit Action
sortify_project_action = CopilotAction(
    name="getSortifyProjectInfo", 
    description="從 Sortify 後端獲取特定分類的專案資訊 (例如 'status', 'team', 'version')。",
    parameters=[
        {
            "name": "category",
            "type": "string",
            "description": "要查詢的資訊分類 (例如 'status', 'team', 'version')",
            "required": True,
        }
    ],
    handler=get_sortify_project_details
)

# --- 設定 CopilotKit 遠端端點 ---
python_backend_sdk = CopilotKitRemoteEndpoint(actions=[sortify_project_action])

copilot_logger.info("CopilotKit SDK (python_backend_sdk) initialized in copilot_setup.py") 