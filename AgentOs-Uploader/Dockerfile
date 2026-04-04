FROM pzm2mntd3t74vneyhy.xuanyuan.run/node:20.19.4-alpine AS web-builder

# 加速 Node 阶段依赖下载（腾讯云 npm 镜像）
ENV NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    HF_ENDPOINT=https://hf-mirror.com

WORKDIR /web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim

ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/uploader

WORKDIR /app

RUN set -ex \
    # 替换以支持公网镜像（腾讯云公网镜像），避免内网镜像在非腾讯云 VPC 环境失败
    && sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list 2>/dev/null || true \
    && sed -i 's|security.debian.org|mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list 2>/dev/null || true \
    # 替换 DEB822 格式的 .sources 文件（Debian 12+）
    && find /etc/apt/sources.list.d/ -name "*.sources" -exec sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' {} \; 2>/dev/null || true \
    && find /etc/apt/sources.list.d/ -name "*.sources" -exec sed -i 's|security.debian.org|mirrors.cloud.tencent.com/debian-security|g' {} \; 2>/dev/null || true \
    # 同时处理遗留的 .list 文件（兼容旧系统）
    && find /etc/apt/sources.list.d/ -name "*.list" -exec sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' {} \; 2>/dev/null || true \
    && find /etc/apt/sources.list.d/ -name "*.list" -exec sed -i 's|security.debian.org|mirrors.cloud.tencent.com/debian-security|g' {} \; 2>/dev/null || true

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fontconfig && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

COPY . /app/
# 与 main.py 中 Path(__file__).parent / "web" / "dist" 一致
COPY --from=web-builder /web/dist /app/web/dist

EXPOSE 8002

ENV PYTHONPATH=/app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
