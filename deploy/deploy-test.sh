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
# 规范化路径：`DATA_DIR=./data-test/../data` 这类写法能绕过下面的字符串前缀
# 校验（审查 M-08），必须先 realpath 再比较。
if command -v realpath >/dev/null 2>&1; then
  DATA_PATH="$(realpath -m "$DATA_PATH")"
fi
DEPLOY_REAL="$(realpath -m "$DEPLOY_DIR" 2>/dev/null || echo "$DEPLOY_DIR")"
case "$DATA_PATH" in
  "$DEPLOY_REAL/data"|"$DEPLOY_REAL/data/"*)
    echo "[deploy-test] DATA_DIR 不能指向生产数据目录 deploy/data（解析后：$DATA_PATH）" >&2
    exit 2
    ;;
esac

# 占位符/弱口令检测：.env.test.example 里是 CHANGEME，没改就会用弱口令起栈
for key in JWT_SECRET DB_PASSWORD ADMIN_INIT_PASSWORD; do
  val="$(env_value "$key")"
  case "$val" in
    ""|CHANGEME*|changeme*|请改成*|请设置*|your-*|your_*|xxx*|placeholder*|secret|password|123456*)
      echo "[deploy-test] .env.test 的 $key 仍是空值或占位符，请先改成随机值（openssl rand -hex 32）" >&2
      exit 2
      ;;
  esac
done

# 与生产隔离：共用库名会直接连到生产库；共用 JWT 会让测试 token 在生产同样有效
if [[ -f .env ]]; then
  prod_env() {
    grep -E "^$1=" .env 2>/dev/null | head -1 | sed -E "s/^$1=//" \
      | sed -E 's/[[:space:]]+$//' | tr -d "\"'"
  }
  if [[ -n "$(prod_env DB_NAME)" && "$(env_value DB_NAME)" == "$(prod_env DB_NAME)" ]]; then
    echo "[deploy-test] .env.test 的 DB_NAME 与生产相同，测试栈会连到生产库" >&2
    exit 2
  fi
  if [[ -n "$(prod_env JWT_SECRET)" && "$(env_value JWT_SECRET)" == "$(prod_env JWT_SECRET)" ]]; then
    echo "[deploy-test] .env.test 的 JWT_SECRET 与生产相同：测试环境签发的 token 在生产同样有效" >&2
    exit 2
  fi
  prod_port="$(prod_env HTTP_PORT)"
  prod_port="${prod_port:-80}"
  if [[ "$HTTP_PORT" == "$prod_port" ]]; then
    echo "[deploy-test] HTTP_PORT 与生产相同（$prod_port），两栈会抢同一端口" >&2
    exit 2
  fi
fi

# 显式导出：即使 .env.test 漏键，Compose 也必须使用脚本校验过的值
export STACK_PREFIX HTTP_PORT HTTP_BIND DATA_DIR

# 测试栈刻意 DEBUG=true，但再叠加 0.0.0.0 就等于把 /api/docs 暴露给整个网络
if [[ "$(env_value DEBUG)" == "true" && "$HTTP_BIND" == "0.0.0.0" ]]; then
  echo "[deploy-test] [警告] DEBUG=true 且 HTTP_BIND=0.0.0.0：调试接口暴露到内网，建议 HTTP_BIND=127.0.0.1" >&2
fi

COMPOSE=(
  docker compose
  -p "$STACK_PREFIX"
  --env-file .env.test
  -f docker-compose.yml
  -f docker-compose.test.yml
)

echo "[deploy-test] 构建测试镜像"
"${COMPOSE[@]}" build

# 上传目录由 backend uid 10001 写入。用刚构建好的 backend 镜像在容器内 chown，
# 不需要宿主机 sudo，与生产 deploy.sh 的做法保持一致（审查 M-05）。
# 必须先 build：原先用 nginx 镜像做 chown，镜像不在时脚本会在 build 前就失败。
mkdir -p "$DATA_PATH/uploads"
if ! "${COMPOSE[@]}" run --rm --no-deps -T -u root backend \
      sh -c "chown -R 10001:10001 /data/uploads" >/dev/null 2>&1; then
  echo "[deploy-test] 上传目录属主修正失败，请手工执行：" >&2
  echo "  sudo chown -R 10001:10001 $DATA_PATH/uploads" >&2
  exit 1
fi

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
# 注意：nginx 的 /health 是 `return 200 "ok"`，不经过 backend/db，
# 只查它会得到假阳性（审查 M-03）。这里必须查后端自己的 /api/health，
# 并用一个未带 token 的管理接口确认鉴权链路也是通的（期望 401）。
BASE="http://127.0.0.1:${HTTP_PORT}"
code_health=""
code_api=""
for _ in $(seq 1 60); do
  code_health="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/health" 2>/dev/null || true)"
  code_api="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/admin/products" 2>/dev/null || true)"
  [[ "$code_health" == "200" && "$code_api" == "401" ]] && break
  sleep 1
done

if [[ "$code_health" != "200" || "$code_api" != "401" ]]; then
  echo "[deploy-test] 健康检查失败：/api/health=$code_health（期望 200）、/api/admin/products=$code_api（期望 401）" >&2
  echo "[deploy-test] 目标：http://127.0.0.1:${HTTP_PORT}（env=.env.test 项目=${STACK_PREFIX}）" >&2
  echo "[deploy-test] 排查：docker compose -p ${STACK_PREFIX} --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml logs backend --tail 50" >&2
  exit 1
fi

if curl -fsS -o /dev/null "$BASE/" 2>/dev/null; then
  echo "[deploy-test] 完成：$BASE/"
else
  echo "[deploy-test] 后端就绪，但 SPA 首页未返回 200：$BASE/" >&2
  exit 1
fi
exit 0
