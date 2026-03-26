# ========================================
# AgentOS Enterprise - Dockerfile
# ========================================

# 默认 Docker Hub 官方 node / nginx；换标签可构建传入，例如：
#   docker build --build-arg NODE_IMAGE=node:22-alpine --build-arg NGINX_IMAGE=nginx:alpine .
FROM node:20-alpine AS builder

# 设置工作目录
WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制源代码
COPY . .

# 构建项目
RUN npm run build

# 生产镜像
FROM nginx:27-alpine AS production

# 复制构建产物到 Nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 可在构建时覆盖 Nginx 配置文件（默认 nginx.conf）
ARG NGINX_CONF=nginx.conf
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]
