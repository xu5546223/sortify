from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm # 用於接收 username 和 password
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import timedelta

from ...dependencies import get_db
from ...models.token_models import Token # Token 回應模型
from ...models.user_models import User, UserCreate, UserInDB, UserUpdate, PasswordUpdateIn # <--- 確保 UserUpdate 已導入
from ...models.response_models import MessageResponse # <--- 導入 MessageResponse
from ...crud.crud_users import crud_users # User CRUD 操作
from ...core.security import verify_password, create_access_token, get_current_active_user # 移除 get_password_hash
from ...core.password_utils import get_password_hash # 從 password_utils.py 匯入 get_password_hash
from ...core.config import settings
from ...core.logging_utils import log_event
from ...models.log_models import LogLevel


router = APIRouter()

@router.post("/token", response_model=Token, summary="使用者登入並獲取 JWT Token")
async def login_for_access_token(
    request: Request, # 用於日誌記錄
    db: AsyncIOMotorDatabase = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends() # FastAPI 提供的標準表單
):
    """
    使用使用者名稱和密碼進行身份驗證，成功則返回 Access Token。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    log_details = {"username": form_data.username}
    await log_event(db, LogLevel.DEBUG, f"使用者嘗試登入: {form_data.username}", "auth_api", request_id=request_id_for_log, details=log_details)

    user = await crud_users.get_user_by_username(db, username=form_data.username)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        await log_event(db, LogLevel.WARNING, f"使用者登入失敗: {form_data.username} - 無效的憑證", "auth_api", request_id=request_id_for_log, details=log_details)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不正確的使用者名稱或密碼",
            headers={"WWW-Authenticate": "Bearer"}, # 標準的未授權回應頭
        )
    
    if not user.is_active:
        await log_event(db, LogLevel.WARNING, f"使用者登入失敗: {form_data.username} - 帳戶未啟用", "auth_api", request_id=request_id_for_log, details=log_details)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="帳戶未啟用"
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
        # 如果需要在 token 中包含 user.id，可以在 create_access_token 的 subject 中傳遞一個 dict
        # subject={"username": user.username, "user_id": str(user.id)}
        # 然後在 TokenData 和解碼邏輯中相應處理
    )
    
    await log_event(db, LogLevel.INFO, f"使用者成功登入: {user.username}", "auth_api", user_id=str(user.id), request_id=request_id_for_log)
    return Token(access_token=access_token, token_type="bearer")

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED, summary="註冊新使用者")
async def register_new_user(
    request: Request,
    user_in: UserCreate, 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    創建一個新使用者帳戶。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    log_details = {"username": user_in.username, "email": user_in.email}
    await log_event(db, LogLevel.DEBUG, f"嘗試註冊新使用者: {user_in.username}", "auth_api", request_id=request_id_for_log, details=log_details)

    existing_user_by_name = await crud_users.get_user_by_username(db, username=user_in.username)
    if existing_user_by_name:
        await log_event(db, LogLevel.WARNING, f"使用者註冊失敗: 使用者名稱 {user_in.username} 已存在", "auth_api", request_id=request_id_for_log, details=log_details)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="使用者名稱已被使用",
        )
    
    if user_in.email: # 只有在提供了 email 時才檢查
        existing_user_by_email = await crud_users.get_user_by_email(db, email=user_in.email)
        if existing_user_by_email:
            await log_event(db, LogLevel.WARNING, f"使用者註冊失敗: 電子郵件 {user_in.email} 已存在", "auth_api", request_id=request_id_for_log, details=log_details)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="電子郵件已被使用",
            )

    created_user = await crud_users.create_user(db=db, user_in=user_in)
    # create_user 返回的是 UserInDB，包含 hashed_password
    # 我們需要返回 User 模型 (不含 hashed_password)
    
    await log_event(db, LogLevel.INFO, f"新使用者成功註冊: {created_user.username}", "auth_api", user_id=str(created_user.id), request_id=request_id_for_log)
    return User(**created_user.model_dump(exclude={"hashed_password"}))


@router.get("/users/me", response_model=User, summary="獲取當前登入使用者的資訊")
async def read_users_me(
    current_user: UserInDB = Depends(get_current_active_user) # 改為 UserInDB
):
    """
    獲取當前已驗證使用者的詳細資訊。
    """
    # request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    # await log_event(db, LogLevel.DEBUG, f"使用者 {current_user.username} 獲取自身資訊", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)
    
    return User(**current_user.model_dump(exclude={"hashed_password"}))

@router.put("/users/me", response_model=User, summary="更新當前登入使用者的個人資料")
async def update_current_user_profile(
    request: Request,
    user_update_in: UserUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    更新當前已驗證使用者的個人資料 (例如 email, full_name)。
    不允許透過此端點更新密碼或使用者名稱。
    不允許用戶自行將 is_active 設為 False，但如果管理員將其設為 False，用戶也無法透過此修改。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    log_details = user_update_in.model_dump(exclude_unset=True)
    await log_event(db, LogLevel.DEBUG, f"使用者 {current_user.username} 嘗試更新個人資料", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log, details=log_details)

    # 如果用戶嘗試更新 is_active 狀態為 False，則阻止
    if user_update_in.is_active is False:
        await log_event(db, LogLevel.WARNING, f"使用者 {current_user.username} 嘗試將 is_active 設為 False，操作被拒絕", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不允許自行停用帳戶。"
        )

    updated_user = await crud_users.update_user(
        db=db, user_id=current_user.id, user_in=user_update_in
    )

    if updated_user is None:
        # CRUD 層的 email 衝突檢查返回 None
        await log_event(db, LogLevel.ERROR, f"使用者 {current_user.username} 更新個人資料失敗 (可能由於 Email 衝突)", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log, details=log_details)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無法更新使用者資料，可能是電子郵件已被使用。"
        )
    
    await log_event(db, LogLevel.INFO, f"使用者 {current_user.username} 成功更新個人資料", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log, details=updated_user.model_dump(exclude={"hashed_password"}))
    return User(**updated_user.model_dump(exclude={"hashed_password"}))

@router.put("/users/me/password", response_model=MessageResponse, status_code=status.HTTP_200_OK, summary="更新當前登入使用者的密碼")
async def update_current_user_password(
    request: Request,
    password_update_in: PasswordUpdateIn,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    更新當前已驗證使用者的密碼。
    需要提供目前密碼和新密碼。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(db, LogLevel.DEBUG, f"使用者 {current_user.username} 嘗試更新密碼", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)

    if not verify_password(password_update_in.current_password, current_user.hashed_password):
        await log_event(db, LogLevel.WARNING, f"使用者 {current_user.username} 更新密碼失敗: 目前密碼不正確", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="目前密碼不正確。"
        )
    
    if password_update_in.current_password == password_update_in.new_password:
        await log_event(db, LogLevel.INFO, f"使用者 {current_user.username} 嘗試將密碼更新為與目前密碼相同的值，操作跳過但仍視為成功更新", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)
        # 即使密碼相同，也返回成功訊息，因為操作意圖是"更新"，且未出錯
        return MessageResponse(message="密碼未變更，但請求已處理。")

    password_updated = await crud_users.update_password(
        db=db, user_id=current_user.id, new_password=password_update_in.new_password
    )

    if not password_updated:
        await log_event(db, LogLevel.ERROR, f"使用者 {current_user.username} 更新密碼時發生未知錯誤 (CRUD 操作未成功)", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新密碼時發生錯誤，請稍後再試。"
        )
    
    await log_event(db, LogLevel.INFO, f"使用者 {current_user.username} 成功更新密碼", "auth_api", user_id=str(current_user.id), request_id=request_id_for_log)
    return MessageResponse(message="密碼已成功更新")

@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT, summary="刪除當前登入使用者的帳戶")
async def delete_current_user_account(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    永久刪除當前已驗證使用者的帳戶。
    這是一個無法復原的操作。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    user_id_to_delete = current_user.id
    username_to_delete = current_user.username
    
    await log_event(db, LogLevel.WARNING, f"使用者 {username_to_delete} (ID: {user_id_to_delete}) 嘗試刪除自己的帳戶", "auth_api", user_id=str(user_id_to_delete), request_id=request_id_for_log)

    # 實際刪除操作
    deleted_successfully = await crud_users.delete_user(db=db, user_id=user_id_to_delete)

    if not deleted_successfully:
        # 這種情況理論上不應該發生，除非用戶在驗證後立即被其他人刪除，或數據庫錯誤
        await log_event(db, LogLevel.ERROR, f"使用者 {username_to_delete} (ID: {user_id_to_delete}) 刪除帳戶失敗 (CRUD 操作未成功)", "auth_api", user_id=str(user_id_to_delete), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="刪除帳戶時發生錯誤，請稍後再試。"
        )
    
    # 考慮：刪除用戶後，可能需要使其所有 JWT 失效（如果系統實現了 token 黑名單機制）
    # 考慮：刪除用戶相關的數據，例如 ConnectedDevice 記錄等（如果業務邏輯需要）

    await log_event(db, LogLevel.INFO, f"使用者 {username_to_delete} (ID: {user_id_to_delete}) 已成功刪除其帳戶", "auth_api", user_id=str(user_id_to_delete), request_id=request_id_for_log)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# 後續可以添加 /users/me 端點來獲取當前用戶信息，以及註冊端點
# @router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
# async def register_new_user(...):
#    ... 