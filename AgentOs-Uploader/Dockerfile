FROM pzm2mntd3t74vneyhy.xuanyuan.run/node:20.19.4-alpine AS web-builder

ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com

WORKDIR /web
COPY web/package.json ./
RUN npm install
COPY web/ ./
# 与主站同源/域名一致时需通过 build-arg 覆盖（例如 https://app.example.com）
ARG VITE_LOGIN_PAGE_URL=http://localhost/login
ARG VITE_MAIN_APP_ORIGIN=http://localhost
ENV VITE_LOGIN_PAGE_URL=$VITE_LOGIN_PAGE_URL
ENV VITE_MAIN_APP_ORIGIN=$VITE_MAIN_APP_ORIGIN
RUN npm run build

FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim

ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://registry.npmmirror.com \
    HF_ENDPOINT=https://hf-mirror.com

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/uploader

WORKDIR /app

ARG APT_USE_TENCENT_MIRROR=0
RUN if [ "$APT_USE_TENCENT_MIRROR" = "1" ] && [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
      sed -i 's/security.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && \
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

COPY . /app/uploader/
COPY --from=web-builder /web/dist /app/web/dist

EXPOSE 8002

CMD ["uvicorn", "uploader.main:app", "--host", "0.0.0.0", "--port", "8002"]
