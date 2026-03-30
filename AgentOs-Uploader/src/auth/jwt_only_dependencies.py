"""
Uploader 独立服务用：仅校验 JWT，不查库。
停用用户后已签发 token 在过期前仍可能通过校验（与常见无状态 JWT 行为一致）。
"""

from typing import Optional

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from src.auth.jwt_decode import decode_access_token
from src.exceptions import UnauthorizedException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException()
    except JWTError:
        raise UnauthorizedException()
    return {"id": user_id}


async def get_current_user_from_header_or_query(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    access_token: Optional[str] = Query(None, description="JWT token for video streaming (query param fallback)"),
):
    """Support token from Authorization header OR access_token query param (for video streaming).
    
    HTML5 video element cannot send custom headers, so we support token via query parameter.
    """
    actual_token = token
    if actual_token is None and access_token:
        actual_token = access_token
    
    if not actual_token:
        raise UnauthorizedException()
    
    try:
        payload = decode_access_token(actual_token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise UnauthorizedException()
    except JWTError:
        raise UnauthorizedException()
    return {"id": user_id}
