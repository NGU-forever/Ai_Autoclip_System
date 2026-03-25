from fastapi import APIRouter, Depends
from src.auth.schemas import LoginRequest, TokenResponse
from src.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, service: AuthService = Depends()):
    return await service.login(request)
