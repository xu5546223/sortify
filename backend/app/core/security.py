from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError

from .config import settings
from ..dependencies import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..crud.crud_users import crud_users
from ..models.user_models import UserInDB
from ..models.token_models import TokenData
from .password_utils import verify_password

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
    token: str = Depends(oauth2_scheme)
) -> str | None:
    """
    解碼 JWT token 並返回 payload。實際的用戶對象查找應在調用此依賴的端點中進行，
    以允許更靈活的資料庫訪問和錯誤處理。
    或者，如果 db 依賴可以解決，則直接返回 UserInDB。
    為了避免 security.py 依賴 db.py，然後 db.py 可能又依賴其他東西，
    這裡先返回 token_data (payload中的用戶標識)，讓端點自己去查 user。
    更新：FastAPI 建議依賴項可以互相依賴，所以 get_db 是可以的。
    """
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
            # log an event here
            raise credentials_exception
        # 使用 TokenData 驗證 payload 的結構 (如果 sub 存在)
        token_data = TokenData(user_id=user_id_from_token)
    except JWTError: # Catches ExpiredSignatureError, JWTClaimsError, etc.
        # log an event here
        raise credentials_exception
    except ValidationError: # Pydantic validation error for TokenData
        # log an event here
        raise credentials_exception
    
    return user_id_from_token # 返回 user_id

async def get_current_active_user(
    current_user_id: str | None = Depends(get_current_user), # 依賴於 get_current_user 返回的 user_id
    db: AsyncIOMotorDatabase = Depends(get_db) 
) -> UserInDB: 
    if current_user_id is None:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="無效的 token (無法獲取 user_id)")

    try:
        user_uuid = UUID(current_user_id) # 將 str 轉換為 UUID
    except ValueError:
        # 如果 current_user_id 不是有效的 UUID 格式
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="無效的 token (user_id 格式錯誤)")

    user = await crud_users.get_user_by_id(db, user_id=user_uuid) # 使用 get_user_by_id
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用戶不存在")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非活動使用者")
    return user

# 後續我們會在這裡添加一個依賴項，用於解碼和驗證 token，
# 例如 get_current_user
# async def get_current_user(token: str = Depends(oauth2_scheme)):\
#     ... 