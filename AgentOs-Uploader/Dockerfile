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

# 第一阶段：系统依赖安装（使用腾讯云镜像加速）
FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim AS system-deps

ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com

# 替换 apt 源为腾讯云镜像（加速系统依赖下载）
RUN set -ex \
    && sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's|security.debian.org|mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fontconfig \
        xvfb \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

# 复制应用代码
COPY . /app/
COPY --from=web-builder /web/dist /app/web/dist

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]