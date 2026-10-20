#!/usr/bin/env bash
# 镜像拉取助手：直连失败时依次尝试镜像站，成功后把镜像改回官方名
# 用法: bash scripts/dev/pull_images.sh [镜像名...]
# 默认目标：4 个基础镜像（运行期 2 个 + 构建期 2 个）

set -uo pipefail

IMAGES=("$@")
if [ ${#IMAGES[@]} -eq 0 ]; then
  IMAGES=(postgres:15-alpine nginx:1.25-alpine python:3.12-slim node:22-alpine)
fi

MIRRORS=(
  "docker.m.daocloud.io"
  "docker.1ms.run"
  "dockerproxy.net"
  "docker.xuanyuan.me"
  "hub.rat.dev"
)

ok=0
failed=()

for img in "${IMAGES[@]}"; do
  echo "== $img =="

  if docker image inspect "$img" >/dev/null 2>&1; then
    echo "   [SKIP] 本地已有"
    ok=$((ok+1))
    continue
  fi

  if docker pull "$img" >/dev/null 2>&1; then
    echo "   [OK]   直连 Docker Hub"
    ok=$((ok+1))
    continue
  fi
  echo "   [..]   直连失败，尝试镜像站"

  done_it=0
  for m in "${MIRRORS[@]}"; do
    case "$img" in
      */*) src="$m/$img" ;;          # 带命名空间的镜像原样拼接
      *)   src="$m/library/$img" ;;  # 官方镜像需要 library/ 前缀
    esac
    if docker pull "$src" >/dev/null 2>&1; then
      docker tag "$src" "$img"
      echo "   [OK]   经 $m 拉取并重命名为 $img"
      ok=$((ok+1))
      done_it=1
      break
    fi
    echo "   [--]   $m 失败"
  done

  if [ "$done_it" = "0" ]; then
    failed+=("$img")
  fi
done

echo
if [ ${#failed[@]} -eq 0 ]; then
  echo "全部就绪（$ok 个）。下一步: cd deploy && docker compose up -d"
  exit 0
fi

echo "仍然失败：${failed[*]}"
echo
echo "排查建议（按顺序）："
echo "  1) 确认是否能到 Docker Hub："
echo "       curl -sS -o /dev/null -w '%{http_code}\\n' --max-time 8 https://registry-1.docker.io/v2/"
echo "     返回 401 表示网络通（只是要认证）；超时/连接失败说明被墙或 DNS 有问题。"
echo "  2) 看当前镜像站配置："
echo "       docker info | grep -A5 'Registry Mirrors'"
echo "  3) 换成能用的镜像站写入 /etc/docker/daemon.json 后重启："
echo "       sudo -A tee /etc/docker/daemon.json >/dev/null <<'JSON'"
echo '       { "registry-mirrors": ["https://docker.m.daocloud.io"] }'
echo "       JSON"
echo "       sudo systemctl restart docker"
echo "  4) 如果公司网络需要代理，给 dockerd 配代理（systemd drop-in），不要只设 shell 变量。"
echo "  5) 兜底：在能拉镜像的机器上 docker save，拷过来 docker load。"
exit 1
