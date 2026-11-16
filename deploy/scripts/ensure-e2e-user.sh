#!/usr/bin/env bash
# 为 E2E 准备「纯仓管」账号（幂等）。
#
# 背景：frontend/e2e/warehouse-login.spec.js 锁定的是「仓管登录不卡死、
# 按权限落到 /admin/inventory/skus」。这个账号以前靠人工在界面建，
# 换台机器或新建测试栈跑 E2E 就会因登录失败而红，验收记录无法复现。
#
# 用法（默认生产栈；测试栈显式指定 env，项目名会按容器前缀推导）：
#   STACK_ENV_FILE=.env.test ./scripts/ensure-e2e-user.sh
#   STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/ensure-e2e-user.sh
#
# 生产栈拒绝执行，除非显式 STACK_ASSUME_YES=1 且显式给了 E2E_WAREHOUSE_PASS：
# 这个脚本的本意是给测试栈备号，不该在生产上默默建一个弱口令仓管账号。
#
# 账号/口令可用环境变量覆盖，需与跑 E2E 时保持一致：
#   E2E_WAREHOUSE_USER（默认 warehouse）
#   E2E_WAREHOUSE_PASS（测试栈默认 12345678；生产栈必须显式指定）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# shellcheck disable=SC1091
source "$SCRIPT_DIR/_stack.sh"
stack_require_env
stack_banner "准备 E2E 账号"

USERNAME="${E2E_WAREHOUSE_USER:-warehouse}"
# 目标是生产项目（-p 未指定即 compose 默认项目 deploy）时不接受默认弱口令。
IS_PROD_STACK=0
if [[ -z "$STACK_PROJECT" || "$STACK_PROJECT" == "deploy" ]]; then
  IS_PROD_STACK=1
fi

if [[ "$IS_PROD_STACK" == "1" ]]; then
  if [[ "${STACK_ASSUME_YES:-0}" != "1" ]]; then
    echo "[e2e] 拒绝执行：检测到目标是生产栈（项目 ${STACK_PROJECT:-deploy(默认)}）。" >&2
    echo "      E2E 应该跑在测试栈上：STACK_ENV_FILE=.env.test $0" >&2
    echo "      确需在生产建号，请显式设 STACK_ASSUME_YES=1 与 E2E_WAREHOUSE_PASS" >&2
    exit 2
  fi
  if [[ -z "${E2E_WAREHOUSE_PASS:-}" ]]; then
    echo "[e2e] 拒绝执行：生产栈不允许使用默认口令，请显式设 E2E_WAREHOUSE_PASS" >&2
    exit 2
  fi
fi

PASSWORD="${E2E_WAREHOUSE_PASS:-12345678}"

# init_admin.py 的 user add 是「位置参数 username」+ 可选 --password/--role，
# 不是 --username。写错会直接 argparse exit 2，脚本却当成建号失败。
set +e
OUT="$(compose run --rm -T init user add \
  "$USERNAME" --password "$PASSWORD" --role warehouse_clerk 2>&1)"
RC=$?
set -e

if [[ "$RC" == "0" ]]; then
  echo "[e2e] 已创建账号 ${USERNAME}（角色 warehouse_clerk）"
elif grep -q "已存在" <<<"$OUT"; then
  # 已存在不是失败：账号可能已经建过，角色也可能被人工调过。
  # 注意 warehouse-login.spec.js 对「非纯仓管」账号会跳过落地断言，
  # 所以这里不强行改角色——改角色属于权限变更，应由人在用户管理页做。
  echo "[e2e] 账号 ${USERNAME} 已存在，跳过（如需改角色请到用户管理页）"
else
  echo "$OUT" >&2
  echo "[e2e] 创建失败（exit=$RC）" >&2
  exit 1
fi

echo "[e2e] 跑 E2E 时保持同一组变量："
echo "      E2E_WAREHOUSE_USER=${USERNAME} E2E_WAREHOUSE_PASS=${PASSWORD} npm run e2e"
