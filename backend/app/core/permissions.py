"""权限码、角色模板、数据范围与生效权限。

权限是代码行为的一部分，不建数据库表；用户角色存 `user_roles`（可多角色），
权限与数据范围按全部角色的并集计算。
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

# 进销存：独立账域，按 inventory:<资源>:<动作> 组织
INVENTORY_SKU_READ = "inventory:sku:read"
INVENTORY_SKU_WRITE = "inventory:sku:write"
INVENTORY_INBOUND_READ = "inventory:inbound:read"
INVENTORY_INBOUND_WRITE = "inventory:inbound:write"
INVENTORY_OUTBOUND_READ = "inventory:outbound:read"
INVENTORY_OUTBOUND_WRITE = "inventory:outbound:write"
INVENTORY_MOVEMENT_READ = "inventory:movement:read"
# 盘点/冲正能凭空改账，单独拆出高危码，且不允许临时授权
INVENTORY_ADJUST_WRITE = "inventory:adjust:write"
INVENTORY_EXPORT = "inventory:export"
# L1 只登记不启用：没有端点 require 它，等做金额账时再接读路径
INVENTORY_COST_READ = "inventory:cost:read"
# 主管改已生效入库/出库单（数量、种类）：录入员不含，仅 warehouse_manager 具备
INVENTORY_DOC_EDIT = "inventory:doc:edit"

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
        INVENTORY_SKU_READ,
        INVENTORY_SKU_WRITE,
        INVENTORY_INBOUND_READ,
        INVENTORY_INBOUND_WRITE,
        INVENTORY_OUTBOUND_READ,
        INVENTORY_OUTBOUND_WRITE,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_ADJUST_WRITE,
        INVENTORY_EXPORT,
        INVENTORY_COST_READ,
        INVENTORY_DOC_EDIT,
    }
)

# 角色中文名（仅文档/运维速查用；界面展示以 frontend/src/locales/*/common.js 为准）。
# 「仓管」限定词不能省：supervisor 是售后主管，裸写「主管」两个角色分不清。
ROLE_NAMES = {
    "super_admin": "超级管理员",
    "supervisor": "售后主管",
    "product_planner": "产品计划",
    "warehouse_clerk": "仓管录入员",
    "warehouse_manager": "仓管主管",
    "agent": "一线客服",
    "auditor": "只读审计",
}

# 录入员：对售后模块零权限的纯库存角色；盘点/冲正不在其内。
# 注意别为了「建 SKU 时能选关联产品/零件」给它 product:read / part:read——
# 那会让它落地页变成产品目录、侧边栏冒出售后菜单。库存域改用
# /admin/inventory/refs/* 两个只读引用端点（挂 inventory:sku:read）。
_INVENTORY_CLERK = frozenset(
    {
        INVENTORY_SKU_READ,
        INVENTORY_SKU_WRITE,
        INVENTORY_INBOUND_READ,
        INVENTORY_INBOUND_WRITE,
        INVENTORY_OUTBOUND_READ,
        INVENTORY_OUTBOUND_WRITE,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_EXPORT,
    }
)
# 主管：录入员全部权限 + 改已生效入库/出库单（数量、种类）
_INVENTORY_MANAGER = _INVENTORY_CLERK | frozenset({INVENTORY_DOC_EDIT})

# 只读审计：台账与流水全域只读，可导出；不含任何写码，也不含成本码
_AUDITOR_INVENTORY = frozenset(
    {
        INVENTORY_SKU_READ,
        INVENTORY_INBOUND_READ,
        INVENTORY_OUTBOUND_READ,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_EXPORT,
    }
)

# 主数据唯一业务写者：产品/零件/产品线。售后与物资只读引用。
# super_admin 仍保留全部权限作为 break-glass，不在此集合内。
_PRODUCT_MASTER = frozenset(
    {
        PRODUCT_READ,
        PRODUCT_WRITE,
        PART_READ,
        PART_WRITE,
        PRODUCT_LINE_READ,
        PRODUCT_LINE_WRITE,
    }
)

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "super_admin": ALL_PERMISSIONS,
    # 售后主管保留主数据只读，不再写产品/零件/产品线
    "supervisor": ALL_PERMISSIONS
    - {
        USER_READ,
        USER_WRITE,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    },
    "product_planner": _PRODUCT_MASTER,
    "warehouse_clerk": _INVENTORY_CLERK,
    "warehouse_manager": _INVENTORY_MANAGER,
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
    )
    | _AUDITOR_INVENTORY,
}

# 库存域统一 ALL：SKU 的 part_id 可空，纯物资没有产品线可判，
# 继承 LINES 会导致谁都看不见。service 层显式写死，勿复用 apply_ticket_scope。
_DATA_SCOPE: dict[str, str] = {
    "super_admin": ALL,
    "supervisor": ALL,
    "product_planner": ALL,
    "warehouse_clerk": ALL,
    "warehouse_manager": ALL,
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
    INVENTORY_SKU_WRITE: frozenset({INVENTORY_SKU_READ}),
    INVENTORY_INBOUND_READ: frozenset({INVENTORY_SKU_READ}),
    INVENTORY_INBOUND_WRITE: frozenset({INVENTORY_INBOUND_READ}),
    INVENTORY_OUTBOUND_READ: frozenset({INVENTORY_SKU_READ}),
    INVENTORY_OUTBOUND_WRITE: frozenset({INVENTORY_OUTBOUND_READ}),
    INVENTORY_MOVEMENT_READ: frozenset({INVENTORY_SKU_READ}),
    INVENTORY_ADJUST_WRITE: frozenset(
        {INVENTORY_MOVEMENT_READ, INVENTORY_INBOUND_READ, INVENTORY_OUTBOUND_READ}
    ),
    INVENTORY_EXPORT: frozenset(
        {
            INVENTORY_SKU_READ,
            INVENTORY_INBOUND_READ,
            INVENTORY_OUTBOUND_READ,
            INVENTORY_MOVEMENT_READ,
        }
    ),
    INVENTORY_COST_READ: frozenset({INVENTORY_SKU_READ}),
    INVENTORY_DOC_EDIT: frozenset(
        {
            INVENTORY_INBOUND_READ,
            INVENTORY_INBOUND_WRITE,
            INVENTORY_OUTBOUND_READ,
            INVENTORY_OUTBOUND_WRITE,
        }
    ),
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
    """多角色取最宽范围：任一角色为 ALL 即 ALL。"""
    if not user.roles:
        return LINES
    scopes = {role_scope(item.role) for item in user.roles}
    return ALL if ALL in scopes else LINES


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# 永远不可临时授予的权限码。发放侧与运行时共用同一集合：
# 只挡发放挡不住存量行——008 之前写入的 product:write 最长留 180 天，
# 从备份恢复旧 grants 表也会重现，所以运行时必须再过滤一次。
UNGRANTABLE_PERMISSIONS: frozenset[str] = frozenset(
    {
        USER_WRITE,
        INVENTORY_ADJUST_WRITE,
        INVENTORY_COST_READ,
        PRODUCT_WRITE,
        PART_WRITE,
        PRODUCT_LINE_WRITE,
    }
)


def active_grants(db: Session, user_id: int) -> list[str]:
    """未收回、未过期的临时授权。按 Python 侧比较，兼容 SQLite 单测。

    已剔除不可授予的权限码：这些码即使存在于表里也不生效，
    避免「迁移收回了才安全」这种把不变量交给一次性 UPDATE 的写法。
    """
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(UserPermissionGrant).where(
            UserPermissionGrant.user_id == user_id,
            UserPermissionGrant.revoked_at.is_(None),
        )
    ).all()
    return [
        row.permission
        for row in rows
        if _as_utc(row.expires_at) > now and row.permission not in UNGRANTABLE_PERMISSIONS
    ]


def effective_permissions(db: Session, user: User) -> frozenset[str]:
    if not user.is_active:
        return frozenset()
    role_permissions_union: set[str] = set()
    for item in user.roles:
        role_permissions_union |= role_permissions(item.role)
    return expand(role_permissions_union | set(active_grants(db, user.id)))


def grantable_permissions() -> frozenset[str]:
    """可临时授予的权限。

    永远排除（与 `UNGRANTABLE_PERMISSIONS` 同源）：
    - `user:write`：临时授权会变成提权入口，可直接改角色；
    - `inventory:adjust:write`：冲正能凭空改账，不应带 expires_at / reason 临时发放；
    - `inventory:cost:read`：L1 只登记不启用、无端点使用，避免出现没有实际功能的选项；
    - `product:write` / `part:write` / `product_line:write`：
      主数据单写者，常规只能由 product_planner 角色持有；
      super_admin 的 break-glass 权限不通过临时授权转授。
    """
    return ALL_PERMISSIONS - UNGRANTABLE_PERMISSIONS


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
