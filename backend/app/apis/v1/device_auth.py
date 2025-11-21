"""
Device Authentication API
處理手機端裝置認證和管理
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.db.mongodb_utils import get_db
from app.models.user_models import User
from app.models.device_token_models import (
    PairingTokenResponse,
    DevicePairRequest,
    DevicePairResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    DeviceListResponse,
    DeviceRevokeResponse,
    DeviceToken,
    UpdateDeviceNameRequest,
    UpdateDeviceNameResponse
)
from app.core.security import get_current_active_user, get_current_admin_user, create_access_token
from app.core.device_security import (
    generate_pairing_token,
    verify_pairing_token,
    create_device_token,
    verify_device_token,
    generate_qr_data,
    validate_device_info,
    DEVICE_TOKEN_EXPIRE_DAYS,
    REFRESH_TOKEN_EXPIRE_DAYS
)
from app.crud.crud_device_tokens import crud_device_tokens
from app.core.logging_utils import log_event, LogLevel


router = APIRouter()


@router.post("/generate-qr", response_model=PairingTokenResponse, summary="生成配對 QR Code")
async def generate_qr_code(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    生成配對 QR Code（電腦端使用）
    
    - 生成一個臨時配對 Token（5分鐘有效）
    - 返回 QR Code 數據，供前端生成 QR Code 圖像
    """
    try:
        # 生成配對 Token
        pairing_token, expires_at = generate_pairing_token(current_user.id)
        
        # 生成 QR Code 數據
        server_url = str(request.base_url).rstrip('/')
        qr_data = generate_qr_data(pairing_token, server_url)
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 生成配對 QR Code",
            source="api.device_auth.generate_qr",
            user_id=str(current_user.id),
            details={"expires_at": expires_at.isoformat()}
        )
        
        return PairingTokenResponse(
            pairing_token=pairing_token,
            qr_data=qr_data,
            expires_at=expires_at
        )
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"生成配對 QR Code 失敗: {str(e)}",
            source="api.device_auth.generate_qr",
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="生成配對 QR Code 失敗"
        )


