from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from src.exceptions import UnauthorizedException, ForbiddenException
from jose import JWTError
from src.auth.utils import decode_access_token
from src.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

def get_user_repository():
    pass


# 开发模式 mock 用户
DEV_MOCK_USER = {"id": "admin", "email": "admin@example.com", "role": "admin", "status": "active"}


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)):
    # DEV_MODE: 登录已移除 - 直接返回 mock 用户
    return DEV_MOCK_USER

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)):
        if user.get("role") not in self.allowed_roles:
            raise ForbiddenException("You do not have enough permissions to perform this action")
        return user
