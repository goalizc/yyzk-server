#!/usr/bin/env bash
# ============================================================
# 售后故障诊断系统 - 一键部署
#
# 一条命令完成全部部署动作，重复执行安全（幂等）：
#   ./deploy.sh
#
# 它做了什么（按顺序）：
#   1. 检查前置条件：docker、compose v2、docker 权限、必要命令
#   2. 生成 .env：不存在则从 .env.example 复制，并把占位密码换成随机强值
#   3. 建数据目录 data/pg、data/uploads
#   4. 构建镜像（首次约 3-6 分钟）
#   5. 修正上传目录属主 —— 在容器内以 root 做，**不需要宿主机 sudo**
#   6. 起服务并等待 db / backend 变 healthy
#   7. 初始化管理员账号（幂等，不覆盖已改过的密码）
#   8. 健康验证：/health、登录接口、SPA 首页
#   9. 注册每日清理任务（回收上传残留，见 cleanup-uploads.sh）
#  10. 打印访问地址与管理员初始密码
#
# 用法：
#   ./deploy.sh                 # 完整部署（推荐）
#   ./deploy.sh --check         # 只做体检，不部署（查环境、查配置、查健康）
#   ./deploy.sh --skip-cron     # 跳过定时清理注册
#   ./deploy.sh --rebuild       # 强制重建镜像（改了代码后用）
#
# ------------------------------------------------------------
# 设计前提：**不要用 sudo 运行本脚本**。
#   以 root 跑会让 .env 归 root 所有，之后普通用户改不了；
#   deploy 相关文件散落成 root 属主，后续维护很痛苦。
#   需要 root 的唯一动作（chown 上传目录）已改为容器内执行。
# ============================================================

set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEPLOY_DIR"

# 与 backend/Dockerfile 保持一致，改一处要同步另一处
BACKEND_UID=10001
BACKEND_GID=10001

MODE="deploy"
SKIP_CRON=0
FORCE_REBUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)      MODE="check"; shift ;;
    --skip-cron)  SKIP_CRON=1; shift ;;
    --rebuild)    FORCE_REBUILD=1; shift ;;
    -h|--help)    sed -n '2,42p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$1（用 --help 查看用法）" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------- 输出

STEP=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
info() { printf '  \033[36m·\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[31m[失败] %s\033[0m\n' "$*" >&2; exit 1; }

step() {
  STEP=$((STEP + 1))
  printf '\n\033[1m[%d/10] %s\033[0m\n' "$STEP" "$*"
}

# ---------------------------------------------------------------- 1. 前置检查

step "检查前置条件"

command -v docker >/dev/null 2>&1 \
  || die "未安装 Docker。

  安装（Ubuntu/Debian）：
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker \$USER && newgrp docker

  安装后重新执行本脚本。"

docker compose version >/dev/null 2>&1 \
  || die "未安装 Docker Compose v2（需要 'docker compose' 子命令，不是旧的 docker-compose）。

  Ubuntu/Debian：sudo apt install docker-compose-plugin
  或参考 https://docs.docker.com/compose/install/"

# docker 守护进程是否可达：不可达时先区分"没跑"和"没权限"，否则用户会照着错的提示去排查
if ! docker info >/dev/null 2>&1; then
  if command -v systemctl >/dev/null 2>&1 && ! systemctl is-active --quiet docker 2>/dev/null; then
    die "Docker 守护进程未运行。

  启动：sudo systemctl start docker
  开机自启：sudo systemctl enable docker"
  fi
  die "当前用户无权访问 Docker。

  加入 docker 组后重新登录：
    sudo usermod -aG docker \$USER
    newgrp docker

  （报错细节：\$(docker info 2>&1 | head -1)）"
fi

docker compose version >/dev/null 2>&1 \
  && ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')，Compose $(docker compose version --short 2>/dev/null || echo '?')"

# 磁盘空间：镜像 + 数据目录，低于 5G 会中途失败且难排查
AVAIL_KB=$(df -Pk "$DEPLOY_DIR" | awk 'NR==2 {print $4}')
if [[ -n "$AVAIL_KB" ]] && (( AVAIL_KB < 5 * 1024 * 1024 )); then
  warn "可用磁盘仅 $(( AVAIL_KB / 1024 / 1024 ))G，建议至少 5G（镜像约 2G + 数据增长）"
else
  ok "磁盘可用 $(( AVAIL_KB / 1024 / 1024 ))G"
fi

