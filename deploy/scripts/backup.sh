#!/usr/bin/env bash
# ============================================================
# 售后故障诊断系统 - 备份脚本
#
# 备份范围（与 docs/04-运维与运营/备份恢复方案.md §1 一致）：
#   1. PostgreSQL 全库（pg_dump，自定义格式压缩）
#   2. 上传附件目录（tar.gz）
#
# 用法：
#   ./backup.sh                    备份到默认目录（deploy/backups）
#   ./backup.sh --dir /mnt/nas     指定备份目录（建议挂载到另一块盘）
#   ./backup.sh --retention 7      保留 7 天（默认 30）
#   ./backup.sh --dry-run          只打印将要执行的动作，不落盘
#
# 退出码：
#   0 成功  |  1 备份失败  |  2 参数/环境错误
#
# ------------------------------------------------------------
# 为什么校验这么重：
#   `set -e` 对管道无效。`pg_dump | gzip` 的退出码取的是 gzip——数据库连不上时
#   pg_dump 立刻死掉，gzip 却会"成功"压缩 0 字节并返回 0，最终得到一个几十字节的
#   空文件，看起来备份成功。所以必须：pipefail + gzip -t + 体积下限 三重校验，
#   并且先写 .tmp 再 mv，避免半截文件被当成有效备份。
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKUP_DIR="$DEPLOY_DIR/backups"
RETENTION_DAYS=30
DRY_RUN=0
# 数据库为空库时 dump 也有几 KB（表结构），低于此值必然是失败产物
MIN_DB_BYTES=1024

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) BACKUP_DIR="$2"; shift 2 ;;
    --retention) RETENTION_DAYS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[$(date '+%F %T')] $*"; }
die() { echo "[$(date '+%F %T')] [ERROR] $*" >&2; exit 1; }

cd "$DEPLOY_DIR"

# 双栈环境层：默认仍是生产栈；测试栈用
#   STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/backup.sh --dry-run
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_stack.sh"
stack_require_env

# ---------- 环境检查 ----------

# 调用方显式传入的变量优先于 .env（否则无法用 DB_NAME=xxx 覆盖来排查问题）。
# 先把已有的记下来，source 完再盖回去。
_OVERRIDE_DB_USER="${DB_USER:-}"
_OVERRIDE_DB_NAME="${DB_NAME:-}"

# shellcheck disable=SC1091
set -a; source "$STACK_ENV_PATH"; set +a

[[ -n "$_OVERRIDE_DB_USER" ]] && DB_USER="$_OVERRIDE_DB_USER"
[[ -n "$_OVERRIDE_DB_NAME" ]] && DB_NAME="$_OVERRIDE_DB_NAME"

DB_USER="${DB_USER:-fault}"
DB_NAME="${DB_NAME:-fault_db}"
STAMP="$(date +%Y%m%d_%H%M%S)"

stack_banner "备份"

# 容器必须在跑，否则 pg_dump 无从执行
compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -qx "$DB_CONTAINER" \
  || die "容器 $DB_CONTAINER 未运行，先执行该栈的 docker compose up -d"

log "开始备份（目标目录 $BACKUP_DIR，保留 $RETENTION_DAYS 天）"

if [[ $DRY_RUN -eq 1 ]]; then
  log "[dry-run] 将执行: pg_dump -U $DB_USER $DB_NAME → $BACKUP_DIR/db_${STACK_PREFIX}_$STAMP.dump"
  log "[dry-run] 将执行: tar czf → $BACKUP_DIR/uploads_${STACK_PREFIX}_$STAMP.tar.gz（源 $UPLOADS_DIR）"
  log "[dry-run] 将清理 $RETENTION_DAYS 天前的备份"
  exit 0
fi

mkdir -p "$BACKUP_DIR"

