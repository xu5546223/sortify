from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: str | None = None # 將 username 改為 user_id，因為 subject 將存儲 user_id
    # 如果您打算在 token 中加入其他 scope 或 id，可以在這裡添加
    # user_id: UUID | None = None 