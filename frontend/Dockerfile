# ========================================
# AgentOS Enterprise - Dockerfile
# ========================================

# 默认使用阿里云 library 同步镜像；不可用则构建时传入官方名，例如：
#   docker build --build-arg NODE_IMAGE=node:20-alpine --build-arg NGINX_IMAGE=nginx:alpine .
ARG NODE_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/node:20-alpine
ARG NGINX_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/nginx:alpine

FROM ${NODE_IMAGE} AS builder

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
FROM ${NGINX_IMAGE} AS production

# 复制构建产物到 Nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 可在构建时覆盖 Nginx 配置文件（默认 nginx.conf）
ARG NGINX_CONF=nginx.conf
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]