# ---------- 1. 数据库 ----------
# 用 -Fc（自定义格式）而不是纯 SQL：体积更小、支持 pg_restore 并行与选择性恢复
# 文件名带栈前缀：生产 fault_* / 测试 fault-test_*，避免两套备份互相覆盖
DB_TMP="$BACKUP_DIR/.db_${STACK_PREFIX}_$STAMP.dump.tmp"
DB_OUT="$BACKUP_DIR/db_${STACK_PREFIX}_$STAMP.dump"

log "1/3 备份数据库..."
if ! compose exec -T db pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$DB_TMP" 2>"$BACKUP_DIR/.db_err"; then
  cat "$BACKUP_DIR/.db_err" >&2
  rm -f "$DB_TMP" "$BACKUP_DIR/.db_err"
  die "pg_dump 失败"
fi
rm -f "$BACKUP_DIR/.db_err"

# 校验：体积下限 + 文件头魔数（PGDMP），两者都过才算数
SIZE=$(stat -c%s "$DB_TMP" 2>/dev/null || stat -f%z "$DB_TMP")
[[ "$SIZE" -gt "$MIN_DB_BYTES" ]] || { rm -f "$DB_TMP"; die "dump 仅 $SIZE 字节，疑似失败"; }
# 自定义格式的魔数是 "PGDMP"
[[ "$(head -c 5 "$DB_TMP")" == "PGDMP" ]] || { rm -f "$DB_TMP"; die "dump 不是有效的 PG 自定义格式"; }

mv "$DB_TMP" "$DB_OUT"
log "    完成: $(basename "$DB_OUT") ($(numfmt --to=iec "$SIZE" 2>/dev/null || echo "$SIZE B"))"

# ---------- 2. 附件 ----------
UP_TMP="$BACKUP_DIR/.uploads_${STACK_PREFIX}_$STAMP.tar.gz.tmp"
UP_OUT="$BACKUP_DIR/uploads_${STACK_PREFIX}_$STAMP.tar.gz"

log "2/3 备份附件..."
if [[ -d "$UPLOADS_DIR" ]]; then
  # -C 数据目录、归档 uploads 目录名：restore.sh 也用 -C "$DATA_PATH" 解包，
  # 两侧一致，且绝对路径/相对路径的 DATA_DIR 都能正确处理。
  if ! tar czf "$UP_TMP" -C "$DATA_PATH" uploads 2>/dev/null; then
    rm -f "$UP_TMP"; die "附件打包失败"
  fi
  # 校验可读性：tar tzf 会真的解压索引，能发现截断的包
  tar tzf "$UP_TMP" > /dev/null || { rm -f "$UP_TMP"; die "附件包校验失败"; }
  mv "$UP_TMP" "$UP_OUT"
  log "    完成: $(basename "$UP_OUT")"
else
  log "    跳过：$UPLOADS_DIR 目录不存在"
fi

# ---------- 3. 清理过期 ----------
# 必须按栈前缀过滤：两栈共用 deploy/backups，`db_*.dump` 会同时匹配
# db_fault_* 与 db_fault-test_*，任一栈跑一次保留期清理就会删掉另一栈的备份，
# 回退链直接断掉。`db_fault_` 含下划线，天然不会误匹配 `db_fault-test_`。
log "3/3 清理 $RETENTION_DAYS 天前的备份（仅 ${STACK_PREFIX} 栈）..."
BEFORE=$(find "$BACKUP_DIR" -maxdepth 1 \( -name "db_${STACK_PREFIX}_*.dump" -o -name "uploads_${STACK_PREFIX}_*.tar.gz" \) | wc -l)
find "$BACKUP_DIR" -maxdepth 1 -name "db_${STACK_PREFIX}_*.dump" -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "uploads_${STACK_PREFIX}_*.tar.gz" -mtime +"$RETENTION_DAYS" -delete
AFTER=$(find "$BACKUP_DIR" -maxdepth 1 \( -name "db_${STACK_PREFIX}_*.dump" -o -name "uploads_${STACK_PREFIX}_*.tar.gz" \) | wc -l)
log "    清理 $((BEFORE - AFTER)) 个过期文件，现存 $AFTER 个"

log "备份完成: $STAMP"
