# 基础镜像：默认阿里云 library 同步；不可用则构建加参，例如：
#   docker build --build-arg PYTHON_IMAGE=python:3.11-slim .
ARG PYTHON_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim
FROM ${PYTHON_IMAGE}

# 设置工作目录
WORKDIR /app

# 复制文件
COPY requirements.txt .
# 安装依赖
RUN apt-get update && apt-get install -y ffmpeg wget unzip git git-lfs curl
RUN pip install --no-cache-dir -r requirements.tx

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