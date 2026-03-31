FROM pzm2mntd3t74vneyhy.xuanyuan.run/node:20.19.4-alpine AS webbuilder

WORKDIR /build/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY web/ ./
RUN npm run build

FROM mirror.ccs.tencentyun.com/library/python:3.11-slim

# 轩辕镜像优化：加速依赖下载
ENV NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://mirrors.cloud.tencent.com/npm/ \
    HF_ENDPOINT=https://hf-mirror.com

# 设置工作目录
WORKDIR /app

# 复制文件
COPY requirements.txt .
# 腾讯云内网 apt 加速（本地 / 非腾讯云构建勿开：mirrors.tencentyun.com 外网不可达）
ARG APT_USE_TENCENT_MIRROR=1
# 安装依赖
RUN if [ "$APT_USE_TENCENT_MIRROR" = "1" ]; then \
      sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
      sed -i 's/security.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        wget \
        unzip \
        git \
        git-lfs \
        curl && \
    rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

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