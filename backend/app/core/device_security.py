"""
Device Security 工具
用於生成和驗證裝置指紋、Token 等安全相關功能
"""

import hashlib
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from uuid import UUID

from .config import settings


# Device Token 的配置
DEVICE_TOKEN_EXPIRE_DAYS = 30  # Device Token 有效期 30 天
REFRESH_TOKEN_EXPIRE_DAYS = 90  # Refresh Token 有效期 90 天
PAIRING_TOKEN_EXPIRE_MINUTES = 5  # 配對 Token 有效期 5 分鐘


def generate_device_id(user_id: UUID, device_fingerprint: str) -> str:
    """
    生成唯一的裝置 ID
    
    Args:
        user_id: 用戶 ID
        device_fingerprint: 裝置指紋
        
    Returns:
        裝置 ID（SHA256 hash）
    """
    data = f"{user_id}:{device_fingerprint}:{secrets.token_hex(16)}"
    return hashlib.sha256(data.encode()).hexdigest()


def generate_refresh_token() -> str:
    """
    生成 Refresh Token
    
    Returns:
        安全的隨機 Refresh Token
    """
    return secrets.token_urlsafe(64)


def generate_pairing_token(user_id: UUID) -> tuple[str, datetime]:
    """
    生成配對 Token（臨時，5分鐘有效）
    
    Args:
        user_id: 用戶 ID
        
    Returns:
        (pairing_token, expires_at)
    """
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PAIRING_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": str(user_id),
        "type": "pairing",
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16)  # Unique ID for this token
    }
    
    pairing_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return pairing_token, expires_at


def verify_pairing_token(pairing_token: str) -> Optional[UUID]:
    """
    驗證配對 Token
    
    Args:
        pairing_token: 配對 Token
        
    Returns:
        用戶 ID（如果驗證成功），否則 None
    """
    try:
        payload = jwt.decode(
            pairing_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # 檢查 Token 類型
        if payload.get("type") != "pairing":
            return None
        
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        
        return UUID(user_id_str)
        
    except (JWTError, ValueError):
        return None


def create_device_token(
    user_id: UUID,
    device_id: str,
    device_name: str
) -> tuple[str, datetime]:
    """
    創建 Device Token
    
    Args:
        user_id: 用戶 ID
        device_id: 裝置 ID
        device_name: 裝置名稱
        
    Returns:
        (device_token, expires_at)
    """
    expires_at = datetime.now(timezone.utc) + timedelta(days=DEVICE_TOKEN_EXPIRE_DAYS)
    
    payload = {
        "sub": str(user_id),
        "device_id": device_id,
        "device_name": device_name,
        "type": "device",
        "exp": expires_at,
        "iat": datetime.now(timezone.utc)
    }
    
    device_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return device_token, expires_at


def verify_device_token(device_token: str) -> Optional[Dict[str, Any]]:
    """
    驗證 Device Token
    
    Args:
        device_token: Device Token
        
    Returns:
        Token payload（如果驗證成功），否則 None
    """
    try:
        payload = jwt.decode(
            device_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # 檢查 Token 類型
        if payload.get("type") != "device":
            return None
        
        return payload
        
    except JWTError:
        return None


def generate_qr_data(pairing_token: str, server_url: Optional[str] = None) -> str:
    """
    生成 QR Code 數據（優化版本 - 簡化數據以減少 QR Code 密度）
    
    Args:
        pairing_token: 配對 Token
        server_url: 服務器 URL（可選）
        
    Returns:
        QR Code 數據（JSON 字符串）
    """
    qr_data = {
        "type": "sortify_mobile_pairing",
        "pairing_token": pairing_token
    }
    
    # 只在需要時添加 server_url（通常手機端使用相同域名）
    # if server_url and server_url != "http://localhost:8000":
    #     qr_data["server_url"] = server_url
    
    return json.dumps(qr_data, separators=(',', ':'))  # 使用緊湊格式，不加空格


def parse_qr_data(qr_data_str: str) -> Optional[Dict[str, Any]]:
    """
    解析 QR Code 數據
    
    Args:
        qr_data_str: QR Code 數據字符串
        
    Returns:
        解析後的數據（如果成功），否則 None
    """
    try:
        data = json.loads(qr_data_str)
        
        # 驗證必要字段
        if (data.get("type") == "sortify_mobile_pairing" and
            "pairing_token" in data and
            "server_url" in data):
            return data
        
        return None
        
    except (json.JSONDecodeError, TypeError):
        return None


def generate_device_fingerprint(
    user_agent: str,
    screen_resolution: Optional[str] = None,
    platform: Optional[str] = None
) -> str:
    """
    生成裝置指紋（客戶端應該調用這個邏輯）
    
    Args:
        user_agent: User-Agent 字符串
        screen_resolution: 屏幕解析度（例如："1920x1080"）
        platform: 平台信息（例如："iOS"、"Android"）
        
    Returns:
        裝置指紋（SHA256 hash）
    """
    components = [user_agent]
    
    if screen_resolution:
        components.append(screen_resolution)
    
    if platform:
        components.append(platform)
    
    fingerprint_data = "|".join(components)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()


def is_device_fingerprint_changed(
    stored_fingerprint: str,
    current_fingerprint: str,
    threshold: float = 0.8
) -> bool:
    """
    檢查裝置指紋是否發生顯著變化
    
    Args:
        stored_fingerprint: 儲存的裝置指紋
        current_fingerprint: 當前裝置指紋
        threshold: 相似度閾值（0-1）
        
    Returns:
        True 如果發生顯著變化
    """
    # 簡單的比較：如果完全不同則認為變化
    # 在實際應用中，可以使用更複雜的相似度算法
    return stored_fingerprint != current_fingerprint


def validate_device_info(
    device_name: str,
    device_fingerprint: str
) -> tuple[bool, Optional[str]]:
    """
    驗證裝置信息的合法性
    
    Args:
        device_name: 裝置名稱
        device_fingerprint: 裝置指紋
        
    Returns:
        (is_valid, error_message)
    """
    if not device_name or len(device_name.strip()) == 0:
        return False, "裝置名稱不能為空"
    
    if len(device_name) > 100:
        return False, "裝置名稱過長（最多100個字符）"
    
    if not device_fingerprint or len(device_fingerprint) != 64:  # SHA256 hash length
        return False, "無效的裝置指紋"
    
    return True, None

