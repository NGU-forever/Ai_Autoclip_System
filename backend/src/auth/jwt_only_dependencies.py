"""
Uploader 独立服务用：仅校验 JWT，不查库。
停用用户后已签发 token 在过期前仍可能通过校验（与常见无状态 JWT 行为一致）。
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from src.auth.jwt_decode import decode_access_token
from src.exceptions import UnauthorizedException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException()
    except JWTError:
        raise UnauthorizedException()
    return {"id": user_id}
