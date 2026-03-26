# syntax=docker/dockerfile:1

# 基础镜像：默认使用阿里云公共库（与 Docker Hub library 同步）。
# 镜像不可用或需直连官方时，构建时传入例如：
#   docker build --build-arg PYTHON_IMAGE=python:3.11-slim .
ARG PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim

# ============================================================
# Stage 1 — Base Image
# ============================================================
FROM ${PYTHON_IMAGE} AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Set PYTHONPATH to include the current directory so "import app" works
ENV PYTHONPATH=/app

# System deps (ffmpeg/fonts used by some media workflows; Playwright brings Chromium).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fontconfig && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Stage 2 — Install dependencies
# ============================================================
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

# ============================================================
# Stage 3 — Copy application code
# ============================================================
# Copy everything from backend/ folder (build context) into /app
COPY . .

# Expose FastAPI port
EXPOSE 8000

# ============================================================
# Entrypoint: run DB init/seed scripts, then start the server
# ============================================================
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
