from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Request
from typing import List

from ...models.user_models import ConnectedDevice, User # Import User model
from ...crud.crud_users import crud_devices
from ...dependencies import get_db
from ...core.security import get_current_active_user # Import authentication dependency
from motor.motor_asyncio import AsyncIOMotorDatabase
from ...core.logging_utils import log_event
from ...models.log_models import LogLevel

router = APIRouter()

@router.post("/", response_model=ConnectedDevice, status_code=status.HTTP_201_CREATED)
async def register_or_update_device(
    request: Request,
    device: ConnectedDevice = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user) # Add auth dependency
):
    """註冊一個新裝置或更新現有裝置的資訊與活動狀態。"""
    # Ensure the device is associated with the authenticated user
    device.user_id = current_user.id

    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    log_details = {"device_id": device.device_id, "device_name": device.device_name, "is_active": device.is_active, "user_id": str(current_user.id)}
    await log_event(
        db=db, 
        level=LogLevel.DEBUG, 
        message=f"使用者 {current_user.username} 嘗試註冊或更新裝置: {device.device_id}", 
        source="users_api", 
        user_id=str(current_user.id), 
        request_id=request_id_for_log, 
        details=log_details
    )

    try:
        # Pass current_user.id to create_or_update if it needs to verify ownership on update
        # For now, crud_devices.create_or_update will use device.user_id which we just set
        created_device = await crud_devices.create_or_update(db, device_data=device)
        if not created_device:
            await log_event(
                db=db, 
                level=LogLevel.ERROR, 
                message=f"無法創建或更新裝置: {device.device_id} for user {current_user.username}", 
                source="users_api", 
                user_id=str(current_user.id), 
                request_id=request_id_for_log, 
                details=log_details
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="無法創建或更新裝置")
        
        await log_event(
            db=db, 
            level=LogLevel.INFO, 
            message=f"裝置 {device.device_id} 已成功為使用者 {current_user.username} 註冊/更新", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device.device_id, 
            request_id=request_id_for_log, 
            details=created_device.model_dump()
        )
        return created_device
    except Exception as e:
        await log_event(
            db=db, 
            level=LogLevel.ERROR, 
            message=f"註冊/更新裝置 {device.device_id} for user {current_user.username} 時發生錯誤: {str(e)}", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device.device_id, 
            request_id=request_id_for_log, 
            details={**log_details, "error": str(e)}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"處理裝置時發生錯誤: {str(e)}")

@router.get("/", response_model=List[ConnectedDevice])
async def get_connected_devices(
    current_user: User = Depends(get_current_active_user), # Add auth dependency
    skip: int = Query(0, ge=0, description="跳過查詢結果的數量"),
    limit: int = Query(10, ge=1, le=100, description="返回查詢結果的最大數量"),
    active_only: bool = Query(False, description="是否只返回活動中的裝置"),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """獲取當前使用者已連接裝置的列表，支援分頁和篩選活動裝置。"""
    devices = await crud_devices.get_all(db, skip=skip, limit=limit, active_only=active_only, user_id=current_user.id)
    return devices

@router.get("/{device_id}", response_model=ConnectedDevice)
async def get_device_info(
    request: Request,
    device_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user) # Add auth dependency
):
    """根據裝置 ID 獲取特定裝置的詳細資訊。"""
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, 
        level=LogLevel.DEBUG, 
        message=f"使用者 {current_user.username} 嘗試獲取裝置資訊: {device_id}", 
        source="users_api", 
        user_id=str(current_user.id), 
        device_id=device_id, 
        request_id=request_id_for_log
    )
    
    device = await crud_devices.get_by_id(db, device_id=device_id)
    if not device:
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"獲取裝置資訊失敗: ID 為 {device_id} 的裝置不存在 (請求者: {current_user.username})", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {device_id} 的裝置不存在")
    
    if device.user_id != current_user.id:
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"授權失敗: 使用者 {current_user.username} 嘗試訪問不屬於自己的裝置 {device_id}", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權訪問此裝置")

    await log_event(
        db=db, 
        level=LogLevel.DEBUG, 
        message=f"成功為使用者 {current_user.username} 獲取裝置資訊: {device_id}", 
        source="users_api", 
        user_id=str(current_user.id), 
        device_id=device_id, 
        request_id=request_id_for_log, 
        details=device.model_dump()
    )
    return device