# 端口占用：80 被别的服务占着是首次部署最常见的失败点
if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | grep -qE ':80\s'; then
    # 如果占用者就是本项目的 nginx，那属于重复部署，是正常的
    if ! docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q "fault-nginx.*:80->"; then
      die "端口 80 已被其他程序占用。

  查看占用者：sudo ss -ltnp | grep ':80'
  停掉它，或改本项目的端口（deploy/docker-compose.yml 里 nginx 的 ports）。"
    fi
  fi
  ok "端口 80 可用"
fi

if [[ "$(id -u)" == "0" ]]; then
  warn "当前以 root 运行。建议用普通用户执行（root 会让 .env 归 root 所有）"
fi

[[ "$MODE" == "check" ]] || ok "前置条件满足"

# ---------------------------------------------------------------- 2. 生成 .env

step "准备配置文件 .env"

if [[ -f .env ]]; then
  ok ".env 已存在，保留现有配置"
  # 复用 harden.sh 的幂等能力：它只替换占位/弱值，已经改过的不动
  bash scripts/harden.sh >/dev/null 2>&1 || die "校验 .env 失败，执行 ./scripts/harden.sh --check 查看详情"
  ok "密钥已校验（占位值会被替换成随机强值）"
else
  [[ -f .env.example ]] || die "缺少 .env.example，仓库可能不完整"
  cp .env.example .env
  chmod 600 .env
  ok "已从 .env.example 创建 .env"
  bash scripts/harden.sh >/dev/null 2>&1 || die "生成密钥失败，执行 ./scripts/harden.sh --check 查看详情"
  ok "已生成随机 JWT_SECRET / DB_PASSWORD / ADMIN_INIT_PASSWORD"
fi

# 读一个键（不 source，避免值里的特殊字符被执行 —— harden.sh 踩过这个坑）
get_env() {
  grep -E "^$1=" .env 2>/dev/null | head -1 | sed -E "s/^$1=//" | sed -E 's/[[:space:]]+$//' | tr -d "\"'" || true
}

ADMIN_USER=$(get_env ADMIN_USERNAME)
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PW=$(get_env ADMIN_INIT_PASSWORD)
ADMIN_PW_DEFAULTED=0
if [[ -z "$ADMIN_PW" ]]; then
  die "ADMIN_INIT_PASSWORD 为空。本项目没有默认口令，请在 .env 里设置一个再执行。"
