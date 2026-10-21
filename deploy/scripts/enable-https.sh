#!/usr/bin/env bash
# ============================================================
# 售后故障诊断系统 - 启用 HTTPS
#
# 把 deploy/nginx-https.conf.example 落地为可用配置：
#   1. 校验证书文件存在且可读
#   2. 从 example 生成 nginx.conf，替换 server_name 占位符
#   3. 自动改 docker-compose.yml：开放 443、挂载 certs 目录
#   4. nginx -t 校验语法后再 reload，失败则回滚
#
# 用法：
#   ./enable-https.sh --domain fault.example.com
#   ./enable-https.sh --domain fault.example.com --cert-dir /etc/letsencrypt/live/fault
#   ./enable-https.sh --check          # 只检查当前状态
#
# 证书要求（--cert-dir 下）：
#   fullchain.pem  完整证书链
#   privkey.pem    私钥
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DOMAIN=""
CERT_DIR=""
MODE="apply"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --cert-dir) CERT_DIR="$2"; shift 2 ;;
    --check) MODE="check"; shift ;;
    -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1" >&2; exit 2 ;;
  esac
done

log()  { echo "[https] $*"; }
warn() { echo "[https] [警告] $*" >&2; }
die()  { echo "[https] [ERROR] $*" >&2; exit 1; }

cd "$DEPLOY_DIR"
[[ -f nginx-https.conf.example ]] || die "找不到 nginx-https.conf.example"
[[ -f docker-compose.yml ]] || die "找不到 docker-compose.yml"

CERT_DIR="${CERT_DIR:-$DEPLOY_DIR/certs}"

# ---------- 检查模式 ----------
if [[ "$MODE" == "check" ]]; then
  echo ""
  echo "HTTPS 状态检查"
  echo "----------------------------------------"
  if grep -q "nginx-https.conf" nginx.conf 2>/dev/null || grep -q "listen 443" nginx.conf 2>/dev/null; then
    log "nginx.conf：已启用 HTTPS 配置"
  else
    warn "nginx.conf：当前是 HTTP 配置"
  fi
  # 注意排除注释行：compose 里本来就有 `# - "443:443"` 的说明性注释，
  # 直接 grep 会把注释当成已启用，给出"已开放 443"的假结论。
  if grep -qE '^\s*-\s*"443:443"' docker-compose.yml; then
    log "compose：已开放 443"
  else
    warn "compose：未开放 443"
  fi
  [[ -f "$CERT_DIR/fullchain.pem" ]] \
    && log "证书：fullchain.pem 存在" || warn "证书：$CERT_DIR/fullchain.pem 不存在"
  [[ -f "$CERT_DIR/privkey.pem" ]] \
    && log "私钥：privkey.pem 存在" || warn "私钥：$CERT_DIR/privkey.pem 不存在"
  echo ""
  exit 0
fi

# ---------- 必要参数 ----------
[[ -n "$DOMAIN" ]] || die "必须指定 --domain（如 fault.example.com）"
[[ -f "$CERT_DIR/fullchain.pem" ]] || die "证书不存在: $CERT_DIR/fullchain.pem"
[[ -f "$CERT_DIR/privkey.pem" ]] || die "私钥不存在: $CERT_DIR/privkey.pem"

# 私钥权限过宽是个真实风险：644 意味着同机任何用户都能读
PRIV_PERM=$(stat -c '%a' "$CERT_DIR/privkey.pem" 2>/dev/null || echo "600")
if [[ "$PRIV_PERM" != "600" && "$PRIV_PERM" != "640" ]]; then
  warn "私钥权限为 $PRIV_PERM，建议 chmod 600 $CERT_DIR/privkey.pem"
fi

log "目标域名: $DOMAIN"
log "证书目录: $CERT_DIR"

# ---------- 备份 ----------
BACKUP_TAG=".pre-https.$(date +%Y%m%d_%H%M%S)"
cp nginx.conf "nginx.conf$BACKUP_TAG"
cp docker-compose.yml "docker-compose.yml$BACKUP_TAG"
log "已备份原配置（$BACKUP_TAG）"

