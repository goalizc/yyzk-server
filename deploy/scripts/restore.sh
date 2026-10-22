#!/usr/bin/env bash
# ============================================================
# 售后故障诊断系统 - 恢复脚本
#
# 用法：
#   ./restore.sh --db backups/db_20261021_030000.dump
#   ./restore.sh --db <文件> --uploads backups/uploads_20261021_030000.tar.gz
#   ./restore.sh --db <文件> --dry-run      只做校验，不动数据
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB_FILE="$2"; shift 2 ;;
    --uploads) UPLOADS_FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[$(date '+%F %T')] $*"; }
die() { echo "[$(date '+%F %T')] [ERROR] $*" >&2; exit 1; }

[[ -n "$DB_FILE" ]] || die "必须指定 --db <备份文件>"
[[ -f "$DB_FILE" ]] || die "备份文件不存在: $DB_FILE"

cd "$DEPLOY_DIR"
[[ -f .env ]] || die "找不到 $DEPLOY_DIR/.env"

# 调用方显式传入的变量优先于 .env（同 backup.sh 的说明）
_OVERRIDE_DB_USER="${DB_USER:-}"
_OVERRIDE_DB_NAME="${DB_NAME:-}"

# shellcheck disable=SC1091
set -a; source .env; set +a

[[ -n "$_OVERRIDE_DB_USER" ]] && DB_USER="$_OVERRIDE_DB_USER"
[[ -n "$_OVERRIDE_DB_NAME" ]] && DB_NAME="$_OVERRIDE_DB_NAME"

DB_USER="${DB_USER:-fault}"
DB_NAME="${DB_NAME:-fault_db}"

# ---------- 校验备份文件本身 ----------
SIZE=$(stat -c%s "$DB_FILE" 2>/dev/null || stat -f%z "$DB_FILE")
[[ "$SIZE" -gt 1024 ]] || die "备份文件仅 $SIZE 字节，不可能有效"
[[ "$(head -c 5 "$DB_FILE")" == "PGDMP" ]] || die "不是有效的 PG 自定义格式备份"

docker compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q "fault-db" \
  || die "容器 fault-db 未运行"

# ---------- 校验备份文件结构 ----------
# pg_restore -l 需要真实文件路径，不能从 stdin 读；把备份先拷进容器再列目录。
# 这一步只验结构（能否被 pg_restore 解析），不碰数据。
log "校验备份文件..."
docker cp "$DB_FILE" fault-db:/tmp/.restore_probe.dump >/dev/null 2>&1 \
  || die "无法把备份文件拷入容器"
if ! docker compose exec -T db pg_restore -l /tmp/.restore_probe.dump > /dev/null 2>&1; then
  docker compose exec -T db rm -f /tmp/.restore_probe.dump 2>/dev/null || true
  die "备份文件无法被 pg_restore 解析，可能已损坏"
fi
docker compose exec -T db rm -f /tmp/.restore_probe.dump 2>/dev/null || true

if [[ $DRY_RUN -eq 1 ]]; then
  log "[dry-run] 备份文件有效: $(basename "$DB_FILE") ($SIZE 字节)"
  log "[dry-run] 将: 停 backend → 备份当前库 → DROP+CREATE SCHEMA → pg_restore → 行数自检"
  if [[ -n "$UPLOADS_FILE" ]]; then log "[dry-run] 将解包附件: $UPLOADS_FILE"; fi
  exit 0
fi

# ---------- 1. 停后端，避免恢复期间写入 ----------
log "1/5 停止 backend（避免恢复时仍有写入）..."
docker compose stop backend >/dev/null

# ---------- 2. 先备份当前库 ----------
PRE="$DEPLOY_DIR/backups/db_pre-restore_$(date +%Y%m%d_%H%M%S).dump"
log "2/5 备份当前库到 $(basename "$PRE")（恢复出问题可回退）..."
if ! docker compose exec -T db pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$PRE"; then
  docker compose start backend >/dev/null
  die "当前库备份失败，已中止（未做任何破坏性操作）"
fi

# ---------- 3. 清空 public schema ----------
log "3/5 清空 public schema..."
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" \
  || { docker compose start backend >/dev/null; die "清空 schema 失败，已中止"; }

# ---------- 4. 恢复 ----------
log "4/5 恢复数据..."
# 先把备份送进容器再 pg_restore 读本地文件：用 `exec -T ... < file` 让宿主机重定向
# 进容器 stdin 在某些 compose/终端组合下会拿不到内容，且失败时不报错。
docker cp "$DB_FILE" fault-db:/tmp/.restore_payload.dump >/dev/null 2>&1 \
  || die "无法把备份文件拷入容器"

