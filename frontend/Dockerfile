# ========================================
# AgentOS Enterprise - Dockerfile
# ========================================
FROM pzm2mntd3t74vneyhy.xuanyuan.run/node:20.19.4-alpine AS builder

# 轩辕镜像优化：加速依赖下载
ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    GOPROXY=https://goproxy.cn,direct \
    YARN_REGISTRY=https://registry.npmmirror.com \
    HF_ENDPOINT=https://hf-mirror.com

# 设置工作目录
WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制源代码
COPY . .

# qiankun 子应用 entry（生产为同源 /uploader-ui/、/openstoryline-ui/，由 Nginx 反代）
ARG VITE_UPLOADER_QIANKUN_ENTRY=/uploader-ui/
ENV VITE_UPLOADER_QIANKUN_ENTRY=$VITE_UPLOADER_QIANKUN_ENTRY
ARG VITE_OPENSTORYLINE_QIANKUN_ENTRY=/openstoryline-ui/
ENV VITE_OPENSTORYLINE_QIANKUN_ENTRY=$VITE_OPENSTORYLINE_QIANKUN_ENTRY

# 构建项目
RUN npm run build

# 生产镜像
FROM pzm2mntd3t74vneyhy.xuanyuan.run/nginx:1.27.2-alpine AS production

# 复制构建产物到 Nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 可在构建时覆盖 Nginx 配置文件（默认 nginx.conf）
ARG NGINX_CONF=nginx.conf
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]