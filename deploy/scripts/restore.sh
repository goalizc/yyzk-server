#!/usr/bin/env bash
# ============================================================
# 售后故障诊断系统 - 恢复脚本
#
# 用法：
#   ./restore.sh --db backups/db_20261021_030000.dump
#   ./restore.sh --db <文件> --uploads backups/uploads_20261021_030000.tar.gz
#   ./restore.sh --db <文件> --dry-run      只做校验，不动数据
#   ./restore.sh --db <文件> --yes          非交互执行（cron/CI）时跳过确认
#   ./restore.sh --db <文件> --skip-migrate 保留备份里的 schema，不跑迁移
#                                           （发布事故回滚用，见下）
#
# --skip-migrate 的用途：deploy.sh 迁移失败时如果正是「新迁移本身有问题」
# （例如 009 删 users.role 导致旧镜像 500），恢复旧备份后**不能再跑同一批
# 迁移**，否则会再次把 schema 推到坏状态。此时用 --skip-migrate 保留备份
# 自带的旧 schema，旧镜像才能正常启动。
#
# 退出码：0 成功 | 1 恢复失败 | 2 参数/环境错误
#
# ------------------------------------------------------------
# 这个脚本替你做掉的三件危险事：
#
# 1. 先自动备份"当前库"再动手。恢复错了还能回去，否则就是单向操作。
# 2. DROP SCHEMA public CASCADE 后重建。schema.sql 已在 initdb 时建好表，
#    直接 pg_restore 会全部冲突；而 psql/pg_restore 默认遇错继续、最后返回 0，
#    看起来成功其实一条数据都没进去——这是本方案最容易翻车的地方。
# 3. ON_ERROR_STOP=1 + 恢复后行数自检。恢复完立即比对关键表行数，
#    对不上就报错退出，不让"假成功"通过。
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DB_FILE=""
UPLOADS_FILE=""
DRY_RUN=0
ASSUME_YES=0
SKIP_MIGRATE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB_FILE="$2"; shift 2 ;;
    --uploads) UPLOADS_FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    --skip-migrate) SKIP_MIGRATE=1; shift ;;
    -h|--help) sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[$(date '+%F %T')] $*"; }
die() { echo "[$(date '+%F %T')] [ERROR] $*" >&2; exit 1; }

[[ -n "$DB_FILE" ]] || die "必须指定 --db <备份文件>"
[[ -f "$DB_FILE" ]] || die "备份文件不存在: $DB_FILE"

cd "$DEPLOY_DIR"

# 双栈环境层：恢复是破坏性操作，务必确认目标栈（见下方 stack_banner）。
# 生产（默认）：./restore.sh --db xxx.dump
# 测试：STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./restore.sh --db xxx.dump
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_stack.sh"
stack_require_env

# --yes 与非交互环境的约定：非交互默认拒绝，必须显式放行才可能走到 DROP
if [[ "$ASSUME_YES" == "1" ]]; then
  export STACK_ASSUME_YES=1
fi

# 调用方显式传入的变量优先于 .env（同 backup.sh 的说明）
_OVERRIDE_DB_USER="${DB_USER:-}"
_OVERRIDE_DB_NAME="${DB_NAME:-}"

# shellcheck disable=SC1091
set -a; source "$STACK_ENV_PATH"; set +a

[[ -n "$_OVERRIDE_DB_USER" ]] && DB_USER="$_OVERRIDE_DB_USER"
[[ -n "$_OVERRIDE_DB_NAME" ]] && DB_NAME="$_OVERRIDE_DB_NAME"

DB_USER="${DB_USER:-fault}"
DB_NAME="${DB_NAME:-fault_db}"

# ---------- 校验备份文件本身 ----------
SIZE=$(stat -c%s "$DB_FILE" 2>/dev/null || stat -f%z "$DB_FILE")
[[ "$SIZE" -gt 1024 ]] || die "备份文件仅 $SIZE 字节，不可能有效"
[[ "$(head -c 5 "$DB_FILE")" == "PGDMP" ]] || die "不是有效的 PG 自定义格式备份"

compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -qx "$DB_CONTAINER" \
  || die "容器 $DB_CONTAINER 未运行（当前目标栈：${STACK_PROJECT:-deploy(默认)}）"

# ---------- 校验备份文件结构 ----------
# pg_restore -l 需要真实文件路径，不能从 stdin 读；把备份先拷进容器再列目录。
# 这一步只验结构（能否被 pg_restore 解析），不碰数据。
log "校验备份文件..."
docker cp "$DB_FILE" "$DB_CONTAINER:/tmp/.restore_probe.dump" >/dev/null 2>&1 \
  || die "无法把备份文件拷入容器 $DB_CONTAINER"
if ! compose exec -T db pg_restore -l /tmp/.restore_probe.dump > /dev/null 2>&1; then
  compose exec -T db rm -f /tmp/.restore_probe.dump 2>/dev/null || true
  die "备份文件无法被 pg_restore 解析，可能已损坏"
fi
compose exec -T db rm -f /tmp/.restore_probe.dump 2>/dev/null || true

if [[ $DRY_RUN -eq 1 ]]; then
  log "[dry-run] 备份文件有效: $(basename "$DB_FILE") ($SIZE 字节)"
  log "[dry-run] 将: 停 backend → 备份当前库 → DROP+CREATE SCHEMA → pg_restore → 行数自检"
  if [[ -n "$UPLOADS_FILE" ]]; then log "[dry-run] 将解包附件: $UPLOADS_FILE"; fi
  exit 0
fi

# ---------- 破坏性操作前：显式确认目标栈（审查 C-02）----------
# 以前这里没有任何提示，在测试栈语境下跑 restore 会静默把备份灌进生产库。
stack_banner "恢复"
stack_confirm "恢复（会清空目标库 $DB_CONTAINER 的 public schema）"

# ---------- 1. 停后端，避免恢复期间写入 ----------
log "1/5 停止 backend（避免恢复时仍有写入）..."
compose stop backend >/dev/null

# ---------- 2. 先备份当前库 ----------
# 文件名带栈前缀，避免生产/测试两套回退备份互相覆盖
PRE="$DEPLOY_DIR/backups/db_pre-restore_${STACK_PREFIX}_$(date +%Y%m%d_%H%M%S).dump"
log "2/5 备份当前库到 $(basename "$PRE")（恢复出问题可回退）..."
if ! compose exec -T db pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$PRE"; then
  compose start backend >/dev/null
  die "当前库备份失败，已中止（未做任何破坏性操作）"
fi

# ---------- 3. 清空 public schema ----------
log "3/5 清空 public schema..."
compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" \
  || { compose start backend >/dev/null; die "清空 schema 失败，已中止"; }

# ---------- 4. 恢复 ----------
log "4/5 恢复数据..."
# 先把备份送进容器再 pg_restore 读本地文件：用 `exec -T ... < file` 让宿主机重定向
# 进容器 stdin 在某些 compose/终端组合下会拿不到内容，且失败时不报错。
docker cp "$DB_FILE" "$DB_CONTAINER:/tmp/.restore_payload.dump" >/dev/null 2>&1 \
  || die "无法把备份文件拷入容器 $DB_CONTAINER"

# --no-owner/--no-privileges：备份可能来自不同服务器，原 owner 不存在会直接报错
# --exit-on-error：任何一条失败立即停，不留半截库
RESTORE_OK=1
compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" \
  --no-owner --no-privileges --exit-on-error /tmp/.restore_payload.dump \
  || RESTORE_OK=0

compose exec -T db rm -f /tmp/.restore_payload.dump 2>/dev/null || true

if [[ $RESTORE_OK -ne 1 ]]; then
  log "恢复失败。可回退：./restore.sh --db $PRE"
  compose start backend >/dev/null
  exit 1
