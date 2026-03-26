FROM python:3.11-slim

# 轩辕镜像优化：加速依赖下载
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
    PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://registry.npmmirror.com \
    HF_ENDPOINT=https://hf-mirror.com

# 设置工作目录
WORKDIR /app

# 复制文件
COPY requirements.txt .
# 安装依赖
RUN sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources && \
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
COPY prompts/ ./prompts/
COPY .storyline/ ./.storyline/
COPY download.sh .
# 下载
RUN chmod +x download.sh
RUN ./download.sh

# 暴露 HF Space 默认端口
EXPOSE 7860

# 启动命令
CMD ["bash", "run.sh"]