fi
if [[ "$ADMIN_PW" == "ChangeMe_123456" ]] || [[ ${#ADMIN_PW} -lt 8 ]]; then
  warn "管理员初始密码较弱（$ADMIN_PW），建议改用随机值"
  ADMIN_PW_DEFAULTED=1
fi

# ---------------------------------------------------------------- 3. 数据目录

step "准备数据目录"

mkdir -p data/pg data/uploads
ok "data/pg、data/uploads 已就绪"

if [[ "$MODE" == "check" ]]; then
  echo
  info "--check 模式到此结束（未构建、未起服）"
fi

# ---------------------------------------------------------------- 4. 构建

step "构建镜像"

if [[ "$MODE" == "check" ]]; then
  info "跳过（--check 模式）"
else
  # 构建上下文是仓库根（compose 里 context: ..），镜像 tag 固定，增量构建通常 10 秒内
  if [[ "$FORCE_REBUILD" == "1" ]]; then
    info "强制重建（--rebuild）"
  fi

  # 注意：不能写成 `if ! docker compose build 2>&1 | tail -5`。
  # 管道退出码取自最后一个命令（tail），docker 构建失败会被 tail 的 0 掩盖，
  # 表现为"构建失败却显示成功"。必须先落文件再取退出码。
  #
  # 构建耗时较长且输出被重定向到文件，用户会以为卡死 —— 先给个预期
  info "构建镜像中（首次约 3–6 分钟，请勿中断）"
  set +e
  docker compose build >/tmp/deploy_build.log 2>&1
  BUILD_RC=$?
  set -e

  tail -5 /tmp/deploy_build.log
  if [[ "$BUILD_RC" != "0" ]]; then
    echo
    grep -iE "error|failed|no such|cannot|denied" /tmp/deploy_build.log | tail -10 >&2 || true
    rm -f /tmp/deploy_build.log
    die "镜像构建失败。

  常见原因：
    - 网络无法访问 pypi / npm registry：在 .env 里改用国内镜像
        PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
        NPM_REGISTRY=https://registry.npmmirror.com
      （注意：本机实测清华源返回 403，改用 pypi.org 直连即可）
    - 磁盘满：df -h 检查

  完整日志：docker compose build --progress plain"
  fi
  rm -f /tmp/deploy_build.log
  ok "镜像构建完成"
fi

# ---------------------------------------------------------------- 5. 上传目录属主

step "修正上传目录属主"

# 关键：在容器内以 -u root 执行 chown，**不需要宿主机 sudo**。
# backend 镜像里有 chown 命令，挂载的 /data/uploads 就是宿主机目录，
# 容器内 root 改属主等价于宿主机 root —— 但不要求调用者本身是 root。
if [[ "$MODE" == "check" ]]; then
  OWNER=$(docker run --rm -v "$PWD/data/uploads:/data/uploads:ro" --entrypoint stat alpine:3 2>/dev/null \
    -c '%u:%g' /data/uploads 2>/dev/null || echo "")
  info "跳过修正（--check 模式）"
else
  if docker compose run --rm --no-deps -u root -T backend \
       sh -c "chown -R $BACKEND_UID:$BACKEND_GID /data/uploads && chmod 775 /data/uploads" >/dev/null 2>&1; then
    ok "已修正为 $BACKEND_UID:$BACKEND_GID（容器内执行，无需宿主机 sudo）"
  else
    warn "自动修正失败。若上传仍报 503，在宿主机执行："
    warn "  sudo chown -R $BACKEND_UID:$BACKEND_GID $PWD/data/uploads"
  fi
fi

# ---------------------------------------------------------------- 6. 起服

step "启动服务"

if [[ "$MODE" == "check" ]]; then
  docker compose ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || true
else
  # 1) 只起 db，先完成迁移，避免新代码对旧表
  set +e
  docker compose up -d db >/tmp/deploy_up.log 2>&1
  UP_RC=$?
  set -e
  if [[ "$UP_RC" != "0" ]]; then
    tail -15 /tmp/deploy_up.log >&2
    die "启动数据库失败，详见上面的输出"
  fi

  DB_DEADLINE=$(( SECONDS + 120 ))
  until docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -q "^fault-db healthy"; do
    if (( SECONDS >= DB_DEADLINE )); then
      docker compose logs --tail=50 db
      die "数据库未在 120 秒内就绪"
    fi
    sleep 2
  done

  # 迁移会删除 products.category，不可逆；先备份，失败即中止
  if [[ -x scripts/backup.sh ]]; then
    set +e
    ./scripts/backup.sh >/tmp/deploy_backup.log 2>&1
    BK_RC=$?
    set -e
    tail -2 /tmp/deploy_backup.log
    if [[ "$BK_RC" != "0" ]]; then
      tail -20 /tmp/deploy_backup.log >&2
      die "迁移前备份失败，已中止（本次迁移会删除 products.category）"
    fi
    rm -f /tmp/deploy_backup.log
  fi

  set +e
  docker compose run --rm -T migrate >/tmp/deploy_migrate.log 2>&1
  MIG_RC=$?
  set -e
  tail -5 /tmp/deploy_migrate.log
  if [[ "$MIG_RC" != "0" ]]; then
    tail -30 /tmp/deploy_migrate.log >&2
    die "数据库迁移失败，详见上面的输出"
  fi
  rm -f /tmp/deploy_migrate.log

  # 2) 迁移完成后再起 backend/frontend
  set +e
  docker compose up -d >/tmp/deploy_up.log 2>&1
  UP_RC=$?
  set -e
  tail -3 /tmp/deploy_up.log
  if [[ "$UP_RC" != "0" ]]; then
    echo
    tail -15 /tmp/deploy_up.log >&2
    rm -f /tmp/deploy_up.log
    die "启动服务失败，详见上面的输出。

  常见原因：
    - 端口 80 被占用：sudo ss -ltnp | grep ':80'
    - data/pg 属主不对：sudo chown -R 1000:1000 data/pg
    - 内存不足（需 ≥ 2G）：free -h"
  fi
  rm -f /tmp/deploy_up.log

  # 等 db 与 backend 变 healthy；backend 有 30s start_period，给足 180s。
  # 用单行动态刷新而不是每轮打一行：健康检查每 10s 一次，180s 最多 60 行日志
  # 会把有用信息冲掉，用户也读不出"到底卡在哪一步"。
  DEADLINE=$(( SECONDS + 180 ))
  READY=0
  while (( SECONDS < DEADLINE )); do
    HEALTH=$(docker compose ps --format '{{.Name}} {{.Health}}' 2>/dev/null || true)
    if echo "$HEALTH" | grep -q "^fault-db healthy" && echo "$HEALTH" | grep -q "^fault-backend healthy"; then
      READY=1
      break
    fi
    DB_S="启动中"; BE_S="启动中"
    echo "$HEALTH" | grep -q "^fault-db healthy" && DB_S="就绪" || true
    echo "$HEALTH" | grep -q "^fault-backend healthy" && BE_S="就绪" || true
    printf '\r  \033[36m·\033[0m 等待服务就绪：db %s / backend %s（已等 %ds）   ' \
      "$DB_S" "$BE_S" "$(( 180 - (DEADLINE - SECONDS) ))"
    sleep 3
  done
  printf '\r%*s\r' 70 ''   # 清掉这一行，免得和后面的 ✓ 叠在一起

  if [[ "$READY" != "1" ]]; then
    echo
    docker compose ps
    die "服务未在 180 秒内就绪。

  排查顺序：
    docker compose ps                      # 哪个容器没起来
    docker compose logs --tail=50 backend  # 后端报什么错
    docker compose logs --tail=50 db       # 数据库报什么错

  常见原因：
    - data/pg 属主不对（曾用 root 跑过）→ sudo chown -R 1000:1000 data/pg
    - 内存不足（需 ≥ 2G）：free -h"
  fi
  ok "db / backend 已 healthy"
fi

# ---------------------------------------------------------------- 7. 初始化管理员

step "初始化管理员账号"

if [[ "$MODE" == "check" ]]; then
  info "跳过（--check 模式）"
else
  # 幂等：已存在则不覆盖密码；脚本未设置密码时会退出码 2
  #
  # 注意不能写成 `if cmd; then ... else RC=$?`：进入 else 分支时 $? 是
  # **if 语句本身**的退出码，不是 cmd 的。必须先把 cmd 跑完再取 $?。
  set +e
  docker compose run --rm -T init >/tmp/deploy_init.log 2>&1
  RC=$?
  set -e

  if [[ "$RC" == "0" ]]; then
    ok "管理员 $ADMIN_USER 已就绪"
  elif [[ "$RC" == "2" ]]; then
    die "ADMIN_INIT_PASSWORD 未设置，无法创建管理员。在 .env 里补上后重试。"
  elif grep -qE "已存在|already exists" /tmp/deploy_init.log 2>/dev/null; then
    # 已存在不算错误——这才是重复执行的常态
    ok "管理员 $ADMIN_USER 已存在（未改动密码）"
  else
    tail -20 /tmp/deploy_init.log >&2
    die "初始化管理员失败，详见上面的输出"
  fi
  rm -f /tmp/deploy_init.log
fi

# ---------------------------------------------------------------- 8. 健康验证

step "健康验证"

LOCAL_URL="http://127.0.0.1"
FAILED=0

check_code() {
  local desc="$1" url="$2" expect="$3" extra="${4:-}"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 $extra "$url" 2>/dev/null || echo "000")
  if [[ "$code" == "$expect" ]]; then
    ok "$desc（$code）"
  else
    warn "$desc 返回 $code，期望 $expect"
    FAILED=$((FAILED + 1))
  fi
}

check_code "健康检查 /health" "$LOCAL_URL/health" "200"
check_code "SPA 首页 /" "$LOCAL_URL/" "200"
check_code "API 鉴权校验（未带 token 应 401）" "$LOCAL_URL/api/admin/products" "401"

# 登录接口：能拿到 token 才算真的可用
LOGIN_CODE=$(curl -s -o /tmp/deploy_login.json -w '%{http_code}' --max-time 10 \
  -X POST "$LOCAL_URL/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}" 2>/dev/null || echo "000")

if [[ "$LOGIN_CODE" == "200" ]] && grep -q access_token /tmp/deploy_login.json 2>/dev/null; then
  ok "登录接口可用（管理员凭证正确）"
else
  # 401 有明确含义：账号在、口令不对。多为**之前改过密码，而 .env 没同步**。
  # 这不是部署失败（服务本身是好的），但用户会卡在这里进不去后台，必须给出下一步。
  if [[ "$LOGIN_CODE" == "401" ]]; then
    ok "登录接口可达（返回 401 属正常响应）"
    echo
    warn "但用 .env 里的 ADMIN_INIT_PASSWORD 登录失败——密码很可能已被改过。"
    warn ".env 里的是**初始**密码，只在首次创建账号时用一次；之后改密码不会回写 .env。"
    echo
    echo "  三个选择："
    echo "    a) 用你记得的密码直接登录（最可能就是你之前设的）"
    echo "    b) 忘了密码 → 重置为 .env 里的值："
    echo "         cd $DEPLOY_DIR && docker compose run --rm init user passwd $ADMIN_USER --password \"$ADMIN_PW\""
    echo "    c) 换一个新密码："
    echo "         docker compose run --rm init user passwd $ADMIN_USER"
    echo
  else
    warn "登录接口返回 $LOGIN_CODE"
    FAILED=$((FAILED + 1))
  fi
fi
rm -f /tmp/deploy_login.json

if (( FAILED > 0 )); then
  echo
  warn "健康验证有 $FAILED 项未通过，服务可能未完全就绪"
fi

# ---------------------------------------------------------------- 9. 定时清理

step "注册每日清理任务"

if [[ "$SKIP_CRON" == "1" ]] || [[ "$MODE" == "check" ]]; then
  info "跳过（--skip-cron 或 --check）"
else
  set +e
  CRON_OUT=$(bash scripts/install-cron.sh 2>&1)
  CRON_RC=$?
  set -e

  if [[ "$CRON_RC" == "0" ]]; then
    printf '%s\n' "$CRON_OUT" | sed 's/^/  /'
  else
    # 不中断部署：清理任务缺失不影响系统可用，只是磁盘会慢慢涨。
    # 但必须把真实原因讲清楚，否则用户看到"失败"却无从下手。
    warn "定时清理未注册（不影响系统运行，但上传残留将不再自动回收）"
    printf '%s\n' "$CRON_OUT" | grep -vE '^\s*$' | head -6 | sed 's/^/      /' >&2
    echo
    if printf '%s\n' "$CRON_OUT" | grep -qE '权限不够|Permission denied|Operation not permitted'; then
      info "原因：当前环境不允许写 crontab（常见于容器内、受限沙箱）"
      printf '      在真实主机的普通用户下执行即可注册：\n'
      printf '        cd %s && ./scripts/install-cron.sh\n' "$DEPLOY_DIR"
    else
      printf '      可稍后手动注册：cd %s && ./scripts/install-cron.sh\n' "$DEPLOY_DIR"
    fi
    printf '      在注册成功前，请定期手动执行：./scripts/cleanup-uploads.sh --apply\n'
    echo
  fi
fi

# ---------------------------------------------------------------- 10. 汇总

step "部署完成"

# hostname -I 在部分环境（精简镜像、无网络命名空间）返回空，必须容错。
# 也不要写成 `[[ -n "$LAN_IP" ]] && echo ...`：条件为假时该行整体返回 1，
# 在 set -e 下会终止脚本 —— 实测表现为第 10 步打印标题后静默结束（退出码却是 0，
# 因为末尾还有别的命令兜底），排查成本很高。用 if 显式分支。
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}') || LAN_IP=""
LAN_IP="${LAN_IP:-}"

echo
echo "  访问地址"
echo "    本机   ： $LOCAL_URL/"
if [[ -n "$LAN_IP" ]]; then
  echo "    局域网 ： http://$LAN_IP/"
else
  echo "    局域网 ： 未能自动识别本机 IP，用 ip addr 查看后访问 http://<IP>/"
fi
echo
echo "  管理员账号"
echo "    用户名 ： $ADMIN_USER"
if [[ "$ADMIN_PW_DEFAULTED" == "1" ]]; then
  echo "    密码   ： $ADMIN_PW  （较弱，请立即修改）"
else
  echo "    密码   ： 见 deploy/.env 的 ADMIN_INIT_PASSWORD"
fi
echo
echo "  常用命令"
echo "    查看状态   docker compose ps"
echo "    查看日志   docker compose logs -f backend"
echo "    重启后端   docker compose restart backend"
echo "    停止服务   docker compose down"
echo "    重复部署   ./deploy.sh          （幂等，可随时再跑）"
echo "    体检       ./deploy.sh --check"
echo "    清理残留   ./scripts/cleanup-uploads.sh"
echo

if [[ "$ADMIN_PW_DEFAULTED" == "1" ]]; then
  warn "初始密码较弱，首次登录后请立即在后台「顶栏 → 修改密码」更换"
fi

if (( FAILED > 0 )); then
  echo
  warn "有 $FAILED 项检查未通过，请先排查再投入使用"
  exit 1
fi

echo "  部署成功。首次登录后请立即修改初始密码。"
echo
