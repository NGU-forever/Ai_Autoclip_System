from src.auth.schemas import LoginRequest, TokenResponse
from src.exceptions import UnauthorizedException
from src.auth.utils import create_access_token

class AuthService:
    def __init__(self):
        pass

    async def login(self, request: LoginRequest) -> TokenResponse:
        # 简化登录：统一硬编码账号为 admin，密码 123456
        if request.email == "admin" and request.password == "123456":
            access_token = create_access_token(data={"sub": "admin", "role": "admin"})
            return TokenResponse(
                access_token=access_token,
                user={"id": "admin", "email": "admin", "role": "admin", "status": "active"}
            )
        raise UnauthorizedException("Incorrect email or password")
