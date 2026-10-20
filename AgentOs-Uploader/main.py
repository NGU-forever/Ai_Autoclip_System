"""
Uploader 独立进程入口（Docker 容器内 uvicorn 加载 `uploader.main:app`）。
"""

import asyncio
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, JSONResponse

from src.config import settings
from src.exceptions import AppException, app_exception_handler, global_exception_handler
from src.upload.router import router as uploader_router
from src.browser import shutdown_browser_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── 中间件 ──────────────────────────────────────────────────────────────────

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        except Exception as exc:
            # 兼容 BaseHTTPMiddleware 在某些版本中无法正确处理异常响应的问题
            return await global_exception_handler(request, exc)


# ─── 生命周期 ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting uploader service...")

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _on_signal(sig):
        logger.info(f"Received signal {sig}, triggering graceful shutdown...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal, sig)

    async def _watch_shutdown():
        await shutdown_event.wait()
        logger.info("Graceful shutdown: cleaning up browser service...")
        try:
            await asyncio.wait_for(shutdown_browser_service(), timeout=15.0)
        except Exception as exc:
            logger.error(f"Error during graceful shutdown: {exc}")

    shutdown_task = asyncio.create_task(_watch_shutdown())

    # 注册登录成功事件处理
    from src.browser.flows.qr_login import QRLoginFlow
    from src.upload.service import UploaderService

    async def _on_login_success(session):
        try:
            # 3. 更新账号 Cookie
            user_name = session.user_name or f"{session.platform}_user"
            await UploaderService().update_account_cookie(
                platform=session.platform,
                user_name=user_name,
                cookie_filename=session.cookie_file,
            )
            logger.info(f"Successfully registered account {user_name}")
        except Exception as exc:
            logger.error(f"Failed to auto-register account: {exc}")

    QRLoginFlow.register_login_success_handler(_on_login_success)

    # Phase 3: 初始化 SQLite 数据库（建表，幂等）
    try:
        from src.db import init_db
        await init_db()
        logger.info("Database initialized.")
    except Exception:
        logger.exception("Database initialization failed")
        raise

    # API restarts cannot establish whether a separate Worker is still publishing.
    # Keep running tasks unchanged; reconcile only after stopping all Workers and
    # verifying the platform outcome, otherwise manual retry can duplicate a post.

    yield
    logger.info("Shutting down uploader service...")
    shutdown_event.set()
    if not shutdown_task.done():
        try:
            await asyncio.wait_for(shutdown_task, timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Shutdown cleanup timed out")

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.remove_signal_handler(sig)


# ─── 目录确保 ─────────────────────────────────────────────────────────────────

os.makedirs(settings.raw_path, exist_ok=True)
os.makedirs(settings.intermediate_path, exist_ok=True)
os.makedirs(settings.exports_path, exist_ok=True)
os.makedirs(settings.openstoryline_path, exist_ok=True)
os.makedirs(settings.uploader_cookies_path, exist_ok=True)
os.makedirs(settings.uploader_video_path, exist_ok=True)

# ─── FastAPI 应用 ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Uploader Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
cors_origins = settings.cors_origins_list
cors_allow_credentials = settings.cors_allow_credentials
if not cors_origins:
    logger.warning("CORS origins empty, fallback to wildcard without credentials.")
    cors_origins = ["*"]
    cors_allow_credentials = False
elif "*" in cors_origins and cors_allow_credentials:
    logger.warning("CORS misconfigured: wildcard with credentials is invalid; credentials disabled.")
    cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# ─── API 路由 ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "uploader"}


app.include_router(uploader_router, prefix="/api/admin")


# ─── Phase 5: 静态文件 / SPA 托管 ────────────────────────────────────────────
# 使用 StaticFiles 替代手动 SPA 路由，获得标准 HTTP 缓存头、ETag、Range 支持

class SPAStaticFiles(StaticFiles):
    """兼容 WebSocket：非 HTTP 请求不做处理，由 FastAPI 路由处理"""

    async def __call__(self, scope, receive, send):
        # 只处理 HTTP 请求，其他类型（如 WebSocket）直接返回
        if scope["type"] != "http":
            return
        await super().__call__(scope, receive, send)


def _static_dist_dir() -> Path:
    """web/dist：包内路径优先；兼容旧镜像曾使用 /app/web/dist。"""
    pkg = Path(__file__).resolve().parent
    primary = pkg / "web" / "dist"
    if primary.is_dir():
        return primary
    legacy = pkg.parent / "web" / "dist"
    if legacy.is_dir():
        return legacy
    return primary


_STATIC_ROOT = _static_dist_dir()

if _STATIC_ROOT.is_dir():
    # 挂载 /uploader-ui/ 前缀，支持独立运行时直接访问 /uploader-ui/
    app.mount("/uploader-ui", SPAStaticFiles(directory=str(_STATIC_ROOT), html=True), name="spa_prefixed")

    # 挂载 /assets 静态资源（支持浏览器长缓存）
    assets_dir = _STATIC_ROOT / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", SPAStaticFiles(directory=str(assets_dir)), name="assets")

    # SPA 兜底：非 API 路径的 404 回退到 index.html（支持前端客户端路由）
    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            index = _STATIC_ROOT / "index.html"
            if index.is_file():
                return FileResponse(index, headers={"Cache-Control": "no-store"})
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    # 挂载 SPA 根目录（必须在所有路由和 exception_handler 注册之后）
    app.mount("/", SPAStaticFiles(directory=str(_STATIC_ROOT), html=True), name="spa")
else:
    logger.warning(
        "SPA build directory not found at %s. Frontend will not be served.", _STATIC_ROOT
    )