@router.post("/pair-device", response_model=DevicePairResponse, summary="配對新裝置")
async def pair_device(
    request: Request,
    pair_request: DevicePairRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    配對新裝置（手機端使用）
    
    - 驗證配對 Token
    - 創建 Device Token 和 Refresh Token
    - 返回長效認證 Token
    """
    try:
        print("\n========== 開始配對裝置 ==========")
        print(f"📱 裝置名稱: {pair_request.device_name}")
        print(f"🔑 配對 Token 長度: {len(pair_request.pairing_token)}")
        print(f"🆔 裝置指紋長度: {len(pair_request.device_fingerprint)}")
        
        # 驗證配對 Token
        print("🔍 步驟 1: 驗證配對 Token...")
        user_id = verify_pairing_token(pair_request.pairing_token)
        print(f"✅ 配對 Token 驗證結果: user_id={user_id}")
        if not user_id:
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="無效的配對 Token",
                source="api.device_auth.pair_device",
                details={"device_name": pair_request.device_name}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無效或已過期的配對 Token"
            )
        
        # 驗證裝置信息
        is_valid, error_message = validate_device_info(
            pair_request.device_name,
            pair_request.device_fingerprint
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        # 檢查是否已經配對過相同的裝置
        existing_device = await crud_device_tokens.get_device_token_by_device_id(
            db=db,
            device_id=pair_request.device_fingerprint[:64]  # 使用前64個字符作為 device_id
        )
        
        if existing_device and existing_device.is_active:
            # 如果已存在活躍的裝置，更新最後使用時間
            client_ip = request.client.host if request.client else None
            await crud_device_tokens.update_last_used(
                db=db,
                device_id=existing_device.device_id,
                last_ip=client_ip
            )
            
            # 生成新的 Device Token
            device_token, token_expires_at = create_device_token(
                user_id=user_id,
                device_id=existing_device.device_id,
                device_name=pair_request.device_name
            )
            
            return DevicePairResponse(
                device_token=device_token,
                refresh_token=existing_device.refresh_token,
                device_id=existing_device.device_id,
                expires_at=token_expires_at
            )
        
        # 創建新的裝置記錄
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        client_ip = request.client.host if request.client else None
        
        device_token_record = await crud_device_tokens.create_device_token(
            db=db,
            user_id=user_id,
            device_name=pair_request.device_name,
            device_fingerprint=pair_request.device_fingerprint,
            expires_at=expires_at,
            last_ip=client_ip
        )
        
        # 生成 Device Token（JWT）
        device_token, token_expires_at = create_device_token(
            user_id=user_id,
            device_id=device_token_record.device_id,
            device_name=pair_request.device_name
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"新裝置配對成功: {pair_request.device_name}",
            source="api.device_auth.pair_device",
            user_id=str(user_id),
            details={
                "device_id": device_token_record.device_id,
                "device_name": pair_request.device_name
            }
        )
        
        return DevicePairResponse(
            device_token=device_token,
            refresh_token=device_token_record.refresh_token,
            device_id=device_token_record.device_id,
            expires_at=token_expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"\n❌ 裝置配對失敗！")
        print(f"錯誤類型: {type(e).__name__}")
        print(f"錯誤信息: {str(e)}")
        print(f"完整堆棧:\n{error_detail}")
        
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"裝置配對失敗: {str(e)}",
            source="api.device_auth.pair_device",
            details={"error_type": type(e).__name__, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"裝置配對失敗: {str(e)}"
        )


@router.post("/refresh", response_model=RefreshTokenResponse, summary="刷新 Access Token")
async def refresh_access_token(
    request: Request,
    refresh_request: RefreshTokenRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    使用 Refresh Token 刷新 Access Token
    
    - 驗證 Refresh Token
    - 生成新的 Access Token
    """
    try:
        # 驗證 Refresh Token
        device_record = await crud_device_tokens.get_device_token_by_refresh_token(
            db=db,
            refresh_token=refresh_request.refresh_token
        )
        
        if not device_record:
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="無效的 Refresh Token",
                source="api.device_auth.refresh"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="無效的 Refresh Token"
            )
        
        # 檢查裝置 ID 是否匹配
        if device_record.device_id != refresh_request.device_id:
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="裝置 ID 不匹配",
                source="api.device_auth.refresh",
                user_id=str(device_record.user_id),
                details={
                    "expected_device_id": device_record.device_id,
                    "provided_device_id": refresh_request.device_id
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="裝置驗證失敗"
            )
        
        # 檢查裝置是否已停用
        if not device_record.is_active:
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="嘗試使用已停用的裝置刷新 Token",
                source="api.device_auth.refresh",
                user_id=str(device_record.user_id),
                details={"device_id": device_record.device_id}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="裝置已被停用"
            )
        
        # 檢查是否過期
        # 確保 expires_at 有時區信息
        expires_at = device_record.expires_at
        if expires_at.tzinfo is None:
            # 如果沒有時區信息，假設是 UTC
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < datetime.now(timezone.utc):
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="Refresh Token 已過期",
                source="api.device_auth.refresh",
                user_id=str(device_record.user_id),
                details={"device_id": device_record.device_id}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh Token 已過期，請重新配對裝置"
            )
        
        # 生成新的 Access Token
        access_token_expires = timedelta(minutes=60)  # 1 小時
        access_token = create_access_token(
            subject=str(device_record.user_id),
            expires_delta=access_token_expires
        )
        
        # 更新最後使用時間
        client_ip = request.client.host if request.client else None
        await crud_device_tokens.update_last_used(
            db=db,
            device_id=device_record.device_id,
            last_ip=client_ip
        )
        
        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"刷新 Token 失敗: {str(e)}",
            source="api.device_auth.refresh"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刷新 Token 失敗"
        )