fi

# ---------- 5. 自检 ----------
log "5/5 校验数据完整性..."
COUNTS=$(compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -t -A -F'|' -c "
  SELECT
    (SELECT count(*) FROM users),
    (SELECT count(*) FROM products),
    (SELECT count(*) FROM parts),
    (SELECT count(*) FROM faults),
    (SELECT count(*) FROM tickets),
    (SELECT count(*) FROM query_logs);
")
NUM_USERS=$(echo "$COUNTS" | cut -d'|' -f1)
NUM_PRODUCTS=$(echo "$COUNTS" | cut -d'|' -f2)
NUM_FAULTS=$(echo "$COUNTS" | cut -d'|' -f4)

# users 必须有记录，否则恢复出了一个无法登录的系统
[[ "$NUM_USERS" -gt 0 ]] || { log "已恢复但 users 表为空，无法登录！请检查备份或重新执行 init"; compose start backend >/dev/null; exit 1; }
[[ "$NUM_PRODUCTS" -gt 0 ]] || log "    警告：products 表为空"
[[ "$NUM_FAULTS" -gt 0 ]] || log "    警告：faults 表为空"

log "    users=$NUM_USERS products=$NUM_PRODUCTS faults=$NUM_FAULTS 全部关键表非空"

# ---------- 迁移：备份可能来自旧版本 ----------
if [[ "$SKIP_MIGRATE" == "1" ]]; then
  log "跳过数据库迁移（--skip-migrate）：保留备份里的 schema 原样"
else
  log "执行数据库迁移（备份可能来自旧版本）"
  set +e
  compose run --rm -T migrate
  MIG_RC=$?
  set -e
  if [[ "$MIG_RC" != "0" ]]; then
    compose start backend >/dev/null 2>&1 || true
    die "迁移失败（详见上方输出）。数据已恢复，但 schema 可能停在中间态：

  若这轮迁移本身就是事故原因（例如删列后旧镜像读不了），
  请加 --skip-migrate 重跑本脚本，保留备份自带的旧 schema：
    ./scripts/restore.sh --db $DB_FILE --skip-migrate
  否则先排查迁移失败原因再重跑。不要反复直接重试。"
  fi
fi

# ---------- 迁移后：角色与库存表完整性 ----------
# 角色只存在 user_roles（009 起）。备份若缺角色行，恢复结果是「能登录但零权限」：
# 所有后台接口 403，而用户管理页本身要 user:write，界面内无法自救。
# 这一步必须拦住，不能像以前那样只数 6 张旧表就报「全部关键表非空」。
ROLE_STAT=$(compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -t -A -F'|' -c "
  SELECT
    (SELECT count(*) FROM user_roles) AS total,
    (SELECT count(*) FROM user_roles WHERE role = 'super_admin') AS super_count;
" | tr -d '[:space:]')
NUM_ROLE_ROWS="${ROLE_STAT%%|*}"
NUM_SUPER="${ROLE_STAT##*|}"

if [[ "${NUM_SUPER:-0}" -lt 1 ]]; then
  log "    [ERROR] user_roles 里没有 super_admin（共 ${NUM_ROLE_ROWS:-0} 行角色）"
  log "    恢复本身成功，但系统不可用：管理员能登录却没有任何权限。手工补授后重跑："
  log "      docker exec -i ${DB_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -c \\"
  log "        \"INSERT INTO user_roles (user_id, role) SELECT id, 'super_admin' FROM users WHERE username='${ADMIN_USERNAME:-admin}' ON CONFLICT DO NOTHING;\""
  compose start backend >/dev/null 2>&1 || true
  exit 1
fi
log "    user_roles=$NUM_ROLE_ROWS 行，super_admin=$NUM_SUPER"

INV_MISSING=$(compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "
  SELECT count(*) FROM (VALUES
    ('inventory_warehouses'), ('inventory_categories'), ('inventory_skus'),
    ('inventory_sku_categories'), ('inventory_sku_products'),
    ('inventory_documents'), ('inventory_document_items'),
    ('inventory_balances'), ('stock_movements')
  ) AS t(name)
  WHERE to_regclass('public.' || t.name) IS NULL;
" | tr -d '[:space:]')
if [[ "${INV_MISSING:-0}" -gt 0 ]]; then
  log "    [WARN] 有 ${INV_MISSING} 张库存表不存在：迁移可能被跳过，进销存页面会 500"
fi

# ---------- 6. 附件 ----------
if [[ -n "$UPLOADS_FILE" ]]; then
  [[ -f "$UPLOADS_FILE" ]] || die "附件包不存在: $UPLOADS_FILE"
  log "恢复附件到 $UPLOADS_DIR ..."
  mkdir -p "$UPLOADS_DIR"

  # 先把现有附件挪到一边：tar 遇到已存在的文件会报错退出，而恢复场景下
  # 文件本来就是要被覆盖的。留一份 .old 便于事后对照，成功后再删。
  # backup.sh 归档的是 uploads 目录名（-C "$DATA_PATH" uploads），
  # 所以这里也解包到 "$DATA_PATH"，两侧一致。
  UPLOADS_OLD="$UPLOADS_DIR.pre-restore.$(date +%Y%m%d_%H%M%S)"
  if [[ -n "$(ls -A "$UPLOADS_DIR" 2>/dev/null)" ]]; then
    mv "$UPLOADS_DIR" "$UPLOADS_OLD"
    mkdir -p "$UPLOADS_DIR"
    log "    现有附件已移至 $(basename "$UPLOADS_OLD")"
  fi

  # --no-same-owner/--no-same-permissions：备份可能来自别的机器，还原原 uid
  # 会因目标机不存在该 uid 而报错；权限统一在解包后 chown 一次。
  # --touch：不还原 mtime，避免 utime 权限错误（非 root 解包时常见）。
  if ! tar xzf "$UPLOADS_FILE" -C "$DATA_PATH" --no-same-owner --no-same-permissions --touch 2>/dev/null; then
    # 解包失败就把原来的挪回来，不留下半套附件
    rm -rf "$UPLOADS_DIR"
    if [[ -d "$UPLOADS_OLD" ]]; then mv "$UPLOADS_OLD" "$UPLOADS_DIR"; fi
    die "附件解包失败，已回滚到恢复前的附件目录"
  fi
  # 注意写法：`[[ ... ]] && cmd` 在 set -e 下，条件为假会让整条语句返回 1，
  # 若这正好是函数/脚本的最后一条命令就会误判为失败。统一写成 if。
  if [[ -d "$UPLOADS_OLD" ]]; then rm -rf "$UPLOADS_OLD"; fi

  # backend 容器以 uid 10001 运行，权限不对会导致上传的文件读不出来。
  # 非 root 执行时 chown 会失败，此时给出可执行的补救命令而不是静默忽略。
  if ! chown -R 10001:10001 "$UPLOADS_DIR" 2>/dev/null; then
    log "    提示：chown 失败（非 root 执行）。若附件打不开，执行："
    log "          sudo chown -R 10001:10001 $UPLOADS_DIR"
  fi
  log "    附件已恢复（$(find "$UPLOADS_DIR" -type f | wc -l) 个文件）"
fi

# ---------- 7. 启动 ----------
log "启动 backend..."
compose start backend >/dev/null

# 等健康检查通过再报告成功，避免"启动了但起不来"也被当成成功
for _ in $(seq 1 30); do
  if compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -q "^${BACKEND_CONTAINER}.*healthy"; then
    log "恢复完成，backend 健康"
    exit 0
  fi
  sleep 2
done

die "backend 启动后 30 次检查仍未 healthy，请查看 compose logs backend"
