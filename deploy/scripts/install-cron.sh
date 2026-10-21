#!/usr/bin/env bash
# ============================================================
# 注册上传残留的每日清理任务（幂等）
#
# 背景：上传与删除是两个独立动作。用户上传后关页面、编辑时换图、
#       保存校验失败等情况，后端无从得知文件已废弃，只能靠定期扫描回收。
#       不清理的话 data/uploads 会一直涨，最终塞满磁盘。
#
# 用法：
#   ./scripts/install-cron.sh              # 注册每日 03:30 清理
#   ./scripts/install-cron.sh --time 04:15 # 自定义时间
#   ./scripts/install-cron.sh --show       # 查看当前注册状态
#   ./scripts/install-cron.sh --remove     # 移除
#
# 说明：
#   - 写入的是**当前用户**的 crontab，不需要 sudo
#   - 用标记行标识本项目条目，重复执行只会替换、不会累积
#   - 清理脚本默认预演，这里固定加 --apply 并保留 60 分钟年龄保护
#   - 日志落到 logs/cleanup.log（自动轮转，超过 5MB 清空）
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DEPLOY_DIR"

MARKER="# fault-system:cleanup-uploads"
LOG_DIR="$DEPLOY_DIR/logs"
RUN_TIME="30 3"
MODE="install"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --time)
      RAW="${2:?--time 需要 HH:MM 格式}"
      H="${RAW%%:*}"; M="${RAW##*:}"
      # 去前导 0（cron 不接受 08 这类写法在部分发行版上会报错）
      H=$((10#$H)); M=$((10#$M))
      (( H >= 0 && H <= 23 && M >= 0 && M <= 59 )) || { echo "时间非法：$RAW" >&2; exit 2; }
      RUN_TIME="$M $H"
      shift 2
      ;;
    --show)   MODE="show"; shift ;;
    --remove) MODE="remove"; shift ;;
    -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$1（用 --help 查看用法）" >&2; exit 2 ;;
  esac
done

if ! command -v crontab >/dev/null 2>&1; then
  echo "系统没有 crontab 命令。安装：" >&2
  echo "  sudo apt install cron      # Debian/Ubuntu" >&2
  echo "  sudo systemctl enable --now cron" >&2
  echo >&2
  echo "或不使用 cron，改用 systemd timer 手动配置；" >&2
  echo "也可跳过定时清理，靠人工定期执行 ./scripts/cleanup-uploads.sh --apply" >&2
  exit 1
fi

CURRENT=$(crontab -l 2>/dev/null || true)
# 过滤掉本项目的旧条目（标记行 + 紧随其后的那条命令）
WITHOUT=$(printf '%s\n' "$CURRENT" | grep -vF "$MARKER" | grep -vF "cleanup-uploads.sh" || true)

case "$MODE" in
  show)
    if printf '%s\n' "$CURRENT" | grep -qF "$MARKER"; then
      echo "已注册："
      printf '%s\n' "$CURRENT" | grep -E "$MARKER|cleanup-uploads.sh"
    else
      echo "未注册定时清理。执行 ./scripts/install-cron.sh 注册。"
    fi
    exit 0
    ;;

  remove)
    printf '%s\n' "$WITHOUT" | crontab -
    echo "已移除定时清理任务"
    exit 0
    ;;

  install)
    mkdir -p "$LOG_DIR"
    # 日志轮转：单文件超过 5MB 就清空。cron 任务里不方便再调 logrotate，
    # 用 shell 判断足够——清理日志本身价值有限，不需要长期留存
    ENTRY="$RUN_TIME * * * cd $DEPLOY_DIR && ( [ -f $LOG_DIR/cleanup.log ] && [ \$(stat -c%s $LOG_DIR/cleanup.log) -gt 5242880 ] && : > $LOG_DIR/cleanup.log; ./scripts/cleanup-uploads.sh --apply >> $LOG_DIR/cleanup.log 2>&1 ) $MARKER"

    {
      printf '%s\n' "$WITHOUT"
      printf '%s\n' "$ENTRY"
    } | crontab -

    echo "已注册每日清理任务："
    echo "  时间：$(echo "$RUN_TIME" | awk '{printf "%02d:%02d", $2, $1}')（每天）"
    echo "  日志：$LOG_DIR/cleanup.log"
    echo
    echo "首次运行前建议先手动预演一次，确认待删清单无误："
    echo "  ./scripts/cleanup-uploads.sh"
    ;;
esac
