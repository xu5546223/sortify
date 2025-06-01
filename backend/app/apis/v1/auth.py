from app.db.mongodb_utils import get_db
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm # 用於接收 username 和 password
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import timedelta


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
    username_for_log = form_data.username # Store for consistent use in logs

    # Log login attempt (already DEBUG, can keep or change if needed)
    await log_event(
        db=db,
        level=LogLevel.DEBUG,
        message=f"Login attempt for user: {username_for_log}",
        source="api.auth.login", # Standardized source
        request_id=request_id_for_log,
        details={"username": username_for_log}
    )

    user = await crud_users.get_user_by_username(db, username=username_for_log)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="User login failed: Invalid credentials.", # Standardized message
            source="api.auth.login",
            request_id=request_id_for_log,
            details={"username": username_for_log}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.", # User-friendly, avoids "invalid credentials"
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="User login failed: User inactive or not found.", # Standardized message (covers not found implicitly by previous check)
            source="api.auth.login",
            request_id=request_id_for_log,
            details={"username": username_for_log, "user_id_if_found": str(user.id) if user else None}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Account is inactive." # User-friendly
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )
    
    await log_event(
        db=db,
        level=LogLevel.INFO,
        message="User login successful.", # Standardized message
        source="api.auth.login",
        user_id=str(user.id),
        request_id=request_id_for_log,
        details={"username": username_for_log, "user_id": str(user.id)} # Added user_id to details
    )
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
    log_details = {"username": user_in.username, "email": user_in.email} # Email is logged here, masker should handle if sensitive
    await log_event(db, LogLevel.DEBUG, f"Attempting to register new user: {user_in.username}", source="api.auth.register", request_id=request_id_for_log, details=log_details)

    existing_user_by_name = await crud_users.get_user_by_username(db, username=user_in.username)
    if existing_user_by_name:
        await log_event(db, LogLevel.WARNING, f"User registration failed: Username {user_in.username} already exists", source="api.auth.register", request_id=request_id_for_log, details=log_details)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken.",
        )
    
    if user_in.email: # 只有在提供了 email 時才檢查
        existing_user_by_email = await crud_users.get_user_by_email(db, email=user_in.email)
        if existing_user_by_email:
            await log_event(db, LogLevel.WARNING, f"User registration failed: Email {user_in.email} already exists", source="api.auth.register", request_id=request_id_for_log, details=log_details)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered.",
            )

    created_user = await crud_users.create_user(db=db, user_in=user_in)
    # create_user 返回的是 UserInDB，包含 hashed_password
    # 我們需要返回 User 模型 (不含 hashed_password)
    
    await log_event(db, LogLevel.INFO, f"New user registered successfully: {created_user.username}", source="api.auth.register", user_id=str(created_user.id), request_id=request_id_for_log, details={"user_id": str(created_user.id), "username": created_user.username})
    return User(**created_user.model_dump(exclude={"hashed_password"}))


