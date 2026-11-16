#!/usr/bin/env bash
# ============================================================
# 售后故障诊断系统 - 生产环境配置加固
#
# 作用：把 .env 里所有占位/弱口令替换成随机强值，并做一次上线前体检。
#
# 用法：
#   ./harden.sh              # 生成/修正 .env（已存在的强值不动）
#   ./harden.sh --check      # 只体检，不修改
#   ./harden.sh --force      # 强制重新生成所有密钥（注意：会让现有 token 全部失效）
#
# ------------------------------------------------------------
# 对应验收表（docs/03-测试与验收/验收检查表.md 四、安全验收）：
#   - JWT_SECRET 已改成随机串（不是默认值，长度 ≥ 32）
#   - DB 密码已改成强密码（≥ 16 位，hex 生成）
#   - 仓库与镜像中不存在硬编码的真实密码
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
EXAMPLE_FILE="$DEPLOY_DIR/.env.example"
MODE="fix"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --force) MODE="force"; shift ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1" >&2; exit 2 ;;
  esac
done

log()  { echo "[harden] $*"; }
warn() { echo "[harden] [警告] $*" >&2; }
fail() { echo "[harden] [不合格] $*" >&2; FAILED=$((FAILED + 1)); }
FAILED=0

cd "$DEPLOY_DIR"

