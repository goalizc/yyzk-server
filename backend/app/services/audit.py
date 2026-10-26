"""操作审计：把「谁、何时、从哪、做了什么、结果如何」落到 audit_logs。

三条设计原则：
1. **零侵入优先**：HTTP 方法 + 路径即可识别绝大多数动作（见 `_RULES`），
   新加端点只要在规则表补一行，不需要在 router 里写埋点代码。
2. **语义靠业务补**：端点内可用 `request.state.audit = {...}` 补充目标名、变更摘要
   （如工单状态 from/to），中间件会自动合并进 detail。
3. **审计不能影响主流程**：写库用独立会话，失败只打 warning —— 审计挂了也不能让业务 500。

不记录请求体：密码、客户手机号因此天然不会进入审计表。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from app.database import new_session
from app.models import (
    AuditLog,
    Fault,
    Part,
    Product,
    ProductLine,
    Ticket,
    User,
)

logger = logging.getLogger(__name__)

# (HTTP 方法, 路径正则, action, target_type, 取值组名)
# action 采用 `对象.动作` 形式，前端按前缀分组展示（auth.* / user.* / fault.*）。
# 正则存字符串而不是 re.Pattern：规则表要能一眼读懂，编译结果由 re 模块自己缓存
_RULES: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    (r"POST", r"^/api/auth/login$", "auth.login", "user", None),
    (r"PUT", r"^/api/auth/password$", "auth.password_change", "user", None),
    (r"POST", r"^/api/tickets$", "ticket.create", "ticket", None),
    (r"POST", r"^/api/admin/products$", "product.create", "product", None),
    (r"PUT", r"^/api/admin/products/(?P<id>\d+)$", "product.update", "product", "id"),
    (r"DELETE", r"^/api/admin/products/(?P<id>\d+)$", "product.delete", "product", "id"),
    (r"POST", r"^/api/admin/parts$", "part.create", "part", None),
    (r"PUT", r"^/api/admin/parts/(?P<id>\d+)$", "part.update", "part", "id"),
    (r"DELETE", r"^/api/admin/parts/(?P<id>\d+)$", "part.delete", "part", "id"),
    (r"POST", r"^/api/admin/product-lines$", "product_line.create", "product_line", None),
    (r"PUT", r"^/api/admin/product-lines/(?P<id>\d+)$", "product_line.update", "product_line", "id"),
    (r"DELETE", r"^/api/admin/product-lines/(?P<id>\d+)$", "product_line.delete", "product_line", "id"),
    (r"POST", r"^/api/admin/faults$", "fault.create", "fault", None),
    (r"PUT", r"^/api/admin/faults/(?P<id>\d+)$", "fault.update", "fault", "id"),
    (r"DELETE", r"^/api/admin/faults/(?P<id>\d+)$", "fault.delete", "fault", "id"),
    (r"PUT", r"^/api/admin/tickets/(?P<id>\d+)$", "ticket.update", "ticket", "id"),
    (r"POST", r"^/api/admin/users$", "user.create", "user", None),
    (r"PUT", r"^/api/admin/users/(?P<id>\d+)$", "user.update", "user", "id"),
    (r"POST", r"^/api/admin/users/(?P<id>\d+)/reset-password$", "user.reset_password", "user", "id"),
    (r"POST", r"^/api/admin/users/(?P<id>\d+)/grants$", "user.grant", "user", "id"),
    (r"DELETE", r"^/api/admin/users/(?P<id>\d+)/grants/(?P<grant>\d+)$", "user.revoke_grant", "user", "id"),
    (r"PUT", r"^/api/admin/users/(?P<id>\d+)/product-lines$", "user.set_product_lines", "user", "id"),
    # 审计导出本身也要留痕（meta-audit）：CSV 含所有人 IP，必须知道谁导过
    (r"GET", r"^/api/admin/audit-logs/export$", "audit.export", "audit", None),
    (r"POST", r"^/api/admin/upload$", "upload.create", "upload", None),
    (r"DELETE", r"^/api/admin/upload$", "upload.delete", "upload", None),
)


@dataclass(frozen=True)
class Match:
    action: str
    target_type: str | None
    target_id: str | None


def resolve(method: str, path: str) -> Match | None:
    """命中动作规则则返回 Match，未命中返回 None（只审计命中项，避免全量噪声）。"""
    for rule_method, pattern, action, target_type, group in _RULES:
        if rule_method != method.upper():
            continue
        found = re.compile(pattern).match(path)
        if found is None:
            continue
        target_id = found.group(group) if group else None
        return Match(action=action, target_type=target_type, target_id=target_id)
    return None


def known_actions() -> list[str]:
    """动作清单，供前端筛选下拉使用（与规则表同源，不会漂移）。"""
    return sorted({rule[2] for rule in _RULES})


# target_type → (模型, 用于展示的字段)。上传没有业务表，故不在表内。
_NAME_FIELDS: dict[str, tuple[type, str]] = {
    "fault": (Fault, "title"),
    "part": (Part, "name"),
    "product": (Product, "name"),
    "product_line": (ProductLine, "name"),
    "ticket": (Ticket, "ticket_no"),
    "user": (User, "username"),
}


def client_ip(request: Request) -> str | None:
    """Nginx 用 $remote_addr 覆盖 X-Real-IP，所以这两个头比 client.host 更可信。

    直连后端（绕过 Nginx）的场景下客户端可以伪造该头，但后端端口不对外暴露。
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()[:50]
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:50]
    return request.client.host if request.client else None


@dataclass
class AuditEvent:
    action: str
    method: str
    path: str
    status: int
    result: str
    username: str = "-"
    user_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def _lookup_target_name(target_type: str | None, target_id: str | None) -> str | None:
    if not target_type or not target_id:
        return None
    entry = _NAME_FIELDS.get(target_type)
    if entry is None:
        return None
    model, attr = entry
    if not target_id.isdigit():
        return None
    session = new_session()
    try:
        row = session.get(model, int(target_id))
        return getattr(row, attr, None) if row is not None else None
    except Exception:  # noqa: BLE001 取名字失败不能影响审计本身
        return None
    finally:
        session.close()


def record(event: AuditEvent) -> None:
    """写一条审计。任何异常都吞掉：审计组件不能把正常请求带崩。"""
    try:
        if not event.target_name:
            event.target_name = _lookup_target_name(event.target_type, event.target_id)

        session = new_session()
        try:
            session.add(
                AuditLog(
                    request_id=event.request_id,
                    user_id=event.user_id,
                    username=(event.username or "-")[:50],
                    action=event.action[:50],
                    target_type=event.target_type,
                    target_id=event.target_id[:50] if event.target_id else None,
                    target_name=event.target_name[:200] if event.target_name else None,
                    method=event.method[:10],
                    path=event.path[:200],
                    status=event.status,
                    result=event.result,
                    error_code=event.error_code[:40] if event.error_code else None,
                    ip=event.ip,
                    user_agent=event.user_agent[:200] if event.user_agent else None,
                    detail=event.detail or {},
                )
            )
            session.commit()
        finally:
            session.close()
    except Exception:  # noqa: BLE001
        logger.warning("审计写入失败 action=%s path=%s", event.action, event.path, exc_info=True)
