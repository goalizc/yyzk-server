#!/usr/bin/env bash
# 带完整进度的镜像构建，卡住时能看出卡在哪一步。
#
# 用法：
#   bash scripts/dev/build.sh              # 构建 backend + frontend
#   bash scripts/dev/build.sh backend      # 只构建后端
#   bash scripts/dev/build.sh backend frontend --no-cache
#
# 与 docker compose up -d --build 的区别：默认的 TTY 进度条会把已完成步骤折叠，
# 卡住时看不出停在哪一步；这里用 --progress=plain 逐步打印。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}/deploy"

if [[ ! -f .env ]]; then
    echo "[build] 缺少 deploy/.env，请先 cp .env.example .env 并填三个必填项" >&2
    exit 1
fi

SERVICES=()
EXTRA=()
for arg in "$@"; do
    case "${arg}" in
        -*) EXTRA+=("${arg}") ;;
        *) SERVICES+=("${arg}") ;;
    esac
done
if [[ ${#SERVICES[@]} -eq 0 ]]; then
    SERVICES=(backend frontend)
fi

echo "[build] 构建服务：${SERVICES[*]} ${EXTRA[*]:-}"
docker compose build --progress=plain "${EXTRA[@]}" "${SERVICES[@]}"
echo "[build] 完成。接着执行：docker compose up -d"
