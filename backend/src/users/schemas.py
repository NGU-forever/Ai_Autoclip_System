from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

UserRole = Literal["admin", "user", "viewer"]
UserStatus = Literal["active", "disabled"]


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: UserRole = "user"
    status: UserStatus = "active"
    avatar: Optional[str] = Field(default=None, max_length=500)


class UserCreate(UserBase):
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    model_config = ConfigDict(extra="forbid")


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    avatar: Optional[str] = Field(default=None, max_length=500)
    model_config = ConfigDict(extra="forbid")


class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int
