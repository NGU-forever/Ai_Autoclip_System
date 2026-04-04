#!/bin/bash
#
# AgentOS Uploader - 快速停止所有服务脚本
# 这个脚本会强制停止所有相关的进程和容器
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}💥 正在强制停止所有服务...${NC}"

# 强制终止所有相关的 Python 进程
echo -e "${YELLOW}   停止 Python 相关进程...${NC}"
pkill -9 -f "python.*main.py.*uvicorn" || true
pkill -9 -f "uvicorn.*main:app" || true
pkill -9 -f "uvicorn" || true
pkill -9 -f "watchfiles" || true

# 强制终止 Celery Worker
echo -e "${YELLOW}   停止 Celery Worker...${NC}"
pkill -9 -f "celery.*worker" || true

# 等待进程终止
sleep 2

# 检查并杀死仍在监听端口的进程
UPLOADER_PORT="8002"
if lsof -ti:$UPLOADER_PORT >/dev/null 2>&1; then
    echo -e "${RED}   🔥 端口 $UPLOADER_PORT 仍被占用，强制杀死...${NC}"
    lsof -ti:$UPLOADER_PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 停止 Docker 容器
echo -e "${YELLOW}   停止 Docker 容器...${NC}"
POSTGRES_CONTAINER="uploader-postgres-local"
REDIS_CONTAINER="uploader-redis-local"

for container in "$POSTGRES_CONTAINER" "$REDIS_CONTAINER"; do
    if docker ps --filter "name=$container" --format "{{.Names}}" | grep -q "^${container}$"; then
        docker stop "$container" > /dev/null 2>&1 || true
        echo "   ✅ 已停止 $container"
    fi
done

echo ""
echo -e "${GREEN}✅ 所有服务已停止${NC}"