from app.db.mongodb_utils import get_db
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm # 用於接收 username 和 password
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import timedelta
from pydantic import BaseModel
import json
import base64

from ...models.token_models import Token # Token 回應模型
from ...models.user_models import User, UserCreate, UserInDB, UserUpdate, PasswordUpdateIn # <--- 確保 UserUpdate 已導入
from ...models.response_models import MessageResponse # <--- 導入 MessageResponse
from ...crud.crud_users import crud_users # User CRUD 操作
from ...core.security import verify_password, create_access_token, get_current_active_user # 移除 get_password_hash
from ...core.password_utils import get_password_hash # 從 password_utils.py 匯入 get_password_hash
from ...core.config import settings
from ...core.logging_utils import log_event
from ...models.log_models import LogLevel
from ...core.logging_decorators import log_api_operation


# Google OAuth 請求模型
class GoogleLoginRequest(BaseModel):
    google_token: str


router = APIRouter()

@router.post("/token", response_model=Token, summary="使用者登入並獲取 JWT Token")
@log_api_operation(operation_name="用戶登錄", log_success=True)
async def login_for_access_token(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    使用使用者名稱和密碼進行身份驗證，成功則返回 Access Token。
    """
    user = await crud_users.get_user_by_username(db, username=form_data.username)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        # 保留安全審計日誌
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="User login failed: Invalid credentials.",
            source="api.auth.login",
            details={"username": form_data.username}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        # 保留安全審計日誌
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="User login failed: User inactive.",
            source="api.auth.login",
            details={"username": form_data.username, "user_id": str(user.id)}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Account is inactive."
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token, token_type="bearer")

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED, summary="註冊新使用者")
@log_api_operation(operation_name="用戶註冊", log_success=True)
async def register_new_user(
    request: Request,
    user_in: UserCreate, 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    創建一個新使用者帳戶。
    """
    existing_user_by_name = await crud_users.get_user_by_username(db, username=user_in.username)
    if existing_user_by_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken.",
        )
    
    if user_in.email:
        existing_user_by_email = await crud_users.get_user_by_email(db, email=user_in.email)
        if existing_user_by_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered.",
            )

    created_user = await crud_users.create_user(db=db, user_in=user_in)
    return User(**created_user.model_dump(exclude={"hashed_password"}))

@router.get("/users/me", response_model=User, summary="獲取當前登入使用者的資訊")
@log_api_operation(operation_name="獲取用戶信息", log_success=True, success_level=LogLevel.DEBUG)
async def read_users_me(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取當前已驗證使用者的詳細資訊。
    """
    return User(**current_user.model_dump(exclude={"hashed_password"}))

@router.put("/users/me", response_model=User, summary="更新當前登入使用者的個人資料")
@log_api_operation(operation_name="更新用戶資料", log_success=True)
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
    if user_update_in.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Self-deactivation of account is not allowed."
        )

    if user_update_in.email is not None and user_update_in.email != current_user.email:
        existing_user_by_email = await crud_users.get_user_by_email(db, email=user_update_in.email)
        if existing_user_by_email and existing_user_by_email.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use."
            )

    updated_user = await crud_users.update_user(
        db=db, user_id=current_user.id, user_in=user_update_in
    )

    if updated_user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating user profile."
        )
    
    return User(**updated_user.model_dump(exclude={"hashed_password"}))

@router.put("/users/me/password", response_model=MessageResponse, status_code=status.HTTP_200_OK, summary="更新當前登入使用者的密碼")
@log_api_operation(operation_name="更新密碼", log_success=True)
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
    if not verify_password(password_update_in.current_password, current_user.hashed_password):
        # 保留安全審計日誌
        await log_event(db, LogLevel.WARNING, f"User {current_user.username} password update failed: Current password incorrect", source="api.auth.update_password", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password incorrect."
        )
    
    if password_update_in.current_password == password_update_in.new_password:
        return MessageResponse(message="Password unchanged, request processed.")

    password_updated = await crud_users.update_password(
        db=db, user_id=current_user.id, new_password=password_update_in.new_password
    )

    if not password_updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating password. Please try again later."
        )
    
    return MessageResponse(message="Password updated successfully.")

@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT, summary="刪除當前登入使用者的帳戶")
@log_api_operation(operation_name="刪除用戶帳戶", log_success=True)
async def delete_current_user_account(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    永久刪除當前已驗證使用者的帳戶。
    這是一個無法復原的操作。
    """
    # 保留重要的安全審計日誌
    await log_event(db, LogLevel.WARNING, f"User {current_user.username} (ID: {current_user.id}) attempting to delete their own account", source="api.auth.delete_account", user_id=str(current_user.id))

    deleted_successfully = await crud_users.delete_user(db=db, user_id=current_user.id)

    if not deleted_successfully:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the account. Please try again later."
        )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/google-login", response_model=Token, summary="使用 Google OAuth Token 登入")
