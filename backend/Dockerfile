FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim

# 轩辕镜像优化：加速依赖下载
ENV NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    HF_ENDPOINT=https://hf-mirror.com

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app


RUN set -ex \
    # 替换传统 sources.list 文件
    && sed -i 's|deb.debian.org|mirrors.tencentyun.com|g' /etc/apt/sources.list 2>/dev/null || true \
    && sed -i 's|security.debian.org|mirrors.tencentyun.com/debian-security|g' /etc/apt/sources.list 2>/dev/null || true \
    # 替换 DEB822 格式的 .sources 文件（Debian 12+）
    && find /etc/apt/sources.list.d/ -name "*.sources" -exec sed -i 's|deb.debian.org|mirrors.tencentyun.com|g' {} \; 2>/dev/null || true \
    && find /etc/apt/sources.list.d/ -name "*.sources" -exec sed -i 's|security.debian.org|mirrors.tencentyun.com/debian-security|g' {} \; 2>/dev/null || true \
    # 同时处理遗留的 .list 文件（兼容旧系统）
    && find /etc/apt/sources.list.d/ -name "*.list" -exec sed -i 's|deb.debian.org|mirrors.tencentyun.com|g' {} \; 2>/dev/null || true \
    && find /etc/apt/sources.list.d/ -name "*.list" -exec sed -i 's|security.debian.org|mirrors.tencentyun.com/debian-security|g' {} \; 2>/dev/null || true

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        fontconfig \
        # 浏览器登录依赖 (VNC + 虚拟显示)
        xvfb \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        curl && \
    rm -rf /var/lib/apt/lists/*

# ============================================================
# Stage 2 — Install dependencies
# ============================================================
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install -r requirements.txt

# ============================================================
# Stage 3 — Copy application code
# ============================================================
# Copy everything from backend/ folder (build context) into /app
COPY . .

# Expose FastAPI port
EXPOSE 8000
# 浏览器登录服务端口
EXPOSE 8003
# noVNC 端口
EXPOSE 6080
# VNC 端口
EXPOSE 5900

# ============================================================
# Entrypoint: run DB init/seed scripts, then start the server
# ============================================================
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
