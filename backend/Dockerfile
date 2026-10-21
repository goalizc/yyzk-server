# ============================================================
# 后端镜像（构建上下文 = 仓库根目录，见 deploy/docker-compose.yml）
#   docker build -f backend/Dockerfile -t fault-backend .
#
# 上下文设为仓库根，是为了让 requirements.txt 与 deploy/scripts/init_admin.py
# 保持单一来源，不在 backend/ 下再复制一份。
#
# ⚠ 不要加 `# syntax=docker/dockerfile:1`：BuildKit 会先去 Docker Hub 拉
#   frontend 镜像，国内网络会直接卡在第一步。本文件只用基础语法，不需要它。
#
# 可覆盖的构建参数（compose 里从 .env 透传）：
#   PYTHON_IMAGE     基础镜像，镜像站受限时改成 docker.m.daocloud.io/library/python:3.12-slim
#   PIP_INDEX_URL    pip 源，默认官方 PyPI（清华源对部分云 IP 返回 403）；
#                    国内慢时在 deploy/.env 改成 https://pypi.tuna.tsinghua.edu.cn/simple
#   PIP_TRUSTED_HOST 对应源的 host
# ============================================================
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 非 root 运行。uid/gid 固定 10001，宿主机挂载的 uploads 目录需 chown 成同一 uid，
# 否则上传会因权限不足失败（S0 尚无上传接口，部署时记得执行）。
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads /app/scripts \
    && chown -R app:app /data /app

# 依赖单独一层，代码改动不会触发重新安装。
# --timeout/--retries 让网络不通时几分钟内报错，而不是一直挂着。
COPY requirements.txt ./requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org
RUN pip install --no-cache-dir \
        --index-url "${PIP_INDEX_URL}" \
        --trusted-host "${PIP_TRUSTED_HOST}" \
        --timeout 30 \
        --retries 2 \
        -r requirements.txt

COPY --chown=app:app backend/app ./app
# 管理员初始化脚本随镜像提供，容器内直接 python /app/scripts/init_admin.py
COPY --chown=app:app deploy/scripts/init_admin.py ./scripts/init_admin.py

USER app

EXPOSE 8000

# 访问日志由应用中间件输出（含 request_id 与耗时），关掉 uvicorn 自带的那条；
# 容器 healthcheck 由 compose 定义（python urllib 探 /api/health，无需 curl）。
# --forwarded-allow-ips 只信任 Docker 私有网段（172.16/12），不信任任意 X-Forwarded-For
#
# ---- workers 数量（压测结论，见 docs/05-评估审查/12-性能压测报告.md）----
# 本项目路由全是同步 def，FastAPI 会把它们丢进 anyio 线程池（默认 40 线程），
# 所以单个 worker 就能吃满 100 并发，多进程并不会带来线性收益。
# 实测（100 并发、混合读写、db 固定 2 核）：
#   CPU=1 核 workers=2 → 264 req/s  P95 486ms（两进程抢一核，上下文切换抵消收益）
#   CPU=1 核 workers=1 → 316 req/s  P95 365ms
#   CPU=2 核 workers=2 → 379 req/s  P95 506ms（吞吐更高但尾部抖动变大）
# 默认 1，需要更多算力时把 compose 的 cpus 和 UVICORN_WORKERS 一起调，别只调一个。
ARG UVICORN_WORKERS=1
ENV UVICORN_WORKERS=${UVICORN_WORKERS}

CMD ["sh", "-c", "exec uvicorn app.main:app \
     --host 0.0.0.0 \
     --port 8000 \
     --workers ${UVICORN_WORKERS} \
     --no-access-log \
     --proxy-headers \
     --forwarded-allow-ips 172.16.0.0/12"]
