import os
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://tester:tester@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# 顶层目录名为 AgentOs-Uploader，但 Python 包名仍为 uploader（与容器内 /app/uploader 一致）
_repo_root = Path(__file__).resolve().parents[2]
_agent_uploader = _repo_root / "AgentOs-Uploader"
_backend_src = _repo_root / "backend" / "src"
_uploader_src = _agent_uploader / "src"
_uploader_link = _repo_root / "uploader"
if _agent_uploader.is_dir() and not _uploader_link.exists():
    _pkg = types.ModuleType("uploader")
    _pkg.__path__ = [str(_agent_uploader)]
    sys.modules["uploader"] = _pkg

# 合并 backend/src 与 AgentOs-Uploader/src：测试里 src.auth/config 走主站，src.upload 走分发服务（与 storyline 分包方式一致）
if _backend_src.is_dir() and _uploader_src.is_dir():
    _src_ns = types.ModuleType("src")
    _src_ns.__path__ = [str(_backend_src), str(_uploader_src)]
    sys.modules["src"] = _src_ns

from src.auth.dependencies import get_current_user
from src.auth.jwt_only_dependencies import get_current_user as uploader_get_current_user
from src.auth.router import router as auth_router
from src.auth.schemas import LoginRequest, TokenResponse
from src.auth.service import AuthService
from src.config import settings
from src.exceptions import AppException, UnauthorizedException, app_exception_handler, global_exception_handler
from src.storyline.router import router as storyline_router
from src.users.schemas import UserResponse
from src.upload.router import router as uploader_router


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _make_user(
    user_id: str = "admin-1",
    role: str = "admin",
    email: str = "admin@example.com",
    name: str = "Admin",
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "id": user_id,
        "name": name,
        "email": email,
        "role": role,
        "status": "active",
        "avatar": None,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }


class FakeAuthService:
    async def login(self, request: LoginRequest) -> TokenResponse:
        if request.password != "secret123":
            raise UnauthorizedException("Incorrect email or password")
        u = _make_user(email=request.email, name="Authenticated User")
        return TokenResponse(
            access_token="token-123",
            user=UserResponse(
                id=u["id"],
                name=u["name"],
                email=u["email"],
                role=u["role"],
                status=u["status"],
                avatar=u["avatar"],
                created_at=u["created_at"],
                updated_at=u["updated_at"],
                last_login=u["last_login"],
            ),
        )


@pytest.fixture
def app(tmp_path) -> FastAPI:
    original_storage = settings.storage_root
    settings.storage_root = str(tmp_path / "storage")

    app = FastAPI()
    app.state.authenticated = True
    app.state.current_user = _make_user()

    async def override_current_user():
        if not app.state.authenticated:
            raise UnauthorizedException()
        return app.state.current_user

    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[uploader_get_current_user] = override_current_user
    app.dependency_overrides[AuthService] = lambda: FakeAuthService()

    app.include_router(auth_router, prefix="/api/admin")
    app.include_router(storyline_router, prefix="/api/admin")
    app.include_router(uploader_router, prefix="/api/admin")

    yield app

    settings.storage_root = original_storage


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_state(app: FastAPI):
    def _set(
        *,
        authenticated: bool = True,
        role: str = "admin",
        user_id: str = "admin-1",
        email: str = "admin@example.com",
    ):
        app.state.authenticated = authenticated
        app.state.current_user = _make_user(user_id=user_id, role=role, email=email, name="Test User")

    return _set
