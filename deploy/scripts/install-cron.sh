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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$DEPLOY_DIR"

# 双栈环境层（审查 M-04）：cron 条目必须绑定目标栈，否则只会清生产栈。
#   STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/install-cron.sh
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_stack.sh"
stack_require_env
stack_banner "定时清理注册"

# 标记按栈区分：生产沿用旧标记（历史条目仍能被识别替换），
# 测试栈用独立标记，两栈的 cron 条目互不覆盖。
MARKER_BASE="# fault-system:cleanup-uploads"
IS_PROD=1
if [[ "$STACK_PREFIX" != "fault" || "$STACK_ENV_FILE" == *test* ]]; then
  IS_PROD=0
fi
if [[ "$IS_PROD" == "1" ]]; then
  MARKER="$MARKER_BASE"
  LOG_FILE="$DEPLOY_DIR/logs/cleanup.log"
else
  MARKER="${MARKER_BASE}:${STACK_PREFIX}"
  LOG_FILE="$DEPLOY_DIR/logs/cleanup-${STACK_PREFIX}.log"
fi

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
# 只删除「当前栈」的旧条目。原先的 grep -vF "cleanup-uploads.sh" 会把另一栈
# 的条目一起删掉（装测试栈 cron 就顺手抹掉生产 cron），改为按标记精确匹配。
# 生产栈额外清掉旧格式（没有 :fault 后缀）的历史条目。
WITHOUT=$(printf '%s\n' "$CURRENT" | awk -v m="$MARKER" -v base="$MARKER_BASE" -v prod="$IS_PROD" '
  function endsWith(s, t) {
    return length(s) >= length(t) && substr(s, length(s) - length(t) + 1) == t
  }
  { line = $0; sub(/[[:space:]]+$/, "", line) }
  line == "" { next }
  endsWith(line, m) { next }
  (prod == "1" && endsWith(line, base)) { next }
  { print }
')

case "$MODE" in
  show)
    # 行尾锚定，避免生产标记（无后缀）把测试栈条目也匹配上
    if printf '%s\n' "$CURRENT" | grep -qE "${MARKER}[[:space:]]*$"; then
      echo "已注册（目标栈 env=$STACK_ENV_FILE 项目=${STACK_PROJECT:-deploy(默认)}）："
      printf '%s\n' "$CURRENT" | grep -E "${MARKER}[[:space:]]*$"
    else
      echo "未注册定时清理（目标栈 env=$STACK_ENV_FILE）。执行 ./scripts/install-cron.sh 注册。"
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
    # 把目标栈显式钉进 cron 条目：cron 没有交互 shell 的环境变量，
    # 漏了这一截，测试栈的 cron 会静默回落到生产栈（审查 M-04）。
    STACK_ENV="STACK_ENV_FILE=$STACK_ENV_FILE"
    if [[ -n "$STACK_PROJECT" ]]; then
      STACK_ENV="$STACK_ENV STACK_PROJECT=$STACK_PROJECT"
    fi
    # 日志轮转：单文件超过 5MB 就清空。cron 任务里不方便再调 logrotate，
    # 用 shell 判断足够——清理日志本身价值有限，不需要长期留存
    ENTRY="$RUN_TIME * * * cd $DEPLOY_DIR && ( [ -f $LOG_FILE ] && [ \$(stat -c%s $LOG_FILE) -gt 5242880 ] && : > $LOG_FILE; $STACK_ENV ./scripts/cleanup-uploads.sh --apply >> $LOG_FILE 2>&1; $STACK_ENV ./scripts/cleanup-audit.sh --apply >> $LOG_FILE 2>&1 ) $MARKER"

    {
      printf '%s\n' "$WITHOUT"
      printf '%s\n' "$ENTRY"
    } | crontab -

    echo "已注册每日清理任务（目标栈 env=$STACK_ENV_FILE 项目=${STACK_PROJECT:-deploy(默认)}）："
    echo "  时间：$(echo "$RUN_TIME" | awk '{printf "%02d:%02d", $2, $1}')（每天）"
    echo "  日志：$LOG_FILE"
    echo
    echo "首次运行前建议先手动预演一次，确认待删清单无误："
    echo "  $STACK_ENV ./scripts/cleanup-uploads.sh"
    ;;
esac
