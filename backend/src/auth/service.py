from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from src.users.models import UserRepository
from src.auth.utils import verify_password, create_access_token
from src.auth.schemas import LoginRequest, TokenResponse
from src.exceptions import UnauthorizedException, ForbiddenException
import hashlib
from passlib.exc import UnknownHashError


class AuthService:
    def __init__(self, user_repo: UserRepository = Depends(UserRepository)):
        self.user_repo = user_repo

    async def login(self, request: LoginRequest) -> TokenResponse:
        user_internal = await run_in_threadpool(self.user_repo.get_user_by_email_internal, request.email)
        if not user_internal:
            raise UnauthorizedException("Incorrect email or password")

        password_hash = user_internal.get("password_hash")

        is_valid = False
        try:
            is_valid = verify_password(request.password, password_hash)
        except (ValueError, TypeError, UnknownHashError):
            sha256_hash = hashlib.sha256(request.password.encode()).hexdigest()
            if sha256_hash == password_hash:
                is_valid = True

        if not is_valid:
            raise UnauthorizedException("Incorrect email or password")

        if user_internal.get("status") != "active":
            raise ForbiddenException("User account is disabled")

        await run_in_threadpool(self.user_repo.update_last_login, str(user_internal["id"]))

        access_token = create_access_token(data={"sub": str(user_internal["id"]), "role": user_internal["role"]})

        user_public = user_internal.copy()
        user_public.pop("password_hash", None)

        return TokenResponse(
            access_token=access_token,
            user=user_public
        )
