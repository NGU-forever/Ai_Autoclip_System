"""
Uploader 独立进程入口（Docker 容器内 uvicorn 加载 `uploader.main:app`）。
"""

import logging
import os
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
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


# ─── 生命周期 ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting uploader service...")

    # Phase 3: 初始化 SQLite 数据库（建表，幂等）
    try:
        from src.db import init_db
        await init_db()
        logger.info("Database initialized.")
    except Exception as exc:
        logger.warning("DB init failed (will use JSON fallback): %s", exc)

    # Task Reconciler: 将上次异常退出遗留的 running 任务重置为 failed
    try:
        from src.db import AsyncSessionLocal, TaskRepository
        async with AsyncSessionLocal() as session:
            repo = TaskRepository(session)
            stale = await repo.reconcile_stale()
            await session.commit()
        if stale:
            logger.warning(
                "DB Reconciler 重置了 %d 个孤儿任务，用户可通过 /retry 重新发布。", stale
            )
    except Exception as exc:
        # JSON 回退：兼容旧版 JSON 持久化
        logger.warning("DB reconciler failed, falling back to JSON: %s", exc)
        try:
            from src.upload.service import UploaderService
            stale_json = UploaderService().reconcile_stale_tasks()
            if stale_json:
                logger.warning("JSON Reconciler 重置了 %d 个孤儿任务。", stale_json)
        except Exception as exc2:
            logger.warning("JSON reconciler also failed: %s", exc2)

    yield
    logger.info("Shutting down uploader service...")


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    # 挂载 /assets 静态资源（支持浏览器长缓存）
    assets_dir = _STATIC_ROOT / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA 兜底：非 API 路径的 404 回退到 index.html（支持前端客户端路由）
    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            index = _STATIC_ROOT / "index.html"
            if index.is_file():
                return FileResponse(index)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    # 挂载 SPA 根目录（必须在所有路由和 exception_handler 注册之后）
    app.mount("/", StaticFiles(directory=str(_STATIC_ROOT), html=True), name="spa")
else:
    logger.warning(
        "SPA build directory not found at %s. Frontend will not be served.", _STATIC_ROOT
    )
