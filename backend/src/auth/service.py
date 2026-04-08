from src.auth.schemas import LoginRequest, TokenResponse
from src.exceptions import UnauthorizedException
from src.auth.utils import create_access_token

class AuthService:
    def __init__(self):
        pass

    async def login(self, request: LoginRequest) -> TokenResponse:
        # DEV_MODE: 登录已移除 - 直接返回 mock token
        access_token = create_access_token(data={"sub": "admin", "role": "admin"})
        return TokenResponse(
            access_token=access_token,
            user={"id": "admin", "email": "admin", "role": "admin", "status": "active"}
        )