@router.post("/{device_id}/disconnect", response_model=ConnectedDevice)
async def disconnect_device(
    request: Request,
    device_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user) # Add auth dependency
):
    """將特定裝置的狀態設為非活動（邏輯斷開）。"""
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, 
        level=LogLevel.DEBUG, 
        message=f"使用者 {current_user.username} 嘗試斷開裝置: {device_id}", 
        source="users_api", 
        user_id=str(current_user.id), 
        device_id=device_id, 
        request_id=request_id_for_log
    )

    existing_device = await crud_devices.get_by_id(db, device_id=device_id)
    if not existing_device:
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"斷開裝置失敗: ID 為 {device_id} 的裝置不存在 (請求者: {current_user.username})", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {device_id} 的裝置不存在")

    if existing_device.user_id != current_user.id:
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"授權失敗: 使用者 {current_user.username} 嘗試斷開不屬於自己的裝置 {device_id}", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權操作此裝置")

    try:
        device = await crud_devices.deactivate(db, device_id=device_id)
        if not device:
            await log_event(
                db=db, 
                level=LogLevel.ERROR, 
                message=f"停用裝置 {device_id} 失敗 (deactivate 返回 None) for user {current_user.username}", 
                source="users_api", 
                user_id=str(current_user.id), 
                device_id=device_id, 
                request_id=request_id_for_log
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法停用 ID 為 {device_id} 的裝置")
        
        await log_event(
            db=db, 
            level=LogLevel.INFO, 
            message=f"裝置 {device_id} 已成功為使用者 {current_user.username} 斷開連接", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log, 
            details=device.model_dump()
        )
        return device
    except Exception as e:
        await log_event(
            db=db, 
            level=LogLevel.ERROR, 
            message=f"斷開裝置 {device_id} for user {current_user.username} 時發生錯誤: {str(e)}", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log, 
            details={"error": str(e)}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"處理斷開裝置時發生錯誤: {str(e)}")

@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device_from_records(
    request: Request,
    device_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user) # Add auth dependency
):
    """從資料庫中永久移除特定裝置的記錄。"""
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, 
        level=LogLevel.DEBUG, 
        message=f"使用者 {current_user.username} 嘗試移除裝置記錄: {device_id}", 
        source="users_api", 
        user_id=str(current_user.id), 
        device_id=device_id, 
        request_id=request_id_for_log
    )

    existing_device = await crud_devices.get_by_id(db, device_id=device_id)
    if not existing_device:
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"移除裝置記錄失敗: ID 為 {device_id} 的裝置不存在 (請求者: {current_user.username})", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {device_id} 的裝置不存在，無法刪除")

    if existing_device.user_id != current_user.id:
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"授權失敗: 使用者 {current_user.username} 嘗試移除不屬於自己的裝置 {device_id}", 
            source="users_api", 
            user_id=str(current_user.id), 
            device_id=device_id, 
            request_id=request_id_for_log
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權刪除此裝置")

    try:
        deleted = await crud_devices.remove(db, device_id=device_id)
        if not deleted:
            await log_event(
                db=db, 
                level=LogLevel.ERROR, 
                message=f"移除裝置 {device_id} 失敗 (remove 返回 False) for user {current_user.username}", 
                source="users_api", 
                user_id=str(current_user.id), 
                device_id=device_id, 
                request_id=request_id_for_log
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法刪除 ID 為 {device_id} 的裝置，或裝置已被移除")
        
        await log_event(
            db=db, 
            level=LogLevel.INFO, 
            message=f"裝置 {device_id} 的記錄已成功從資料庫移除", 
            source="users_api", 
            device_id=device_id, 
            request_id=request_id_for_log
        )
    except Exception as e:
        await log_event(
            db=db, 
            level=LogLevel.ERROR, 
            message=f"移除裝置 {device_id} 時發生錯誤: {str(e)}", 
            source="users_api", 
            device_id=device_id, 
            request_id=request_id_for_log, 
            details={"error": str(e)}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"處理移除裝置時發生錯誤: {str(e)}")
    
    return # FastAPI 會自動處理 204 並返回空回應 