restore() {
  mv "nginx.conf$BACKUP_TAG" nginx.conf
  mv "docker-compose.yml$BACKUP_TAG" docker-compose.yml
  warn "已回滚到原配置"
}

# ---------- 1. 生成 nginx.conf ----------
# example 里是 your.domain.com 占位，直接替换
sed "s/your\.domain\.com/$DOMAIN/g" nginx-https.conf.example > nginx.conf.https.new
log "已生成 HTTPS 配置"

# ---------- 2. 改 compose ----------
# 用 python3 做结构化修改而不是 sed：compose 是 YAML，sed 改缩进容易改坏
command -v python3 >/dev/null || { restore; die "需要 python3 来安全地修改 compose 文件"; }
python3 - "$CERT_DIR" <<'PY' || { restore; exit 1; }
import re, sys, pathlib

cert_dir = sys.argv[1]
p = pathlib.Path('docker-compose.yml')
s = p.read_text(encoding='utf-8')

# 开放 443。用正则匹配 ports 里的 80 映射行（行内可能有尾随空格），
# 单纯字符串 replace 在存在注释/缩进差异时会静默失配。
if not re.search(r'^\s*-\s*"443:443"', s, flags=re.M):
    s, n = re.subn(
        r'^(\s*)-\s*"80:80"\s*$',
        r'\1- "80:80"\n\1- "443:443"',
        s,
        count=1,
        flags=re.M,
    )
    if n == 0:
        sys.exit("[https] [ERROR] 在 compose 里找不到 ports 的 80 映射，请手工添加 443")
    print("[https] compose 已开放 443")

# 挂载证书目录（把注释行改成生效行）
s = s.replace(
    '      # - ./certs:/etc/nginx/certs:ro',
    '      - ./certs:/etc/nginx/certs:ro',
    1,
)
s = s.replace(
    '      # - /var/www/certbot:/var/www/certbot:ro',
    '      - ./certbot-www:/var/www/certbot:ro',
    1,
)

p.write_text(s, encoding='utf-8')
print("[https] compose 已更新：开放 443 + 挂载证书目录")
PY

# ---------- 3. 语法校验 ----------
log "校验 nginx 配置语法..."
mv nginx.conf.https.new nginx.conf
mkdir -p certbot-www

# 用临时容器跑 nginx -t，不碰运行中的服务
if ! docker run --rm \
      -v "$DEPLOY_DIR/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
      -v "$CERT_DIR:/etc/nginx/certs:ro" \
      nginx:1.25-alpine nginx -t 2>&1 | tail -5; then
  restore
  die "nginx 配置语法校验失败，已回滚"
fi

# ---------- 4. 生效 ----------
log "重建 nginx 容器使配置生效..."
docker compose up -d --force-recreate nginx >/dev/null 2>&1 || { restore; die "nginx 重建失败，已回滚"; }

sleep 5

# 自检在容器内部做：宿主机可能有 HTTPS_PROXY 等变量，curl 会走代理而不是直连，
# 从而得出"HTTPS 不可用"的错误结论（本机实测踩过）。
log "自检 HTTPS（容器内）..."
if docker compose exec -T nginx wget -qO- --no-check-certificate https://127.0.0.1/health 2>/dev/null | grep -q ok; then
  log "HTTPS 访问正常（/health 返回 ok）"
else
  warn "HTTPS 自检未通过。排查：docker compose logs nginx --tail 30"
fi

# 顺带确认 80 端口仍然给 healthcheck 返回 200（不能被 301 掉）
if docker compose exec -T nginx wget -qO- http://127.0.0.1/health 2>/dev/null | grep -q ok; then
  log "HTTP /health 正常（容器 healthcheck 不会卡住）"
else
  warn "HTTP /health 被跳转了，容器会一直 unhealthy！"
  warn "检查 nginx-https.conf.example 里 80 端口是否保留了 location = /health"
fi

rm -f "nginx.conf$BACKUP_TAG" "docker-compose.yml$BACKUP_TAG"
log "完成。原配置备份已清理；如需回滚请用 git checkout -- deploy/nginx.conf"
