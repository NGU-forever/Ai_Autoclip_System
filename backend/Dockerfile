FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim

# 轩辕镜像优化：加速依赖下载
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://registry.npmmirror.com \
    HF_ENDPOINT=https://hf-mirror.com

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Set PYTHONPATH to include the current directory so "import app" works
ENV PYTHONPATH=/app

# System deps (ffmpeg/fonts for media workflows; Playwright/Chromium 仅在仓库根目录 AgentOs-Uploader/Dockerfile 构建的镜像中安装).
RUN sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
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
    pip install --no-cache-dir -r requirements.txt

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
