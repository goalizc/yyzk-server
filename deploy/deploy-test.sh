#!/usr/bin/env bash
# ============================================================
# 测试栈部署（与生产同机，独立数据库 / 上传目录 / 端口）
#
#   生产：docker compose up -d            → http://<host>/
#   测试：./deploy-test.sh                → http://<host>:8080/
#
# 测试栈使用 .env.test + docker-compose.test.yml；数据库与上传目录
# 都在 deploy/data-test/ 下，不会碰生产数据。
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEPLOY_DIR"

COMPOSE=(
  docker compose
  -p fault-test
  --env-file .env.test
  -f docker-compose.yml
  -f docker-compose.test.yml
)

[[ -f .env.test ]] || { echo "[deploy-test] 缺少 .env.test" >&2; exit 2; }

# 上传目录由 backend uid 10001 写入；用一次性 root 容器修属主，避免依赖 sudo
mkdir -p data-test/uploads
docker run --rm -u 0 -v "$DEPLOY_DIR/data-test/uploads:/d" nginx:1.25-alpine \
  chown -R 10001:10001 /d

echo "[deploy-test] 构建测试镜像"
"${COMPOSE[@]}" build

echo "[deploy-test] 启动测试数据库"
"${COMPOSE[@]}" up -d db

echo "[deploy-test] 等待数据库健康"
for _ in $(seq 1 60); do
  status="$(docker inspect --format '{{.State.Health.Status}}' fault-test-db 2>/dev/null || true)"
  [[ "$status" == "healthy" ]] && break
  sleep 1
done
[[ "${status:-}" == "healthy" ]] || { echo "[deploy-test] 数据库未就绪" >&2; exit 1; }

echo "[deploy-test] 执行迁移"
"${COMPOSE[@]}" --profile migrate run --rm migrate

echo "[deploy-test] 初始化管理员（已存在则跳过）"
"${COMPOSE[@]}" --profile init run --rm init

echo "[deploy-test] 启动测试栈"
"${COMPOSE[@]}" up -d

echo "[deploy-test] 健康检查"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
    echo "[deploy-test] 完成：http://127.0.0.1:8080/"
    exit 0
  fi
  sleep 1
done

echo "[deploy-test] 健康检查失败，请查看：docker compose -p fault-test logs backend" >&2
exit 1
