from pydantic import BaseModel
from typing import Any

class MessageResponse(BaseModel):
    message: str

class BasicResponse(BaseModel):
    success: bool
    message: str
    data: Any = None 