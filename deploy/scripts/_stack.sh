#!/usr/bin/env bash
# ============================================================
# 双栈运维脚本的公共环境层（审查报告 21 · C-02）
#
# 背景：deploy/scripts/ 下的 backup / restore / harden / cleanup-* 原先
#       把容器名、库名、数据目录全部写死成生产值，且 `docker compose` 不带
#       -p。在「测试栈语境」下执行这些脚本会静默打到生产栈，其中 restore.sh
#       还会把备份灌进生产库（不可逆）。
#
# 用法：在脚本里 `source "$SCRIPT_DIR/_stack.sh"`，然后
#   - 用 compose() 代替裸 `docker compose`
#   - 用 $DB_CONTAINER / $BACKEND_CONTAINER / $UPLOADS_DIR / $DATA_PATH
#     代替 fault-db / data/uploads 等硬编码值
#   - 破坏性操作前调用 stack_banner() + stack_confirm()
#
# 切换目标栈（环境变量，默认完全是改造前的行为）：
#   STACK_ENV_FILE=.env                 # 默认，生产
#   STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test   # 测试栈
#   例：STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/backup.sh --dry-run
#
# 注意：生产栈的 compose 项目名是 deploy（deploy.sh 不带 -p），容器名却是
#       fault-*；所以 STACK_PROJECT 留空时才等价于既有生产行为，**不要**给
#       生产栈显式传 -p fault，那会新建一套孤立容器。
# ============================================================

# 调用方已设置 set -euo pipefail；本文件不重复设置，也不修改调用方的 shell 选项。
STACK_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_DEPLOY_DIR="$(cd "$STACK_LIB_DIR/.." && pwd)"

STACK_ENV_FILE="${STACK_ENV_FILE:-.env}"
STACK_PROJECT="${STACK_PROJECT:-}"
case "$STACK_ENV_FILE" in
  /*) STACK_ENV_PATH="$STACK_ENV_FILE" ;;
  *)  STACK_ENV_PATH="$STACK_DEPLOY_DIR/$STACK_ENV_FILE" ;;
esac
COMPOSE_FILE="$STACK_DEPLOY_DIR/docker-compose.yml"

stack_env_value() {
  local key="$1"
  [[ -f "$STACK_ENV_PATH" ]] || return 0
  grep -E "^${key}=" "$STACK_ENV_PATH" 2>/dev/null | head -1 \
    | sed -E "s/^${key}=//" | sed -E 's/[[:space:]]+$//' | tr -d "\"'" || true
}

STACK_PREFIX="$(stack_env_value STACK_PREFIX)"
STACK_PREFIX="${STACK_PREFIX:-fault}"
DB_CONTAINER="${STACK_PREFIX}-db"
BACKEND_CONTAINER="${STACK_PREFIX}-backend"

DATA_DIR="$(stack_env_value DATA_DIR)"
DATA_DIR="${DATA_DIR:-./data}"
case "$DATA_DIR" in
  /*) DATA_PATH="$DATA_DIR" ;;
  ./*) DATA_PATH="$STACK_DEPLOY_DIR/${DATA_DIR#./}" ;;
  *)   DATA_PATH="$STACK_DEPLOY_DIR/$DATA_DIR" ;;
esac
# 规范化：消除 ../ 之类的路径写法，避免测试栈绕过校验挂到生产数据目录（M-08）
if command -v realpath >/dev/null 2>&1; then
  DATA_PATH="$(realpath -m "$DATA_PATH")"
fi
UPLOADS_DIR="$DATA_PATH/uploads"

stack_require_env() {
  [[ -f "$STACK_ENV_PATH" ]] || {
    echo "[stack] 找不到环境变量文件：$STACK_ENV_PATH" >&2
    exit 2
  }
}

# 统一的 compose 包装：只有显式指定了 STACK_PROJECT 才带 -p。
# 空值 = compose 默认项目名 deploy（与 deploy.sh 的生产栈一致）。
compose() {
  local -a args=()
  if [[ -n "$STACK_PROJECT" ]]; then
    args+=(-p "$STACK_PROJECT")
  fi
  args+=(--env-file "$STACK_ENV_PATH" -f "$COMPOSE_FILE")
  docker compose "${args[@]}" "$@"
}

stack_banner() {
  local label="${1:-操作}"
  echo "[stack] ${label}目标：env=$STACK_ENV_FILE | 项目=${STACK_PROJECT:-deploy(默认)} | 容器=${STACK_PREFIX}-* | DB容器=$DB_CONTAINER | 数据=$DATA_PATH"
}

# 破坏性操作确认：非交互执行（cron / CI）只打印目标栈，不阻塞。
stack_confirm() {
  local label="${1:-操作}" ans
  if [[ ! -t 0 ]]; then
    echo "[stack] 非交互执行，跳过交互确认（目标栈见上一行）" >&2
    return 0
  fi
  read -r -p "[stack] 确认对以上目标栈执行「${label}」？(y/N) " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "[stack] 已取消" >&2; exit 1; }
}
