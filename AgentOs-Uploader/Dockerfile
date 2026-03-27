FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim

ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://registry.npmmirror.com \
    HF_ENDPOINT=https://hf-mirror.com

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ENV PYTHONPATH=/app/backend:/app

RUN sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fontconfig && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements-uploader.txt /tmp/requirements-uploader.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements-uploader.txt && \
    playwright install chromium && \
    playwright install-deps chromium

COPY backend /app/backend
COPY AgentOs-Uploader /app/uploader

EXPOSE 8002

CMD ["uvicorn", "uploader.main:app", "--host", "0.0.0.0", "--port", "8002"]
