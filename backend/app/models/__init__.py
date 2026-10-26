"""SQLAlchemy 模型（11 张表）。

与 `deploy/schema.sql` 一一对应；全新库由 schema.sql 直接建到最新结构，
已有库由 `deploy/migrations` 迁移。模型只负责读写映射，
因此不在此重复声明 CHECK 约束与索引。
"""

from app.models.audit_log import AuditLog
from app.models.fault import Fault
from app.models.part import Part
from app.models.product import Product
from app.models.product_line import ProductLine
from app.models.query_log import QueryLog
from app.models.ticket import Ticket, TicketStatusLog
from app.models.user import User, UserPermissionGrant, UserProductLine

__all__ = [
    "AuditLog",
    "Fault",
    "Part",
    "Product",
    "ProductLine",
    "QueryLog",
    "Ticket",
    "TicketStatusLog",
    "User",
    "UserPermissionGrant",
    "UserProductLine",
]
