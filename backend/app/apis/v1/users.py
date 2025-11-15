from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Request
from typing import List

from ...models.user_models import ConnectedDevice, User # Import User model
from ...crud.crud_users import crud_devices
from ...dependencies import get_db
from ...core.security import get_current_active_user # Import authentication dependency
from motor.motor_asyncio import AsyncIOMotorDatabase
from ...core.logging_utils import log_event
from ...models.log_models import LogLevel
from ...core.logging_decorators import log_api_operation

router = APIRouter()

@router.post("/", response_model=ConnectedDevice, status_code=status.HTTP_201_CREATED)
@log_api_operation(operation_name="註冊/更新設備", log_success=True)
async def register_or_update_device(
    request: Request,
    device: ConnectedDevice = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """註冊一個新裝置或更新現有裝置的資訊與活動狀態。"""
    device.user_id = current_user.id
    
    created_device = await crud_devices.create_or_update(db, device_data=device)
    if not created_device:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="無法創建或更新裝置")
    
    return created_device

@router.get("/", response_model=List[ConnectedDevice])
@log_api_operation(operation_name="獲取設備列表", log_success=True, success_level=LogLevel.DEBUG)
async def get_connected_devices(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0, description="跳過查詢結果的數量"),
    limit: int = Query(10, ge=1, le=100, description="返回查詢結果的最大數量"),
    active_only: bool = Query(False, description="是否只返回活動中的裝置"),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """獲取當前使用者已連接裝置的列表，支援分頁和篩選活動裝置。"""
    devices = await crud_devices.get_all(db, skip=skip, limit=limit, active_only=active_only, user_id=current_user.id)
    return devices

@router.get("/{device_id}", response_model=ConnectedDevice)
@log_api_operation(operation_name="獲取設備詳情", log_success=True, success_level=LogLevel.DEBUG)
async def get_device_info(
    request: Request,
    device_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """根據裝置 ID 獲取特定裝置的詳細資訊。"""
    device = await crud_devices.get_by_id(db, device_id=device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {device_id} 的裝置不存在")
    
    if device.user_id != current_user.id:
        # 保留權限檢查日誌（安全審計）
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"授權失敗: 使用者 {current_user.username} 嘗試訪問不屬於自己的裝置 {device_id}", 
            source="users_api.get_device", 
            user_id=str(current_user.id), 
            device_id=device_id
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權訪問此裝置")

    return device

@router.post("/{device_id}/disconnect", response_model=ConnectedDevice)
@log_api_operation(operation_name="斷開設備", log_success=True)
async def disconnect_device(
    request: Request,
    device_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """將特定裝置的狀態設為非活動（邏輯斷開）。"""
    existing_device = await crud_devices.get_by_id(db, device_id=device_id)
    if not existing_device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {device_id} 的裝置不存在")

    if existing_device.user_id != current_user.id:
        # 保留權限檢查日誌
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"授權失敗: 使用者 {current_user.username} 嘗試斷開不屬於自己的裝置 {device_id}", 
            source="users_api.disconnect_device", 
            user_id=str(current_user.id), 
            device_id=device_id
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權操作此裝置")

    device = await crud_devices.deactivate(db, device_id=device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法停用 ID 為 {device_id} 的裝置")
    
    return device

@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
@log_api_operation(operation_name="移除設備", log_success=True)
async def remove_device_from_records(
    request: Request,
    device_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """從資料庫中永久移除特定裝置的記錄。"""
    existing_device = await crud_devices.get_by_id(db, device_id=device_id)
    if not existing_device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {device_id} 的裝置不存在，無法刪除")

    if existing_device.user_id != current_user.id:
        # 保留權限檢查日誌
        await log_event(
            db=db, 
            level=LogLevel.WARNING, 
            message=f"授權失敗: 使用者 {current_user.username} 嘗試移除不屬於自己的裝置 {device_id}", 
            source="users_api.remove_device", 
            user_id=str(current_user.id), 
            device_id=device_id
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權刪除此裝置")

    deleted = await crud_devices.remove(db, device_id=device_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法刪除 ID 為 {device_id} 的裝置，或裝置已被移除")
    
    return