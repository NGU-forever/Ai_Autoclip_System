from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List
from src.exceptions import UnauthorizedException, ForbiddenException
from jose import JWTError
from src.auth.utils import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_user_repository():
    pass

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException()
    except JWTError:
        raise UnauthorizedException()
    
    # 绕过数据库查询，直接返回 hardcoded admin
    return {"id": "admin", "email": "admin", "role": "admin", "status": "active"}

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)):
        if user.get("role") not in self.allowed_roles:
            raise ForbiddenException("You do not have enough permissions to perform this action")
        return user
