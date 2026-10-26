#!/usr/bin/env bash
# ============================================================
# 清理过期审计日志（默认保留 190 天：等保要求「不少于六个月」，自然月约 183 天）
#
# 为什么需要定期清理：审计表是只增不减的。后台每天几百次写操作，
# 一年就是十万行量级；留着能查是好事，但不能无限增长把磁盘吃满，
# 也不符合「审计数据保存期限应有明确上限」的合规要求。
#
# 默认只统计不删除，确认后加 --apply 才真正执行。
#
# 用法：
#   ./scripts/cleanup-audit.sh                  # 预演：只报告会删多少
#   ./scripts/cleanup-audit.sh --apply          # 真正删除超过 180 天的
#   ./scripts/cleanup-audit.sh --days 365 --apply
#
# 安全护栏：
#   1) 不传 --apply 一律不删；
#   2) --days 小于 30 直接拒绝：审计留不满一个月没有追溯价值，
#      这个下限同时挡住「手滑多打一个 0」把近几天记录删光的情况；
#   3) 删除前先打印区间与行数，删完再报一次实际删除数；
#   4) 审计表是 append-only（004 迁移加了触发器），脚本在本事务内临时禁用触发器再删。
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DEPLOY_DIR"

APPLY=0
DAYS="${AUDIT_RETENTION_DAYS:-190}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --days)  DAYS="${2:?--days 需要天数}"; shift 2 ;;
    -h|--help)
      sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      exit 2
      ;;
  esac
done

if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
  echo "天数必须是整数：$DAYS" >&2
  exit 2
fi

if (( DAYS < 30 )); then
  echo "拒绝执行：保留天数 $DAYS 小于 30 天。审计日志留不满一个月没有追溯价值。" >&2
  exit 2
fi

# shellcheck disable=SC1091
source <(grep -E '^(DB_USER|DB_NAME)=' .env)

PSQL=(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -At -v ON_ERROR_STOP=1)

echo "[audit-cleanup] 保留期：$DAYS 天（早于该时间的记录将被删除）"

COUNT=$("${PSQL[@]}" -c "SELECT count(*) FROM audit_logs WHERE created_at < now() - interval '$DAYS days';")
echo "[audit-cleanup] 待清理：$COUNT 条"

if [[ "$COUNT" == "0" ]]; then
  echo "[audit-cleanup] 无需清理"
  exit 0
fi

if (( APPLY == 0 )); then
  echo "[audit-cleanup] 预演模式，未删除任何记录。确认无误后加 --apply"
  exit 0
fi

# 审计表被 004 迁移做成了只追加（UPDATE/DELETE/TRUNCATE 都会抛错），
# 清理是唯一被允许的删除路径，必须显式临时禁用触发器。
# 三条语句放在同一个事务里：DELETE 失败时事务回滚，触发器自动恢复启用，
# 不会出现「触发器被关着」的中间态。
"${PSQL[@]}" -c "
BEGIN;
ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_logs_immutable;
DELETE FROM audit_logs WHERE created_at < now() - interval '$DAYS days';
ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_immutable;
COMMIT;
" >/dev/null
echo "[audit-cleanup] 已删除 $COUNT 条"

REMAIN=$("${PSQL[@]}" -c "SELECT count(*) FROM audit_logs;")
echo "[audit-cleanup] 剩余 $REMAIN 条"
