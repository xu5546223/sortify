from passlib.context import CryptContext

# Passlib context for password hashing
# 使用 bcrypt 作為主要的哈希算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證明文密碼與哈希後的密碼是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """對明文密碼進行哈希處理"""
    return pwd_context.hash(password) 