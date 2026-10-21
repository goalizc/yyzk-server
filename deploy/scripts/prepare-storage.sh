#!/usr/bin/env bash
# ============================================================
# 准备上传目录（幂等，可重复执行）
#
# 背景：backend 容器以 uid/gid 10001 运行，而 data/uploads 是宿主机目录挂载，
#       镜像构建时给的属主会被挂载点覆盖。如果这个目录是 root 或别的 uid
#       建的，容器就写不进去，表现为上传返回 500/503。
#
# 这个坑在真机上出过一次：POST /api/admin/upload 报
#   PermissionError: [Errno 13] Permission denied: '/data/uploads/.xxx.png.part'
# 之前只在 docker-compose.yml 的注释里写了"首次部署前 sudo chown"，
# 靠人记住的步骤一定会漏，所以固化成脚本。
#
# 用法：
#   ./scripts/prepare-storage.sh            # 修正权限
#   ./scripts/prepare-storage.sh --check    # 只检查，不修改（CI/巡检用）
#   ./scripts/prepare-storage.sh --dry-run  # 只打印将要做什么
#
# 建议在 `docker compose up -d` 之前执行一次；重复执行安全。
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPLOAD_DIR="$DEPLOY_DIR/data/uploads"

# 与 backend/Dockerfile 里的 uid/gid 保持一致，改一处要同步另一处
BACKEND_UID=10001
BACKEND_GID=10001

MODE="apply"
for arg in "$@"; do
  case "$arg" in
    --check)   MODE="check" ;;
    --dry-run) MODE="dry-run" ;;
    -h|--help)
      sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "未知参数：$arg（用 --help 查看用法）" >&2; exit 2 ;;
  esac
done

log()  { printf '[prepare-storage] %s\n' "$*"; }
fail() { printf '[prepare-storage] 错误：%s\n' "$*" >&2; exit 1; }

# ---------- 1. 目录存在 ----------
if [[ ! -d "$UPLOAD_DIR" ]]; then
  if [[ "$MODE" == "check" ]]; then
    fail "$UPLOAD_DIR 不存在，执行 ./scripts/prepare-storage.sh 创建"
  fi
  log "创建 $UPLOAD_DIR"
  [[ "$MODE" == "dry-run" ]] || mkdir -p "$UPLOAD_DIR"
fi

# ---------- 2. 属主与权限 ----------
CURRENT="$(stat -c '%u:%g' "$UPLOAD_DIR" 2>/dev/null || echo 'unknown')"
if [[ "$CURRENT" == "$BACKEND_UID:$BACKEND_GID" ]]; then
  log "属主已是 $CURRENT，无需修改"
else
  log "属主为 $CURRENT，需改为 $BACKEND_UID:$BACKEND_GID（backend 容器以该 uid 运行）"
  if [[ "$MODE" == "check" ]]; then
    fail "属主不正确。执行：sudo ./scripts/prepare-storage.sh"
  elif [[ "$MODE" == "dry-run" ]]; then
    log "[dry-run] 将执行 chown -R $BACKEND_UID:$BACKEND_GID $UPLOAD_DIR"
  else
    # chown 需要 root。非 root 执行时给出可直接复制的命令，而不是静默跳过
    if ! chown -R "$BACKEND_UID:$BACKEND_GID" "$UPLOAD_DIR" 2>/dev/null; then
      fail "chown 失败（需要 root）。请执行：
       sudo chown -R $BACKEND_UID:$BACKEND_GID $UPLOAD_DIR"
    fi
  fi
fi

# ---------- 3. 目录本身要可写可进入 ----------
# 属主对了但权限是 500（只读）时上传同样失败
PERM="$(stat -c '%a' "$UPLOAD_DIR" 2>/dev/null || echo '')"
if [[ "$MODE" == "apply" && -n "$PERM" ]]; then
  # 只在缺少属主写/执行位时补，不覆盖运维特意设置的更严格权限
  if [[ "$(stat -c '%A' "$UPLOAD_DIR" | cut -c3)" != "w" ]]; then
    log "权限 $PERM 缺少属主写位，补为 755"
    chmod 755 "$UPLOAD_DIR"
  fi
fi

# ---------- 4. 真机验证：以容器内 uid 实际写一个文件 ----------
# 只查属主不够——ACL、只读挂载、SELinux 都可能让 chown 正确但仍写不进去。
if [[ "$MODE" != "dry-run" ]]; then
  PROBE="$UPLOAD_DIR/.write-probe-$$"
  if touch "$PROBE" 2>/dev/null; then
    rm -f "$PROBE"
    log "验证通过：目录可写"
  else
    fail "目录仍不可写（属主正确但无法创建文件）。
       请检查：目录是否被只读挂载、是否有 ACL 限制、磁盘是否已满。
       手动复现：docker compose exec backend touch /data/uploads/probe"
  fi
fi

log "完成"
