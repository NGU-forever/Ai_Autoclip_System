from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from typing import List
from src.auth.utils import decode_access_token
from src.users.models import UserRepository
from src.exceptions import UnauthorizedException, ForbiddenException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_user_repository():
    return UserRepository()

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    user_repo: UserRepository = Depends(get_user_repository)
):
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException()
    except JWTError:
        raise UnauthorizedException()
    
    user = await run_in_threadpool(user_repo.get_user_by_id, user_id)
    if user is None:
        raise UnauthorizedException()
    if user.get("status") != "active":
        raise ForbiddenException("User account is disabled")
    return user

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)):
        if user.get("role") not in self.allowed_roles:
            raise ForbiddenException("You do not have enough permissions to perform this action")
        return user
