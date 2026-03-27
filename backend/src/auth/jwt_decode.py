"""JWT decode only (no passlib); for uploader standalone service."""

from typing import Any

from jose import jwt

from src.config import settings


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
