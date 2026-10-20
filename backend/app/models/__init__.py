"""SQLAlchemy 模型（7 张表）。

与 `deploy/schema.sql` 一一对应；建表以 schema.sql 为准（无迁移框架），
模型只负责读写映射，因此不在此重复声明 CHECK 约束与索引。
"""

from app.models.fault import Fault
from app.models.part import Part
from app.models.product import Product
from app.models.query_log import QueryLog
from app.models.ticket import Ticket, TicketStatusLog
from app.models.user import User

__all__ = [
    "Fault",
    "Part",
    "Product",
    "QueryLog",
    "Ticket",
    "TicketStatusLog",
    "User",
]
