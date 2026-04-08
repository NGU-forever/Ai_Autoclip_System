FROM pzm2mntd3t74vneyhy.xuanyuan.run/node:20.19.4-alpine AS web-builder

ENV NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/

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
    PYTHONPATH=/app \
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 \
    DEBIAN_FRONTEND=noninteractive

RUN set -ex \
    && sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's|security.debian.org|mirrors.cloud.tencent.com/debian-security|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto-cjk \
        fonts-unifont \
        fontconfig \
        xvfb \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        curl \
        wget \
        ca-certificates \
    # 安装 Playwright 需要的依赖（基于 Debian Trixie 可用包）
    && apt-get install -y --no-install-recommends \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libatspi2.0-0 \
        libx11-xcb1 \
        libxcb-dri3-0 \
        libxcb1 \
        libdbus-1-3 \
        libexpat1 \
        libglib2.0-0 \
        libgstreamer1.0-0 \
        libgstreamer-plugins-base1.0-0 \
        libgtk-3-0 \
        libgdk-pixbuf-xlib-2.0-0 \
        libxss1 \
        libxtst6 \
        libxshmfence1 \
        libgl1-mesa-dri \
        libosmesa6 \
        mesa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && playwright install chromium \
    && rm -rf /root/.cache/pip

COPY . /app/
COPY --from=web-builder /web/dist /app/web/dist

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]