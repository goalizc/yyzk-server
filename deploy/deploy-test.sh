#!/usr/bin/env bash
# ============================================================
# 测试栈部署（与生产同机，独立数据库 / 上传目录 / 端口）
#
#   生产：docker compose up -d            → http://<host>/
#   测试：./deploy-test.sh                → http://<host>:8080/
#
# 测试栈使用 .env.test + docker-compose.test.yml；数据库与上传目录
# 都在 DATA_DIR（默认 deploy/data-test/）下，不会碰生产数据。
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEPLOY_DIR"

[[ -f .env.test ]] || { echo "[deploy-test] 缺少 .env.test" >&2; exit 2; }

# 与 compose 共用 .env.test，避免脚本与编排各写死一套
env_value() {
  grep -E "^$1=" .env.test 2>/dev/null | head -1 | sed -E "s/^$1=//" | sed -E 's/[[:space:]]+$//' | tr -d "\"'" || true
}
STACK_PREFIX="$(env_value STACK_PREFIX)"
[[ -n "$STACK_PREFIX" ]] || { echo "[deploy-test] .env.test 缺少 STACK_PREFIX" >&2; exit 2; }
[[ "$STACK_PREFIX" != "fault" ]] || {
  echo "[deploy-test] STACK_PREFIX 不能与生产栈 fault 相同" >&2
  exit 2
}
HTTP_PORT="$(env_value HTTP_PORT)"
[[ -n "$HTTP_PORT" ]] || { echo "[deploy-test] .env.test 缺少 HTTP_PORT" >&2; exit 2; }
HTTP_BIND="$(env_value HTTP_BIND)"
HTTP_BIND="${HTTP_BIND:-127.0.0.1}"
DATA_DIR="$(env_value DATA_DIR)"
[[ -n "$DATA_DIR" ]] || { echo "[deploy-test] .env.test 缺少 DATA_DIR" >&2; exit 2; }
case "$DATA_DIR" in
  /*)   DATA_PATH="$DATA_DIR" ;;
  ./*)  DATA_PATH="$DEPLOY_DIR/${DATA_DIR#./}" ;;
  *)    DATA_PATH="$DEPLOY_DIR/$DATA_DIR" ;;
esac
case "$DATA_PATH" in
  "$DEPLOY_DIR/data"|"$DEPLOY_DIR/data/"*)
    echo "[deploy-test] DATA_DIR 不能指向生产数据目录 deploy/data" >&2
    exit 2
    ;;
esac

# 显式导出：即使 .env.test 漏键，Compose 也必须使用脚本校验过的值
export STACK_PREFIX HTTP_PORT HTTP_BIND DATA_DIR

COMPOSE=(
  docker compose
  -p "$STACK_PREFIX"
  --env-file .env.test
  -f docker-compose.yml
  -f docker-compose.test.yml
)

# 上传目录由 backend uid 10001 写入；用一次性 root 容器修属主，避免依赖 sudo
mkdir -p "$DATA_PATH/uploads"
docker run --rm -u 0 -v "$DATA_PATH/uploads:/d" nginx:1.25-alpine \
  chown -R 10001:10001 /d

echo "[deploy-test] 构建测试镜像"
"${COMPOSE[@]}" build

echo "[deploy-test] 启动测试数据库"
"${COMPOSE[@]}" up -d db

echo "[deploy-test] 等待数据库健康"
for _ in $(seq 1 60); do
  status="$(docker inspect --format '{{.State.Health.Status}}' "${STACK_PREFIX}-db" 2>/dev/null || true)"
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
  if curl -fsS "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
    echo "[deploy-test] 完成：http://127.0.0.1:${HTTP_PORT}/"
    exit 0
  fi
  sleep 1
done

echo "[deploy-test] 健康检查失败，请查看：docker compose -p ${STACK_PREFIX} logs backend" >&2
exit 1
