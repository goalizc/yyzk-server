#!/usr/bin/env bash
# 开发环境自检（Docker 路线）
# 用法: bash scripts/dev/check_env.sh
#       bash scripts/dev/check_env.sh --pull    # 额外验证镜像能否拉取
# 退出码: 0 全部通过; 1 有硬性失败; 2 脚本自身问题

set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

PULL=0
[ "${1:-}" = "--pull" ] && PULL=1

fail=0
warn=0
pass() { printf '  [OK]   %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=$((fail+1)); }
note() { printf '  [WARN] %s\n' "$1"; warn=$((warn+1)); }

echo "== 1. Docker 运行时 =="
if command -v docker >/dev/null 2>&1; then
  pass "docker 已安装：$(docker --version 2>/dev/null)"
else
  bad "未找到 docker（sudo -A pacman -S --needed docker docker-compose）"
fi

if docker info >/dev/null 2>&1; then
  pass "daemon 可访问：$(docker info --format '{{.ServerVersion}}' 2>/dev/null)"
else
  bad "docker daemon 不可访问（systemctl status docker；或当前用户不在 docker 组）"
fi

if docker compose version >/dev/null 2>&1; then
  pass "compose v2：$(docker compose version --short 2>/dev/null)"
else
  bad "docker compose 插件不可用（sudo -A pacman -S --needed docker-compose）"
fi

if id -nG 2>/dev/null | grep -qw docker; then
  pass "当前用户在 docker 组"
else
  note "当前用户不在 docker 组（sudo usermod -aG docker \$USER 后重新登录），可用 sudo 临时绕过"
fi

echo
echo "== 2. 端口占用 =="
check_port() {
  local p="$1" what="$2"
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$"; then
      note "端口 ${p} 已被占用（${what}），部署前需释放"
    else
      pass "端口 ${p} 空闲（${what}）"
    fi
  else
    note "无 ss 命令，跳过端口 ${p} 检查"
  fi
}
check_port 80 "nginx 对外"
check_port 5432 "宿主机 PG（若装过原生 PG 需停用）"
check_port 8000 "本地 uvicorn"
check_port 5173 "vite dev"

echo
echo "== 3. 部署配置 =="
if [ -f deploy/.env ]; then
  pass "deploy/.env 存在"
  if grep -qE '请改成|请设置|ple?ase[_ ]change|changeme' deploy/.env; then
    bad "deploy/.env 仍是占位值（DB_PASSWORD / JWT_SECRET / ADMIN_INIT_PASSWORD 需替换）"
  else
    pass "deploy/.env 无明显占位值"
  fi
  if grep -qE '^DB_PASSWORD=.{16,}' deploy/.env 2>/dev/null; then
    pass "DB_PASSWORD 长度 ≥ 16"
  else
    note "DB_PASSWORD 短于 16 位"
  fi
  if grep -qE '^JWT_SECRET=.{32,}' deploy/.env 2>/dev/null; then
    pass "JWT_SECRET 长度 ≥ 32"
  else
    note "JWT_SECRET 短于 32 位"
  fi
else
  bad "缺少 deploy/.env（cp deploy/.env.example deploy/.env 后填三个必填项）"
fi

for d in deploy/data/pg deploy/data/uploads; do
  if [ -d "$d" ]; then pass "目录存在：$d"; else note "目录不存在：$d（mkdir -p $d）"; fi
done

if [ -f deploy/docker-compose.yml ]; then
  if ! command -v docker >/dev/null 2>&1; then
    note "docker 未安装，跳过 compose config 校验"
  elif (cd deploy && docker compose config -q) >/dev/null 2>&1; then
    pass "docker compose config 通过（变量插值与 YAML 合法）"
  else
    bad "docker compose config 失败：$( (cd deploy && docker compose config -q) 2>&1 | head -3 | tr '\n' ' ')"
  fi
else
  bad "缺少 deploy/docker-compose.yml"
fi

echo
echo "== 4. 代码骨架 =="
if [ -d backend ]; then pass "backend/ 存在"; else note "backend/ 尚未生成（S0 任务产出）"; fi
if [ -d frontend ]; then pass "frontend/ 存在"; else note "frontend/ 尚未生成（S0 任务产出）"; fi
if [ -x .venv/bin/python ]; then
  pass "Python venv：$(.venv/bin/python -V 2>&1)"
else
  note "无 .venv（python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt）"
fi

if [ "$PULL" = "1" ]; then
  echo
  echo "== 5. 镜像拉取（--pull） =="
  for img in postgres:15-alpine nginx:1.25-alpine; do
    if docker pull "$img" >/dev/null 2>&1; then
      pass "拉取成功：$img"
    else
      bad "拉取失败：$img（检查网络或 /etc/docker/daemon.json 的 registry-mirrors）"
    fi
  done
fi

echo
if [ "$fail" -gt 0 ]; then
  echo "结果：${fail} 项失败，${warn} 项提醒 —— 先修失败项再 docker compose up"
  exit 1
fi
echo "结果：无失败项，${warn} 项提醒 —— 可以继续"
exit 0
