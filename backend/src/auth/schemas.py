from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from src.users.schemas import UserResponse

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    model_config = ConfigDict(extra="forbid")

class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse
    model_config = ConfigDict(extra="forbid")