# --no-owner/--no-privileges：备份可能来自不同服务器，原 owner 不存在会直接报错
# --exit-on-error：任何一条失败立即停，不留半截库
RESTORE_OK=1
docker compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" \
  --no-owner --no-privileges --exit-on-error /tmp/.restore_payload.dump \
  || RESTORE_OK=0

docker compose exec -T db rm -f /tmp/.restore_payload.dump 2>/dev/null || true

if [[ $RESTORE_OK -ne 1 ]]; then
  log "恢复失败。可回退：./restore.sh --db $PRE"
  docker compose start backend >/dev/null
  exit 1
fi

# ---------- 5. 自检 ----------
log "5/5 校验数据完整性..."
COUNTS=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -t -A -F'|' -c "
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
[[ "$NUM_USERS" -gt 0 ]] || { log "已恢复但 users 表为空，无法登录！请检查备份或重新执行 init"; docker compose start backend >/dev/null; exit 1; }
[[ "$NUM_PRODUCTS" -gt 0 ]] || log "    警告：products 表为空"
[[ "$NUM_FAULTS" -gt 0 ]] || log "    警告：faults 表为空"

log "    users=$NUM_USERS products=$NUM_PRODUCTS faults=$NUM_FAULTS 全部关键表非空"

# ---------- 迁移：备份可能来自旧版本 ----------
log "执行数据库迁移（备份可能来自旧版本）"
docker compose run --rm -T migrate

# ---------- 6. 附件 ----------
if [[ -n "$UPLOADS_FILE" ]]; then
  [[ -f "$UPLOADS_FILE" ]] || die "附件包不存在: $UPLOADS_FILE"
  log "恢复附件..."
  mkdir -p data/uploads

  # 先把现有附件挪到一边：tar 遇到已存在的文件会报错退出，而恢复场景下
  # 文件本来就是要被覆盖的。留一份 .old 便于事后对照，成功后再删。
  UPLOADS_OLD="data/uploads.pre-restore.$(date +%Y%m%d_%H%M%S)"
  if [[ -n "$(ls -A data/uploads 2>/dev/null)" ]]; then
    mv data/uploads "$UPLOADS_OLD"
    mkdir -p data/uploads
    log "    现有附件已移至 $(basename "$UPLOADS_OLD")"
  fi

  # --no-same-owner/--no-same-permissions：备份可能来自别的机器，还原原 uid
  # 会因目标机不存在该 uid 而报错；权限统一在解包后 chown 一次。
  # --touch：不还原 mtime，避免 utime 权限错误（非 root 解包时常见）。
  if ! tar xzf "$UPLOADS_FILE" -C . --no-same-owner --no-same-permissions --touch 2>/dev/null; then
    # 解包失败就把原来的挪回来，不留下半套附件
    rm -rf data/uploads
    if [[ -d "$UPLOADS_OLD" ]]; then mv "$UPLOADS_OLD" data/uploads; fi
    die "附件解包失败，已回滚到恢复前的附件目录"
  fi
  # 注意写法：`[[ ... ]] && cmd` 在 set -e 下，条件为假会让整条语句返回 1，
  # 若这正好是函数/脚本的最后一条命令就会误判为失败。统一写成 if。
  if [[ -d "$UPLOADS_OLD" ]]; then rm -rf "$UPLOADS_OLD"; fi

  # backend 容器以 uid 10001 运行，权限不对会导致上传的文件读不出来。
  # 非 root 执行时 chown 会失败，此时给出可执行的补救命令而不是静默忽略。
  if ! chown -R 10001:10001 data/uploads 2>/dev/null; then
    log "    提示：chown 失败（非 root 执行）。若附件打不开，执行："
    log "          sudo chown -R 10001:10001 $DEPLOY_DIR/data/uploads"
  fi
  log "    附件已恢复（$(find data/uploads -type f | wc -l) 个文件）"
fi

# ---------- 7. 启动 ----------
log "启动 backend..."
docker compose start backend >/dev/null

# 等健康检查通过再报告成功，避免"启动了但起不来"也被当成成功
for _ in $(seq 1 30); do
  if docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -q "fault-backend.*healthy"; then
    log "恢复完成，backend 健康"
    exit 0
  fi
  sleep 2
done

die "backend 启动后 30 次检查仍未 healthy，请查看 docker compose logs backend"
