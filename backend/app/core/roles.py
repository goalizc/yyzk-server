"""角色优先级：一人多岗时用于派生一个兼容展示的单一角色。"""

from __future__ import annotations

from collections.abc import Iterable

# 管理职责越强越靠前；角色白名单、输入规范化与接口输出共用这个顺序。
ROLE_PRIORITY = (
    "super_admin",
    "supervisor",
    "product_planner",
    "warehouse_manager",
    "warehouse_clerk",
    "auditor",
    "agent",
)


def primary_role(roles: Iterable[str]) -> str:
    values = set(roles)
    for role in ROLE_PRIORITY:
        if role in values:
            return role
    return "agent"
