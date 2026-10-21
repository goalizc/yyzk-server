#!/usr/bin/env bash
# ============================================================
# 清理无人引用的上传残留文件（幂等，可重复执行）
#
# 背景：上传与删除是两个独立动作——
#       文件在 POST /api/admin/upload 时立即落盘，
#       引用要等 PUT /api/admin/faults/{id} 保存时才写进 JSONB。
#       中间任何一步没走完，文件就成了孤儿：
#         - 上传后点了"移除"（前端已会通知后端删除，但网络失败时仍会残留）
#         - 上传后直接关闭页面
#         - 编辑时换了另一张图，旧图 URL 被覆盖
#         - 保存时校验失败，整个表单没提交
#
# 默认只报告不删除，确认无误后加 --apply 才真正回收。
#
# 用法：
#   ./scripts/cleanup-uploads.sh                 # 预演（dry-run），只报告
#   ./scripts/cleanup-uploads.sh --apply         # 真正删除
#   ./scripts/cleanup-uploads.sh --min-age 1440  # 只清 24 小时前的（默认 60 分钟）
#   ./scripts/cleanup-uploads.sh --apply --max-ratio 0.8
#
# 安全机制（三层，缺一不可）：
#   1) 默认 dry-run，不显式 --apply 绝不删文件
#   2) 年龄下限：默认只删 60 分钟前的文件，避免误删"刚上传未保存"的图
#   3) 比例闸门：待删超过 50% 判定为引用扫描异常，直接拒绝（目录 ≥10 个文件时生效）
#
# 建议挂到 cron 每日凌晨执行一次：
#   30 3 * * * cd /path/to/deploy && ./scripts/cleanup-uploads.sh --apply >> /var/log/fault-cleanup.log 2>&1
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

APPLY=0
MIN_AGE=60
MAX_RATIO="0.5"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)     APPLY=1; shift ;;
    --min-age)   MIN_AGE="${2:?--min-age 需要分钟数}"; shift 2 ;;
    --max-ratio) MAX_RATIO="${2:?--max-ratio 需要 0-1 之间的小数}"; shift 2 ;;
    -h|--help)
      sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "未知参数：$1（用 --help 查看用法）" >&2; exit 2 ;;
  esac
done

cd "$DEPLOY_DIR"

# 容器必须已经在跑——清理逻辑读的是库里的引用关系
if ! docker compose ps --status running --services 2>/dev/null | grep -qx backend; then
  echo "backend 容器未运行。先执行：docker compose up -d" >&2
  exit 1
fi

if [[ "$APPLY" == "1" ]]; then
  echo "模式：执行删除（--apply）"
else
  echo "模式：预演（只报告，不删任何文件）。确认无误后加 --apply 执行。"
fi
echo

# 逻辑都在 app/services/upload_cleanup.py 里，这里只负责调用与退出码。
# 参数用 -c 的内联脚本读取：heredoc 会占用 stdin，argv 拿不到值。
# 内联脚本尽量短，避免多层引号嵌套被 shell 吃掉字符。
docker compose exec -T \
  -e CLEANUP_APPLY="$APPLY" \
  -e CLEANUP_MIN_AGE="$MIN_AGE" \
  -e CLEANUP_MAX_RATIO="$MAX_RATIO" \
  backend python -c '
import os, sys
from app.database import new_session
from app.services.upload_cleanup import sweep

apply = os.environ["CLEANUP_APPLY"] == "1"
min_age = int(os.environ["CLEANUP_MIN_AGE"])
max_ratio = float(os.environ["CLEANUP_MAX_RATIO"])

db = new_session()
try:
    r = sweep(db, apply=apply, min_age_minutes=min_age, max_ratio=max_ratio)
finally:
    db.close()

print("目录内文件总数    ：%d" % r.total_files)
print("库中被引用文件名数：%d" % r.referenced)
print("因太新而跳过      ：%d（%d 分钟内的文件不处理）" % (r.skipped_too_new, min_age))
print("待清理            ：%d" % len(r.candidates))

if r.refused:
    print()
    print("[拒绝执行] " + r.reason, file=sys.stderr)
    sys.exit(3)

if r.candidates:
    print()
    print("待清理文件列表：")
    for name in r.candidates:
        print("  - " + name)

if apply:
    print()
    print("已删除 %d 个文件，释放 %.2f MB" % (len(r.deleted), r.freed_bytes / 1024 / 1024))
    if len(r.deleted) < len(r.candidates):
        print("注意：有 %d 个文件删除失败，详见 backend 日志（多为目录权限问题）"
              % (len(r.candidates) - len(r.deleted)), file=sys.stderr)
elif r.candidates:
    print()
    print("以上为预演结果，未删除任何文件。确认无误后执行：")
    print("  ./scripts/cleanup-uploads.sh --apply --min-age %d" % min_age)
else:
    print()
    print("没有需要清理的文件。")
'
