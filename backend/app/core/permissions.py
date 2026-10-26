"""权限码、角色模板、数据范围与生效权限。

权限是代码行为的一部分，不建数据库表；角色固定四种。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError
from app.database import get_db
from app.models import User, UserPermissionGrant

# ---- 数据范围 ----
ALL = "ALL"
LINES = "LINES"

# ---- 权限码 ----
TICKET_READ = "ticket:read"
TICKET_WRITE = "ticket:write"
TICKET_ASSIGN = "ticket:assign"
PRODUCT_READ = "product:read"
PRODUCT_WRITE = "product:write"
PART_READ = "part:read"
PART_WRITE = "part:write"
FAULT_READ = "fault:read"
FAULT_WRITE = "fault:write"
UPLOAD_WRITE = "upload:write"
STATS_READ = "stats:read"
USER_READ = "user:read"
USER_WRITE = "user:write"
PRODUCT_LINE_READ = "product_line:read"
PRODUCT_LINE_WRITE = "product_line:write"
# 审计日志：含他人 IP 与操作轨迹，只给管理岗与只读审计岗
AUDIT_READ = "audit:read"

ALL_PERMISSIONS = frozenset(
    {
        TICKET_READ,
        TICKET_WRITE,
        TICKET_ASSIGN,
        PRODUCT_READ,
        PRODUCT_WRITE,
        PART_READ,
        PART_WRITE,
        FAULT_READ,
        FAULT_WRITE,
        UPLOAD_WRITE,
        STATS_READ,
        USER_READ,
        USER_WRITE,
        PRODUCT_LINE_READ,
        PRODUCT_LINE_WRITE,
        AUDIT_READ,
    }
)

ROLE_NAMES = {
    "super_admin": "超级管理员",
    "supervisor": "售后主管",
    "agent": "一线客服",
    "auditor": "只读审计",
}

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "super_admin": ALL_PERMISSIONS,
    "supervisor": ALL_PERMISSIONS - {USER_READ, USER_WRITE},
    "agent": frozenset({TICKET_READ, TICKET_WRITE, FAULT_READ}),
    "auditor": frozenset(
        {
            TICKET_READ,
            PRODUCT_READ,
            PART_READ,
            FAULT_READ,
            STATS_READ,
            USER_READ,
            PRODUCT_LINE_READ,
            AUDIT_READ,
        }
    ),
}

_DATA_SCOPE: dict[str, str] = {
    "super_admin": ALL,
    "supervisor": ALL,
    "agent": LINES,
    "auditor": ALL,
}

_DEPENDENCIES: dict[str, frozenset[str]] = {
    TICKET_WRITE: frozenset({TICKET_READ}),
    TICKET_ASSIGN: frozenset({TICKET_READ, TICKET_WRITE}),
    FAULT_WRITE: frozenset({FAULT_READ, PRODUCT_READ, PART_READ, UPLOAD_WRITE}),
    PRODUCT_WRITE: frozenset({PRODUCT_READ}),
    PART_WRITE: frozenset({PART_READ, PRODUCT_READ}),
    PRODUCT_LINE_WRITE: frozenset({PRODUCT_LINE_READ}),
    USER_WRITE: frozenset({USER_READ}),
}


def expand(permissions: Iterable[str]) -> frozenset[str]:
    """按依赖闭包补齐权限，直到不再变化。"""
    result = set(permissions)
    changed = True
    while changed:
        changed = False
        for permission in tuple(result):
            for dependency in _DEPENDENCIES.get(permission, frozenset()):
                if dependency not in result:
                    result.add(dependency)
                    changed = True
    return frozenset(result)


def role_permissions(role: str) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def role_scope(role: str) -> str:
    return _DATA_SCOPE.get(role, LINES)


def data_scope(user: User) -> str:
    return role_scope(user.role)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def active_grants(db: Session, user_id: int) -> list[str]:
    """未收回、未过期的临时授权。按 Python 侧比较，兼容 SQLite 单测。"""
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(UserPermissionGrant).where(
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.revoked_at.is_(None),
        )
    ).all()
    return [row.permission for row in rows if _as_utc(row.expires_at) > now]


def effective_permissions(db: Session, user: User) -> frozenset[str]:
    if not user.is_active:
        return frozenset()
    return expand(role_permissions(user.role) | set(active_grants(db, user.id)))


def grantable_permissions() -> frozenset[str]:
    """可临时授予的权限：user:write 会变成提权入口，永远排除。"""
    return ALL_PERMISSIONS - {USER_WRITE}


def current_permissions(user: User, db: Session) -> list[str]:
    return sorted(effective_permissions(db, user))


def require(permission: str) -> Callable[..., User]:
    """FastAPI 依赖：无权限返回 403 PERMISSION_DENIED。"""

    def dependency(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if permission not in effective_permissions(db, user):
            raise BusinessError("PERMISSION_DENIED", "无权限执行此操作", 403)
        return user

    return dependency
