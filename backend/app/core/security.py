from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError

from .config import settings
from ..dependencies import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..crud.crud_users import crud_users
from ..models.user_models import UserInDB
from ..models.token_models import TokenData
from .password_utils import verify_password
from ..core.logging_utils import log_event
from ..models.log_models import LogLevel

# Passlib context for password hashing
# 使用 bcrypt 作為主要的哈希算法
# pwd_context, verify_password, get_password_hash 已被移至 password_utils.py

ALGORITHM = settings.ALGORITHM
SECRET_KEY = settings.SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# OAuth2PasswordBearer 實例，tokenUrl 指向獲取 token 的端點路徑
# 重要：tokenUrl 應該是相對於應用根路徑的完整路徑
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")

def create_access_token(
    subject: str | Any, expires_delta: Optional[timedelta] = None
) -> str:
    """
    創建一個新的 Access Token。
    :param subject: Token 的主題 (通常是 user_id 或 username)
    :param expires_delta: Token 的有效期 (timedelta 對象)
    :return: JWT 字串
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode: Dict[str, Any] = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- 依賴注入函數 ---
async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> str | None:
    """
    解碼 JWT token 並返回 user_id。
    如果 token 無效或解碼失敗，則記錄錯誤並引發 HTTPException。
    """
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else "N/A"
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id_from_token: str | None = None
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM]
        )
        user_id_from_token = payload.get("sub")
        if user_id_from_token is None:
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message="Token validation failed: 'sub' claim missing.",
                source="get_current_user",
                request_id=request_id_for_log,
                details={"token_payload": payload}
            )
            raise credentials_exception
        
        token_data = TokenData(user_id=user_id_from_token)

    except JWTError as e:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="Token validation failed due to JWTError.", # Generic message
            source="get_current_user",
            request_id=request_id_for_log,
            details={
                "error_type": type(e).__name__,
                "error_message": "JWT processing error", # More generic message in details
                "guidance": "Verify token structure, signature, and claims. The token may be malformed, expired, or have an invalid signature."
            }
        )
        raise credentials_exception
    except ValidationError as e:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="Token validation failed due to ValidationError (TokenData structure).",
            source="get_current_user",
            request_id=request_id_for_log,
            details={"validation_errors": e.errors()}
        )
        raise credentials_exception
    
    return token_data.user_id

async def get_current_active_user(
    current_user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db) 
) -> UserInDB: 
    try:
        user_uuid = UUID(current_user_id)
    except ValueError:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message="Invalid user_id format in token after primary validation.",
            source="get_current_active_user",
            details={"user_id_from_token": current_user_id}
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="無效的 token (user_id 格式錯誤)")

    user = await crud_users.get_user_by_id(db, user_id=user_uuid)
    if not user:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message=f"Authenticated user ID not found in DB: {user_uuid}",
            source="get_current_active_user",
            details={"user_id": str(user_uuid)}
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用戶不存在")
    if not user.is_active:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message=f"User account is inactive: {user.username}",
            source="get_current_active_user",
            details={"user_id": str(user_uuid), "username": user.username}
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非活動使用者")
    return user

async def get_current_admin_user(
    current_user: UserInDB = Depends(get_current_active_user)
) -> UserInDB:
    """
    獲取當前活躍用戶，並驗證其是否為管理員。
    如果用戶不是管理員，則引發 HTTPException 403 Forbidden。
    """
    if not current_user.is_admin:
        # 注意：這裡我們不應該記錄過於詳細的用戶非管理員嘗試信息，
        # 除非有特定的審計需求。基本的拒絕已經由HTTP狀態碼處理。
        # 如果需要記錄，可以添加一個簡短的日誌條目。
        # await log_event(
        #     db=..., # 需要傳遞 db 實例或使其可用
        #     level=LogLevel.WARNING,
        #     message=f"Non-admin user {current_user.username} attempted admin-only action.",
        #     source="get_current_admin_user",
        #     details={"user_id": str(current_user.id), "username": current_user.username}
        # )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="操作未授權：需要管理員權限"
        )
    return current_user

# 後續我們會在這裡添加一個依賴項，用於解碼和驗證 token，
# 例如 get_current_user
# async def get_current_user(token: str = Depends(oauth2_scheme)):\
#     ... 