# 双栈环境层：默认生产 .env；测试栈应指向 .env.test。
# 注意测试栈刻意 DEBUG=true（.env.test.example 里就这么配），
# 所以 DEBUG 强制关闭一项只对生产栈生效，别把测试栈改坏。
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_stack.sh"
ENV_FILE="$STACK_ENV_PATH"
case "$STACK_ENV_FILE" in
  /*) EXAMPLE_FILE="${STACK_ENV_PATH}.example" ;;
  *)  EXAMPLE_FILE="$DEPLOY_DIR/${STACK_ENV_FILE}.example" ;;
esac
stack_banner "配置加固"

# 下面所有「手工执行」提示里的命令都必须带上目标栈，否则测试栈用户
# 复制粘贴会打到生产栈（审查 C-02 的同类问题）。
COMPOSE_HINT="docker compose"
if [[ -n "$STACK_PROJECT" ]]; then
  COMPOSE_HINT="docker compose -p $STACK_PROJECT"
fi
COMPOSE_HINT="$COMPOSE_HINT --env-file $STACK_ENV_PATH -f $COMPOSE_FILE"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$EXAMPLE_FILE" ]]; then
    log ".env 不存在，从 .env.example 复制一份"
    cp "$EXAMPLE_FILE" "$ENV_FILE"
  else
    echo "[ERROR] 既没有 .env 也没有 .env.example" >&2
    exit 2
  fi
fi

# 从 .env 读一个键的值（不 source，避免值里的特殊字符被执行）
get_env() {
  local key="$1"
  # 去掉可能的引号和行尾空白
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 \
    | sed -E "s/^${key}=//" | sed -E 's/[[:space:]]+$//' | tr -d "\"'" || true
}

# 写入/更新一个键（保留其他内容与顺序）
set_env() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # 用 | 作分隔符，避免 value 里含 / 时出错
    sed -i.bak -E "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

gen_hex() { openssl rand -hex "$1"; }

# ---------- 判定"是否已经是强值" ----------
# 弱值清单：示例占位、常见默认、空
is_weak() {
  local v="$1" min="$2"
  [[ -z "$v" ]] && return 0
  [[ ${#v} -lt $min ]] && return 0
  case "$v" in
    CHANGEME*|changeme*|your-*|your_*|xxx*|placeholder*|secret|password|123456*|admin*)
      return 0 ;;
  esac
  return 1
}

# ---------- 记录改动前的原始值（用于事后判断哪些密钥变了） ----------
ORIG_JWT="$(get_env JWT_SECRET)"
ORIG_DB="$(get_env DB_PASSWORD)"

# ---------- 1. JWT_SECRET ----------
JWT_VAL="$(get_env JWT_SECRET)"
if [[ "$MODE" == "force" ]] || is_weak "$JWT_VAL" 32; then
  if [[ "$MODE" == "check" ]]; then
    fail "JWT_SECRET 未设置或过弱（需 ≥32 位随机串，用 openssl rand -hex 32 生成）"
  else
    NEW="$(gen_hex 32)"
    set_env JWT_SECRET "$NEW"
    log "JWT_SECRET 已生成（64 位 hex）"
  fi
else
  log "JWT_SECRET 合格（长度 ${#JWT_VAL}）"
fi

# ---------- 2. DB_PASSWORD ----------
DB_VAL="$(get_env DB_PASSWORD)"
if [[ "$MODE" == "force" ]] || is_weak "$DB_VAL" 16; then
  if [[ "$MODE" == "check" ]]; then
    fail "DB_PASSWORD 未设置或过弱（需 ≥16 位）"
  else
    NEW="$(gen_hex 16)"
    set_env DB_PASSWORD "$NEW"
    log "DB_PASSWORD 已生成（32 位 hex）"
  fi
else
  log "DB_PASSWORD 合格（长度 ${#DB_VAL}）"
fi

# ---------- 3. 初始管理员密码 ----------
ADMIN_VAL="$(get_env ADMIN_INIT_PASSWORD)"
if [[ "$MODE" == "force" ]] || is_weak "$ADMIN_VAL" 12; then
  if [[ "$MODE" == "check" ]]; then
    # 计入失败而不是只警告：体检里"通过"和"有问题的项"并存，
    # 会让人只看到"通过"就跳过。不合格就是不通过。
    fail "ADMIN_INIT_PASSWORD 未设置或过弱（建议 ≥12 位随机串）"
  else
    NEW="$(gen_hex 8)"
    set_env ADMIN_INIT_PASSWORD "$NEW"
    log "ADMIN_INIT_PASSWORD 已生成，请记录下来（首次 init 后会写入数据库）"
  fi
fi

# ---------- 4. DEBUG 必须关闭（仅生产栈） ----------
# 测试栈刻意 DEBUG=true（.env.test.example 就是这么配的）：方便看 /api/docs
# 与完整报错。这条体检只对生产栈生效，否则会把测试栈改坏。
IS_TEST_STACK=0
if [[ "$STACK_ENV_FILE" == *test* || -n "$STACK_PROJECT" ]]; then
  IS_TEST_STACK=1
fi

DEBUG_VAL="$(get_env DEBUG)"
if [[ "$IS_TEST_STACK" == "1" ]]; then
  log "测试栈（env=$STACK_ENV_FILE）：跳过 DEBUG 强制关闭，当前 DEBUG=${DEBUG_VAL:-未设置}"
elif [[ "$DEBUG_VAL" == "true" ]]; then
  if [[ "$MODE" == "check" ]]; then
    fail "DEBUG=true：生产环境会暴露 /api/docs 与 OpenAPI"
  else
    set_env DEBUG "false"
    log "DEBUG 已改为 false（生产不应暴露接口文档）"
  fi
else
  log "DEBUG 未开启"
fi

# ---------- 5. 体检：密钥是否泄漏进仓库 ----------
log "检查仓库中是否有真实密钥被提交..."
LEAK=0
for f in "$DEPLOY_DIR/docker-compose.yml" "$DEPLOY_DIR/nginx.conf"; do
  [[ -f "$f" ]] || continue
  if grep -qE "JWT_SECRET:.*[a-f0-9]{32,}" "$f" 2>/dev/null; then
    fail "$(basename "$f") 里疑似硬编码了 JWT_SECRET"
    LEAK=1
  fi
done
# env 文件应被 gitignore（按目标栈判定，测试栈查 .env.test 而不是 .env）
ENV_REL="$(basename "$STACK_ENV_FILE")"
if git -C "$DEPLOY_DIR/.." check-ignore -q "deploy/$ENV_REL" 2>/dev/null; then
  log "deploy/$ENV_REL 已被 gitignore 忽略"
elif [[ -d "$DEPLOY_DIR/../.git" ]]; then
  fail "deploy/$ENV_REL 未被 gitignore 忽略，密码有被提交的风险"
fi

# ---------- 汇总 ----------
echo ""
if [[ "$MODE" == "check" ]]; then
  if [[ $FAILED -gt 0 ]]; then
    echo "[harden] 体检未通过：$FAILED 项不合格。执行 ./scripts/harden.sh 自动修正。"
    exit 1
  fi
  echo "[harden] 体检通过"
  exit 0
fi

echo "[harden] 配置已加固。下一步："
echo "  1. 查看 .env 中的 ADMIN_INIT_PASSWORD 并记录"
echo "  2. $COMPOSE_HINT up -d && $COMPOSE_HINT run --rm init"
echo "  3. 首次登录后立即在后台修改密码"
echo ""

# ------------------------------------------------------------
# 改 DB_PASSWORD 时的隐藏炸弹（实测踩到过）：
#   Postgres 的 POSTGRES_PASSWORD 只在**数据目录为空时**生效。
#   已有 ./data/pg 的情况下改 .env 里的密码：
#     - 容器会被重建，但库里的用户密码还是旧的
#     - backend 用新密码连库 → password authentication failed → 一直 unhealthy
#   所以改密码必须同时改数据库里的实际密码。这里直接问一次要不要代劳。
# ------------------------------------------------------------
DB_USER_VAL="$(get_env DB_USER)"
DB_USER_VAL="${DB_USER_VAL:-fault}"
DB_NAME_VAL="$(get_env DB_NAME)"
DB_NAME_VAL="${DB_NAME_VAL:-fault_db}"
NEW_DB="$(get_env DB_PASSWORD)"
if [[ "$NEW_DB" != "$ORIG_DB" && -n "$ORIG_DB" ]]; then
  if [[ -d "$DATA_PATH/pg" && -n "$(ls -A "$DATA_PATH/pg" 2>/dev/null)" ]]; then
    echo "[harden] ⚠ DB_PASSWORD 已变更，但已有数据目录，库里的密码还是旧的。"
    if [[ -t 0 ]]; then
      read -r -p "[harden] 现在同步到数据库并重建 backend？(y/N) " ans
      if [[ "$ans" =~ ^[Yy]$ ]]; then
        if compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q "$DB_CONTAINER"; then
          # 用旧密码连进去改（此时若能 exec 成功说明会话信任本机，无需密码）
          compose exec -T db psql -U "$DB_USER_VAL" -d "$DB_NAME_VAL" -q \
            -c "ALTER USER $DB_USER_VAL WITH PASSWORD '$NEW_DB';" \
            && log "数据库密码已同步" || warn "同步失败，请手工执行 ALTER USER"

          if compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q "$BACKEND_CONTAINER"; then
            log "重建 backend 使新密码生效..."
            compose up -d --force-recreate backend >/dev/null 2>&1 || true
            log "backend 已重建，请用 $COMPOSE_HINT ps 确认 healthy"
          fi
        else
          warn "$DB_CONTAINER 未运行，无法同步。启动后手工执行："
          echo "      $COMPOSE_HINT exec -T db psql -U $DB_USER_VAL -d $DB_NAME_VAL -c \"ALTER USER $DB_USER_VAL WITH PASSWORD '$NEW_DB';\""
        fi
      else
        echo ""
        echo "[harden] 已跳过。等服务起不来时手工执行这两条："
        echo "      $COMPOSE_HINT exec -T db psql -U $DB_USER_VAL -d $DB_NAME_VAL \\"
        echo "        -c \"ALTER USER $DB_USER_VAL WITH PASSWORD '$NEW_DB';\""
        echo "      $COMPOSE_HINT up -d --force-recreate backend"
      fi
    else
      echo "[harden]   非交互执行，请手工补一条："
      echo "      $COMPOSE_HINT exec -T db psql -U $DB_USER_VAL -d $DB_NAME_VAL -c \"ALTER USER $DB_USER_VAL WITH PASSWORD '$NEW_DB';\""
      echo "      $COMPOSE_HINT up -d --force-recreate backend"
    fi
    echo ""
  fi
fi
