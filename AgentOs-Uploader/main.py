"""
Uploader 独立进程入口（Docker 容器内 uvicorn 加载 `uploader.main:app`）。
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.exceptions import AppException, app_exception_handler, global_exception_handler
from uploader.router import router as uploader_router

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting uploader service...")
    yield
    logger.info("Shutting down uploader service...")


os.makedirs(settings.raw_path, exist_ok=True)
os.makedirs(settings.intermediate_path, exist_ok=True)
os.makedirs(settings.exports_path, exist_ok=True)
os.makedirs(settings.openstoryline_path, exist_ok=True)
os.makedirs(settings.uploader_cookies_path, exist_ok=True)
os.makedirs(settings.uploader_video_path, exist_ok=True)

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


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "uploader"}


app.include_router(uploader_router, prefix="/api/admin")