@router.get("/users/me", response_model=User, summary="獲取當前登入使用者的資訊")
async def read_users_me(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user), # 改為 UserInDB
    db:AsyncIOMotorDatabase = Depends(get_db)
    
):
    """
    獲取當前已驗證使用者的詳細資訊。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    user_response = User(**current_user.model_dump(exclude={"hashed_password"}))
    await log_event(
        db=db,
        level=LogLevel.INFO,
        message="User profile accessed.",
        source="api.auth.read_users_me",
        module_name="app.apis.v1.auth",
        func_name="read_users_me",
        user_id=str(current_user.id),
        request_id=request_id_for_log,
        details={"user_id": str(current_user.id), "username": current_user.username}
    )
    return user_response

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
    # Log the attempt with only field names that are being updated, not their values directly from user_update_in
    update_attempt_details = {"attempted_update_fields": list(user_update_in.model_dump(exclude_unset=True).keys())}
    await log_event(db, LogLevel.DEBUG, f"User {current_user.username} attempting to update profile", source="api.auth.update_profile", user_id=str(current_user.id), request_id=request_id_for_log, details=update_attempt_details)

    # 如果用戶嘗試更新 is_active 狀態為 False，則阻止
    if user_update_in.is_active is False:
        await log_event(db, LogLevel.WARNING, f"User {current_user.username} attempt to set is_active to False was rejected", source="api.auth.update_profile", user_id=str(current_user.id), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Self-deactivation of account is not allowed."
        )

    # 檢查 Email 衝突 (如果提供了 email)
    if user_update_in.email is not None and user_update_in.email != current_user.email:
        existing_user_by_email = await crud_users.get_user_by_email(db, email=user_update_in.email)
        if existing_user_by_email and existing_user_by_email.id != current_user.id:
            await log_event(db, LogLevel.WARNING, f"User {current_user.username} profile update failed: Email {user_update_in.email} already in use by another user", source="api.auth.update_profile", user_id=str(current_user.id), request_id=request_id_for_log, details={"conflicting_email": user_update_in.email})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use."
            )

    updated_user = await crud_users.update_user(
        db=db, user_id=current_user.id, user_in=user_update_in
    )

    if updated_user is None:
        # 這種情況現在理論上不應發生，因為主要的業務邏輯檢查 (如 email 衝突) 已在此處處理
        # 但保留以防 CRUD 層因其他原因 (例如資料庫內部錯誤，儘管可能性低) 返回 None
        await log_event(db, LogLevel.ERROR, f"User {current_user.username} profile update failed unexpectedly (CRUD layer returned None)", source="api.auth.update_profile", user_id=str(current_user.id), request_id=request_id_for_log, details=update_attempt_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating user profile."
        )
    
    # Log successful update with the actual fields that were updated from CRUD operation (if available) or from input.
    # crud_users.update_user logs the fields list from input, which is good.
    await log_event(db, LogLevel.INFO, f"User {current_user.username} successfully updated profile", source="api.auth.update_profile", user_id=str(current_user.id), request_id=request_id_for_log, details={"user_id": str(current_user.id), "updated_username": updated_user.username}) # Details can be simple or include changed fields if necessary and safe
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
    await log_event(db, LogLevel.DEBUG, f"User {current_user.username} attempting to update password", source="api.auth.update_password", user_id=str(current_user.id), request_id=request_id_for_log)

    if not verify_password(password_update_in.current_password, current_user.hashed_password):
        await log_event(db, LogLevel.WARNING, f"User {current_user.username} password update failed: Current password incorrect", source="api.auth.update_password", user_id=str(current_user.id), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password incorrect."
        )
    
    if password_update_in.current_password == password_update_in.new_password:
        await log_event(db, LogLevel.INFO, f"User {current_user.username} attempted to update password to the same value. Operation skipped, considered successful.", source="api.auth.update_password", user_id=str(current_user.id), request_id=request_id_for_log)
        return MessageResponse(message="Password unchanged, request processed.")

    password_updated = await crud_users.update_password(
        db=db, user_id=current_user.id, new_password=password_update_in.new_password
    )

    if not password_updated:
        await log_event(db, LogLevel.ERROR, f"User {current_user.username} password update failed unexpectedly (CRUD operation unsuccessful)", source="api.auth.update_password", user_id=str(current_user.id), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating password. Please try again later."
        )
    
    await log_event(db, LogLevel.INFO, f"User {current_user.username} successfully updated password", source="api.auth.update_password", user_id=str(current_user.id), request_id=request_id_for_log)
    return MessageResponse(message="Password updated successfully.")

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
    
    await log_event(db, LogLevel.WARNING, f"User {username_to_delete} (ID: {user_id_to_delete}) attempting to delete their own account", source="api.auth.delete_account", user_id=str(user_id_to_delete), request_id=request_id_for_log)

    # 實際刪除操作
    deleted_successfully = await crud_users.delete_user(db=db, user_id=user_id_to_delete)

    if not deleted_successfully:
        # 這種情況理論上不應該發生，除非用戶在驗證後立即被其他人刪除，或數據庫錯誤
        await log_event(db, LogLevel.ERROR, f"User {username_to_delete} (ID: {user_id_to_delete}) account deletion failed (CRUD operation unsuccessful)", source="api.auth.delete_account", user_id=str(user_id_to_delete), request_id=request_id_for_log)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the account. Please try again later."
        )
    
    # 考慮：刪除用戶後，可能需要使其所有 JWT 失效（如果系統實現了 token 黑名單機制）
    # 考慮：刪除用戶相關的數據，例如 ConnectedDevice 記錄等（如果業務邏輯需要）

    await log_event(db, LogLevel.INFO, f"User {username_to_delete} (ID: {user_id_to_delete}) successfully deleted their account", source="api.auth.delete_account", user_id=str(user_id_to_delete), request_id=request_id_for_log)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# 後續可以添加 /users/me 端點來獲取當前用戶信息，以及註冊端點
# @router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
# async def register_new_user(...):
#    ... 