#!/usr/bin/env bash
# 为 E2E 准备「纯仓管」账号（幂等）。
#
# 背景：frontend/e2e/warehouse-login.spec.js 锁定的是「仓管登录不卡死、
# 按权限落到 /admin/inventory/skus」。这个账号以前靠人工在界面建，
# 换台机器或新建测试栈跑 E2E 就会因登录失败而红，验收记录无法复现。
#
# 用法（默认生产栈；测试栈显式指定 env 与项目名）：
#   ./scripts/ensure-e2e-user.sh
#   STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/ensure-e2e-user.sh
#
# 账号/口令可用环境变量覆盖，需与跑 E2E 时保持一致：
#   E2E_WAREHOUSE_USER（默认 warehouse）/ E2E_WAREHOUSE_PASS（默认 12345678）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# shellcheck disable=SC1091
source "$SCRIPT_DIR/_stack.sh"
stack_require_env
stack_banner "准备 E2E 账号"

USERNAME="${E2E_WAREHOUSE_USER:-warehouse}"
PASSWORD="${E2E_WAREHOUSE_PASS:-12345678}"

set +e
OUT="$(compose run --rm -T init user add \
  --username "$USERNAME" --password "$PASSWORD" --role warehouse_clerk 2>&1)"
RC=$?
set -e

if [[ "$RC" == "0" ]]; then
  echo "[e2e] 已创建账号 ${USERNAME}（角色 warehouse_clerk）"
elif grep -q "已存在" <<<"$OUT"; then
  # 已存在不是失败：账号可能已经建过，或角色是人工调过的
  echo "[e2e] 账号 ${USERNAME} 已存在，跳过（如需改角色请到用户管理页）"
else
  echo "$OUT" >&2
  echo "[e2e] 创建失败（exit=$RC）" >&2
  exit 1
fi

echo "[e2e] 跑 E2E 时保持同一组变量："
echo "      E2E_WAREHOUSE_USER=${USERNAME} E2E_WAREHOUSE_PASS=${PASSWORD} npm run e2e"
