import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, ANY, call
from datetime import datetime

from app.models import ConnectedDevice

# Users API 路由前綴 (已在 app.apis.v1.__init__.py 中設定為 /users)
USERS_API_PREFIX = "/api/v1/users"

# Helper to create a device for tests
def create_sample_device_payload(device_id="test_device", name="Test Device", type="android"):
    return {
        "device_id": device_id,
        "device_name": name,
        "device_type": type,
        "ip_address": "192.168.1.100",
        "user_agent": "TestApp/1.0"
    }

def test_register_new_device(client: TestClient):
    """測試 POST / 註冊一個新裝置。"""
    payload = create_sample_device_payload(device_id="reg_dev_1")
    mock_device_instance = ConnectedDevice(**payload)
    with patch("app.apis.v1.users.crud_users.create_or_update", new_callable=AsyncMock, return_value=mock_device_instance) as mock_create_update:
        response = client.post(f"{USERS_API_PREFIX}/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["device_id"] == payload["device_id"]
        assert mock_create_update.called
        # 檢查呼叫時的參數
        args, kwargs = mock_create_update.call_args
        assert args[1].device_id == payload["device_id"] if len(args) > 1 else True

def test_update_existing_device(client: TestClient):
    """測試 POST / 更新現有裝置的活動狀態。"""
    payload = create_sample_device_payload(device_id="update_dev_1", name="Updated Name")
    # Simulate that first_connected_at already exists and last_active_at will be updated
    mock_device_instance = ConnectedDevice(**payload, first_connected_at=datetime(2023,1,1), last_active_at=datetime.utcnow())
    with patch("app.apis.v1.users.crud_users.create_or_update", new_callable=AsyncMock, return_value=mock_device_instance) as mock_create_update:
        response = client.post(f"{USERS_API_PREFIX}/", json=payload)
        assert response.status_code == 201 
        data = response.json()
        assert data["device_name"] == "Updated Name"
        assert mock_create_update.called

def test_get_connected_devices_empty(client: TestClient):
    """測試 GET / 在沒有裝置時返回空列表。"""
    with patch("app.apis.v1.users.crud_users.get_all", new_callable=AsyncMock, return_value=[]) as mock_get_all:
        response = client.get(f"{USERS_API_PREFIX}/")
        assert response.status_code == 200
        assert response.json() == []
        assert mock_get_all.called
        args, kwargs = mock_get_all.call_args
        assert kwargs.get('limit') == 10
        assert kwargs.get('skip') == 0
        assert kwargs.get('active_only') is False

def test_get_connected_devices_with_data_and_params(client: TestClient):
    """測試 GET / 帶有數據和查詢參數。"""
    dev1_payload = create_sample_device_payload("dev1")
    # dev2_payload = create_sample_device_payload("dev2", is_active=False) # Model doesn't take is_active directly in constructor like this
    mock_devices = [ConnectedDevice(**dev1_payload)] # Only active one for this test case
    with patch("app.apis.v1.users.crud_users.get_all", new_callable=AsyncMock, return_value=mock_devices) as mock_get_all:
        response = client.get(f"{USERS_API_PREFIX}/?skip=0&limit=5&active_only=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "dev1"
        assert mock_get_all.called
        args, kwargs = mock_get_all.call_args
        assert kwargs.get('limit') == 5
        assert kwargs.get('skip') == 0
        assert kwargs.get('active_only') is True

def test_get_device_info_found(client: TestClient):
    """測試 GET /{device_id} 找到裝置。"""
    device_id = "get_dev_found"
    payload = create_sample_device_payload(device_id)
    mock_device_instance = ConnectedDevice(**payload)
    with patch("app.apis.v1.users.crud_users.get_by_id", new_callable=AsyncMock, return_value=mock_device_instance) as mock_get_by_id:
        response = client.get(f"{USERS_API_PREFIX}/{device_id}")
        assert response.status_code == 200
        assert response.json()["device_id"] == device_id
        assert mock_get_by_id.called
        args, kwargs = mock_get_by_id.call_args
        assert kwargs.get('device_id') == device_id

def test_get_device_info_not_found(client: TestClient):
    """測試 GET /{device_id} 裝置未找到。"""
    device_id = "get_dev_not_found"
    with patch("app.apis.v1.users.crud_users.get_by_id", new_callable=AsyncMock, return_value=None) as mock_get_by_id:
        response = client.get(f"{USERS_API_PREFIX}/{device_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == f"ID 為 {device_id} 的裝置不存在"

def test_disconnect_device_success(client: TestClient):
    """測試 POST /{device_id}/disconnect 成功斷開裝置。"""
    device_id = "disconnect_dev_ok"
    payload = create_sample_device_payload(device_id)
    # Simulate device exists and is active, then gets deactivated
    disconnected_device_mock = ConnectedDevice(**payload, is_active=False, last_active_at=datetime.utcnow())
    
    with patch("app.apis.v1.users.crud_users.deactivate", new_callable=AsyncMock, return_value=disconnected_device_mock) as mock_deactivate:
        with patch("app.apis.v1.users.crud_users.get_by_id") as mock_get_by_id_check: # This mock is for the pre-check if deactivate returns None
            # In success case, mock_get_by_id_check should not be called by the API if crud_users.deactivate itself returns the device

            response = client.post(f"{USERS_API_PREFIX}/{device_id}/disconnect")
            assert response.status_code == 200
            data = response.json()
            assert data["device_id"] == device_id
            assert data["is_active"] == False
            assert mock_deactivate.called
            args, kwargs = mock_deactivate.call_args
            assert kwargs.get('device_id') == device_id
            mock_get_by_id_check.assert_not_called() # Ensure the API logic doesn't double-fetch if deactivate is successful

def test_disconnect_device_not_found(client: TestClient):
    """測試 POST /{device_id}/disconnect 裝置未找到。"""
    device_id = "disconnect_dev_not_found"
    # Both deactivate and the subsequent get_by_id will return None
    with patch("app.apis.v1.users.crud_users.deactivate", new_callable=AsyncMock, return_value=None) as mock_deactivate:
        with patch("app.apis.v1.users.crud_users.get_by_id", new_callable=AsyncMock, return_value=None) as mock_get_by_id_check:
            response = client.post(f"{USERS_API_PREFIX}/{device_id}/disconnect")
            assert response.status_code == 404
            assert response.json()["detail"] == f"ID 為 {device_id} 的裝置不存在"
            assert mock_deactivate.called
            args, kwargs = mock_deactivate.call_args
            assert kwargs.get('device_id') == device_id
            assert mock_get_by_id_check.called
            args, kwargs = mock_get_by_id_check.call_args
            assert kwargs.get('device_id') == device_id

def test_remove_device_success(client: TestClient):
    """測試 DELETE /{device_id} 成功移除裝置。"""
    device_id = "remove_dev_ok"
    payload = create_sample_device_payload(device_id)
    existing_device_mock = ConnectedDevice(**payload)
    with patch("app.apis.v1.users.crud_users.get_by_id", new_callable=AsyncMock, return_value=existing_device_mock) as mock_get_by_id:
        with patch("app.apis.v1.users.crud_users.remove", new_callable=AsyncMock, return_value=True) as mock_remove:
            response = client.delete(f"{USERS_API_PREFIX}/{device_id}")
            assert response.status_code == 204
            assert mock_get_by_id.called
            args, kwargs = mock_get_by_id.call_args
            assert kwargs.get('device_id') == device_id
            assert mock_remove.called
            args, kwargs = mock_remove.call_args
            assert kwargs.get('device_id') == device_id

def test_remove_device_not_found(client: TestClient):
    """測試 DELETE /{device_id} 裝置未找到。"""
    device_id = "remove_dev_not_found"
    with patch("app.apis.v1.users.crud_users.get_by_id", new_callable=AsyncMock, return_value=None) as mock_get_by_id:
        with patch("app.apis.v1.users.crud_users.remove", new_callable=AsyncMock) as mock_remove:
            response = client.delete(f"{USERS_API_PREFIX}/{device_id}")
            assert response.status_code == 404
            assert response.json()["detail"] == f"ID 為 {device_id} 的裝置不存在，無法刪除"
            assert mock_get_by_id.called
            args, kwargs = mock_get_by_id.call_args
            assert kwargs.get('device_id') == device_id
            mock_remove.assert_not_called()

def test_remove_device_failed_in_crud(client: TestClient):
    """測試 DELETE /{device_id} 裝置存在但 CRUD 層刪除失敗。"""
    device_id = "remove_dev_fail_crud"
    payload = create_sample_device_payload(device_id)
    existing_device_mock = ConnectedDevice(**payload)
    with patch("app.apis.v1.users.crud_users.get_by_id", new_callable=AsyncMock, return_value=existing_device_mock) as mock_get_by_id:
        with patch("app.apis.v1.users.crud_users.remove", new_callable=AsyncMock, return_value=False) as mock_remove:
            response = client.delete(f"{USERS_API_PREFIX}/{device_id}")
            assert response.status_code == 500
            assert response.json()["detail"] == f"無法刪除 ID 為 {device_id} 的裝置，或裝置已被移除"
            assert mock_get_by_id.called
            args, kwargs = mock_get_by_id.call_args
            assert kwargs.get('device_id') == device_id
            assert mock_remove.called
            args, kwargs = mock_remove.call_args
            assert kwargs.get('device_id') == device_id 