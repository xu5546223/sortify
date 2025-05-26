import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock # 引入 AsyncMock

from app.models import SettingsData, ConnectionInfo, TunnelStatus, UpdatableSettingsData
from app.core.config import settings as app_env_settings # 用於獲取預設值

# System API 路由前綴
SYSTEM_API_PREFIX = "/api/v1/system"

def test_get_system_settings_default(client: TestClient):
    """測試在資料庫中無設定時，GET /settings 返回預設設定。"""
    # 模擬 crud_settings.get_system_settings 返回從環境變數讀取的設定
    # 注意：這裡的模擬路徑需要是 API 檔案中實際 import crud_settings 的路徑
    with patch("app.apis.v1.system.crud_settings.get_system_settings", new_callable=AsyncMock) as mock_get:
        # 模擬從 .env 或預設 Pydantic 設定返回
        mock_response = SettingsData(
            ai_api_key="********" + app_env_settings.AI_API_KEY[-4:] if app_env_settings.AI_API_KEY else None,
            ai_max_output_tokens=app_env_settings.AI_MAX_OUTPUT_TOKENS
        )
        mock_get.return_value = mock_response

        response = client.get(f"{SYSTEM_API_PREFIX}/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["ai_max_output_tokens"] == app_env_settings.AI_MAX_OUTPUT_TOKENS
        if app_env_settings.AI_API_KEY:
            assert data["ai_api_key"].endswith(app_env_settings.AI_API_KEY[-4:])
        else:
            assert data["ai_api_key"] is None
        assert mock_get.called

def test_get_system_settings_from_db(client: TestClient):
    """測試 GET /settings 從資料庫獲取設定。"""
    with patch("app.apis.v1.system.crud_settings.get_system_settings", new_callable=AsyncMock) as mock_get:
        db_settings = SettingsData(ai_api_key="db_key_****", ai_max_output_tokens=1024)
        mock_get.return_value = db_settings

        response = client.get(f"{SYSTEM_API_PREFIX}/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["ai_api_key"] == "db_key_****"
        assert data["ai_max_output_tokens"] == 1024
        assert mock_get.called

def test_update_system_settings(client: TestClient):
    """測試 POST /settings 更新設定。"""
    with patch("app.apis.v1.system.crud_settings.update_system_settings", new_callable=AsyncMock) as mock_update:
        update_payload = UpdatableSettingsData(ai_api_key="new_key", ai_max_output_tokens=2048)
        # 模擬更新成功後返回的設定
        updated_settings_response = SettingsData(ai_api_key="new_key_****", ai_max_output_tokens=2048)
        mock_update.return_value = updated_settings_response

        response = client.post(f"{SYSTEM_API_PREFIX}/settings", json=update_payload.model_dump())
        assert response.status_code == 200
        data = response.json()
        assert data["ai_api_key"] == "new_key_****"
        assert data["ai_max_output_tokens"] == 2048
        assert mock_update.called

def test_get_connection_info(client: TestClient):
    """測試 GET /connection-info。"""
    # crud_settings.get_connection_info 目前返回模擬數據
    with patch("app.apis.v1.system.crud_settings.get_connection_info", new_callable=AsyncMock) as mock_get_conn:
        mock_response_data = ConnectionInfo(
            qr_code_image="https://example.com/qr.png", 
            pairing_code="ABCDEF", 
            server_url="http://testserver.com"
        )
        mock_get_conn.return_value = mock_response_data
        
        response = client.get(f"{SYSTEM_API_PREFIX}/connection-info")
        assert response.status_code == 200
        data = response.json()
        assert data["qr_code_image"] == "https://example.com/qr.png"
        assert data["pairing_code"] == "ABCDEF"
        assert data["server_url"] == "http://testserver.com"
        assert mock_get_conn.called

def test_refresh_connection_info(client: TestClient):
    """測試 POST /connection-info/refresh。"""
    with patch("app.apis.v1.system.crud_settings.refresh_connection_info", new_callable=AsyncMock) as mock_refresh_conn:
        mock_response_data = ConnectionInfo(
            qr_code_image="https://example.com/new_qr.png", 
            pairing_code="GHIJKL", 
            server_url="http://new_testserver.com"
        )
        mock_refresh_conn.return_value = mock_response_data

        response = client.post(f"{SYSTEM_API_PREFIX}/connection-info/refresh")
        assert response.status_code == 200
        data = response.json()
        assert data["qr_code_image"] == "https://example.com/new_qr.png"
        assert data["pairing_code"] == "GHIJKL"
        assert mock_refresh_conn.called

def test_get_tunnel_status(client: TestClient):
    """測試 GET /tunnel-status。"""
    with patch("app.apis.v1.system.crud_settings.get_tunnel_status", new_callable=AsyncMock) as mock_get_tunnel:
        mock_response_data = TunnelStatus(is_active=True, url="https://my-tunnel.example.com", error_message=None)
        mock_get_tunnel.return_value = mock_response_data

        response = client.get(f"{SYSTEM_API_PREFIX}/tunnel-status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] == True
        assert data["url"] == "https://my-tunnel.example.com"
        assert mock_get_tunnel.called 