async def google_login(
    request: Request,
    google_login_req: GoogleLoginRequest,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    使用 Google OAuth ID Token 進行身份驗證，成功則返回 Access Token。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        # 解碼 Google ID Token (不驗證簽名，因為客戶端已驗證)
        # Google ID Token 由三部分組成，以 '.' 分隔
        token_parts = google_login_req.google_token.split('.')
        if len(token_parts) != 3:
            raise ValueError("Invalid token format")
        
        # 解碼 payload (第二部分)
        payload = token_parts[1]
        # 添加必要的 padding
        padding = 4 - (len(payload) % 4)
        if padding != 4:
            payload += '=' * padding
        
        decoded_payload = json.loads(base64.urlsafe_b64decode(payload))
        google_email = decoded_payload.get('email')
        google_name = decoded_payload.get('name', '')
        
        if not google_email:
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="Google login failed: No email in token",
                source="api.auth.google_login",
                request_id=request_id_for_log
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google token: missing email"
            )
        
        # 檢查用戶是否存在
        user = await crud_users.get_user_by_email(db, email=google_email)
        
        if not user:
            # 創建新用戶
            # 生成一個用戶名 (使用 email 的本地部分)
            username = google_email.split('@')[0]
            
            # 確保用戶名唯一
            counter = 1
            original_username = username
            while await crud_users.get_user_by_username(db, username=username):
                username = f"{original_username}{counter}"
                counter += 1
            
            # 創建臨時密碼（Google OAuth 用戶不會使用它）
            temp_password = "google_oauth_user_" + google_email.replace('@', '_').replace('.', '_')
            
            user_create = UserCreate(
                username=username,
                email=google_email,
                full_name=google_name or username,
                password=temp_password
            )
            
            try:
                user = await crud_users.create_user(db=db, user_in=user_create)
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"New user created via Google OAuth: {user.username}",
                    source="api.auth.google_login",
                    user_id=str(user.id),
                    request_id=request_id_for_log,
                    details={"email": google_email, "username": user.username}
                )
            except Exception as e:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"Failed to create user from Google OAuth: {str(e)}",
                    source="api.auth.google_login",
                    request_id=request_id_for_log,
                    details={"email": google_email}
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user account"
                )
        else:
            # 檢查用戶是否活躍
            if not user.is_active:
                await log_event(
                    db=db,
                    level=LogLevel.WARNING,
                    message="Google login failed: User account is inactive",
                    source="api.auth.google_login",
                    user_id=str(user.id),
                    request_id=request_id_for_log
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Account is inactive"
                )
        
        # 生成 Access Token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=str(user.id), expires_delta=access_token_expires
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="User login successful via Google OAuth",
            source="api.auth.google_login",
            user_id=str(user.id),
            request_id=request_id_for_log,
            details={"email": google_email, "username": user.username}
        )
        
        return Token(access_token=access_token, token_type="bearer")
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Google login error: {str(e)}",
            source="api.auth.google_login",
            request_id=request_id_for_log
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during Google login"
        )

# 後續可以添加 /users/me 端點來獲取當前用戶信息，以及註冊端點
# @router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
# async def register_new_user(...):
#    ... 