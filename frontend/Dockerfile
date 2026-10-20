# ============================================================
# 前端镜像（构建上下文 = 仓库根目录，见 deploy/docker-compose.yml）
#   docker build -f frontend/Dockerfile -t fault-frontend .
# 多阶段：node 构建 → nginx 托管静态产物
#
# ⚠ 不要加 `# syntax=docker/dockerfile:1`：BuildKit 会先去 Docker Hub 拉
#   frontend 镜像，国内网络会直接卡在第一步。本文件只用基础语法，不需要它。
#
# 可覆盖的构建参数（compose 里从 .env 透传）：
#   NODE_IMAGE       基础镜像，镜像站受限时改成 docker.m.daocloud.io/library/node:22-alpine
#   NGINX_IMAGE      同上
#   NPM_REGISTRY     npm 源，默认 npmmirror；主机 ~/.npmrc 不会进构建容器
# ============================================================
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:1.25-alpine
FROM ${NODE_IMAGE} AS build

WORKDIR /app

# 构建期注入，Vite 只暴露 VITE_ 前缀变量
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE

# 先只拷清单，利用层缓存：改业务代码不会重装依赖
COPY frontend/package.json frontend/package-lock.json ./

# 构建容器里没有宿主机的 ~/.npmrc，必须显式指定源，否则 npm 直连境外 registry
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm config set fetch-retries 3 \
    && npm config set fetch-timeout 60000 \
    && npm config set fund false \
    && npm config set audit false
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


FROM ${NGINX_IMAGE} AS runtime

# SPA history 回退配置（单一来源：deploy/frontend-nginx.conf）
COPY deploy/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
