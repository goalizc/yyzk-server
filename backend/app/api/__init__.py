"""路由包。"""

from app.api import admin, admin_faults, admin_product_lines, admin_tickets, auth, health, public, stats

__all__ = [
    "admin",
    "admin_faults",
    "admin_product_lines",
    "admin_tickets",
    "auth",
    "health",
    "public",
    "stats",
]