@router.get("/devices", response_model=DeviceListResponse, summary="獲取已配對裝置列表")
async def list_devices(
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取當前用戶所有已配對的裝置
    
    - 只顯示活躍的裝置
    - 按最後使用時間排序
    """
    try:
        devices = await crud_device_tokens.get_user_devices(
            db=db,
            user_id=current_user.id,
            include_inactive=False
        )
        
        device_list = [
            DeviceToken(
                id=device.id,
                device_id=device.device_id,
                device_name=device.device_name,
                user_id=device.user_id,
                created_at=device.created_at,
                last_used=device.last_used,
                expires_at=device.expires_at,
                is_active=device.is_active
            )
            for device in devices
        ]
        
        return DeviceListResponse(
            devices=device_list,
            total=len(device_list)
        )
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"\n❌ 獲取裝置列表失敗！")
        print(f"錯誤類型: {type(e).__name__}")
        print(f"錯誤信息: {str(e)}")
        print(f"完整堆棧:\n{error_detail}")
        
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取裝置列表失敗: {str(e)}",
            source="api.device_auth.list_devices",
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="獲取裝置列表失敗"
        )


@router.patch("/devices/{device_id}", response_model=UpdateDeviceNameResponse, summary="更新裝置名稱")
async def update_device_name(
    device_id: str,
    request: UpdateDeviceNameRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    更新指定裝置的名稱
    
    - 只能更新自己的裝置
    - 名稱長度限制：1-50 個字符
    """
    try:
        # Pydantic 已經驗證了名稱長度，這裡只需要 trim
        device_name = request.device_name.strip()
        
        # 檢查裝置是否存在且屬於當前用戶
        device = await crud_device_tokens.get_device_token_by_device_id(
            db=db,
            device_id=device_id
        )
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="裝置不存在"
            )
        
        if str(device.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權限修改此裝置"
            )
        
        # 更新裝置名稱
        collection = db["device_tokens"]
        result = await collection.update_one(
            {"device_id": device_id},
            {"$set": {"device_name": device_name}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新裝置名稱失敗"
            )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 更新了裝置名稱",
            source="api.device_auth.update_device_name",
            user_id=str(current_user.id),
            details={
                "device_id": device_id,
                "old_name": device.device_name,
                "new_name": device_name
            }
        )
        
        return UpdateDeviceNameResponse(
            success=True,
            message="裝置名稱已更新",
            device_name=device_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"更新裝置名稱失敗: {str(e)}",
            source="api.device_auth.update_device_name",
            user_id=str(current_user.id),
            details={"device_id": device_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新裝置名稱失敗"
        )


@router.delete("/devices/{device_id}", response_model=DeviceRevokeResponse, summary="撤銷裝置授權")
async def revoke_device(
    device_id: str,
    permanent: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    撤銷（停用）指定裝置的授權
    
    - permanent=False（默認）：軟刪除，保留記錄供審計
    - permanent=True：完全刪除，無法恢復
    - 裝置將無法繼續使用
    - 需要重新配對才能恢復訪問
    """
    try:
        if permanent:
            # 🔥 完全刪除（硬刪除）
            success = await crud_device_tokens.delete_device(
                db=db,
                device_id=device_id,
                user_id=current_user.id
            )
            action = "永久刪除"
            message = "裝置已完全刪除"
        else:
            # 🔒 軟刪除（撤銷）
            success = await crud_device_tokens.revoke_device(
                db=db,
                device_id=device_id,
                user_id=current_user.id
            )
            action = "撤銷"
            message = "裝置授權已撤銷"
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="裝置不存在或已被撤銷"
            )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} {action}了裝置授權 (permanent={permanent})",
            source="api.device_auth.revoke_device",
            user_id=str(current_user.id),
            details={"device_id": device_id, "permanent": permanent}
        )
        
        return DeviceRevokeResponse(
            success=True,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"撤銷裝置授權失敗: {str(e)}",
            source="api.device_auth.revoke_device",
            user_id=str(current_user.id),
            details={"device_id": device_id, "permanent": permanent}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="撤銷裝置授權失敗"
        )


@router.post("/cleanup", summary="清理過期和已撤銷的裝置（管理員）")
async def cleanup_devices(
    cleanup_expired: bool = True,
    cleanup_revoked: bool = True,
    expired_days: int = 90,
    revoked_days: int = 30,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    清理過期和已撤銷的裝置（僅管理員）
    
    - cleanup_expired: 是否清理過期設備
    - cleanup_revoked: 是否清理已撤銷設備
    - expired_days: 過期多少天後刪除（默認90天）
    - revoked_days: 撤銷多少天後刪除（默認30天）
    
    Returns:
        清理的數量統計
    """
    try:
        result = {
            "expired_count": 0,
            "revoked_count": 0,
            "total_count": 0
        }
        
        if cleanup_expired:
            expired_count = await crud_device_tokens.cleanup_expired_tokens(
                db=db,
                days_threshold=expired_days
            )
            result["expired_count"] = expired_count
            result["total_count"] += expired_count
        
        if cleanup_revoked:
            revoked_count = await crud_device_tokens.cleanup_revoked_devices(
                db=db,
                days_threshold=revoked_days
            )
            result["revoked_count"] = revoked_count
            result["total_count"] += revoked_count
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"管理員 {current_user.username} 執行設備清理",
            source="api.device_auth.cleanup_devices",
            user_id=str(current_user.id),
            details={
                "expired_count": result["expired_count"],
                "revoked_count": result["revoked_count"],
                "total_count": result["total_count"],
                "expired_days": expired_days,
                "revoked_days": revoked_days
            }
        )
        
        return {
            "success": True,
            "message": f"清理完成，共刪除 {result['total_count']} 個設備",
            "details": result
        }
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"設備清理失敗: {str(e)}",
            source="api.device_auth.cleanup_devices",
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="設備清理失敗"
        )

