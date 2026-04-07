FROM pzm2mntd3t74vneyhy.xuanyuan.run/node:20.19.4-alpine AS webbuilder

# 加速 Node 阶段依赖下载（腾讯云 npm 镜像）
ENV NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    HF_ENDPOINT=https://hf-mirror.com

WORKDIR /build/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY web/ ./
RUN npm run build

FROM pzm2mntd3t74vneyhy.xuanyuan.run/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/openstoryline

# 设置工作目录
WORKDIR /app

# 复制文件
COPY requirements.txt .

# 无条件替换为腾讯云镜像（推荐）
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

# 更新并安装软件包
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        wget \
        unzip \
        git \
        git-lfs \
        curl && \
    rm -rf /var/lib/apt/lists/*

# 4. 配置 pip 镜像（加速 Python 依赖安装）
RUN pip config set global.index-url https://mirrors.tencentyun.com/pypi/simple

# 5. 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install -r requirements.txt

COPY run.sh .
COPY src/ ./src/
COPY agent_fastapi.py .
COPY cli.py .
COPY config.toml .
COPY web/ ./web/
COPY --from=webbuilder /build/web/dist ./web/dist
COPY prompts/ ./prompts/
COPY .storyline/ ./.storyline/
# 大资源不在镜像构建时下载：请在宿主机本目录先执行 `bash download.sh`，生成 `.storyline/models`、`.storyline` 内其它产物及 `resource/`、并更新 `web/legacy/static`。
# 使用 docker-compose 时请将上述目录挂载进容器（与 README / compose 说明一致）。

# 暴露 HF Space 默认端口
EXPOSE 7860

# 启动命令
CMD ["bash", "run.sh"]