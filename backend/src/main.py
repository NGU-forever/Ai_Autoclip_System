import logging
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.config import settings
from src.database import init_db_pool, close_db_pool
from src.exceptions import AppException, app_exception_handler, global_exception_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


# Ensure storage directories always exist before mounting.
os.makedirs(settings.raw_path, exist_ok=True)
os.makedirs(settings.intermediate_path, exist_ok=True)
os.makedirs(settings.exports_path, exist_ok=True)
os.makedirs(settings.uploader_cookies_path, exist_ok=True)
os.makedirs(settings.uploader_video_path, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up AgentOS Enterprise API...")
    init_db_pool()
    yield
    logger.info("Shutting down AgentOS Enterprise API...")
    close_db_pool()


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
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


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": settings.project_name}


app.mount("/storage/exports", StaticFiles(directory=settings.exports_path), name="storage-exports")

from src.auth.router import router as auth_router
from src.storyline.router import router as storyline_router
from src.uploader.router import router as uploader_router

app.include_router(auth_router, prefix="/api/admin")
app.include_router(storyline_router, prefix="/api/admin")
app.include_router(uploader_router, prefix="/api/admin")
