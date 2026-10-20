"""FastAPI 应用入口：中间件、异常处理、路由注册。

建表不在应用启动时执行——DDL 由 deploy/schema.sql 在数据卷初始化时一次性建好，
避免应用与 schema 两处定义发生漂移。
"""

from __future__ import annotations

from fastapi import FastAPI

from app import models  # noqa: F401  确保 7 张表的模型注册到 Base.metadata
from app.api import admin, admin_faults, admin_tickets, auth, health, public, stats
from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestContextMiddleware, setup_logging

settings = get_settings()

setup_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    # 走 /api 前缀，Nginx 反代后可直接访问 /api/docs。
    # 默认关闭（DEBUG=false）：对外不暴露接口清单，本地调试在 .env 里设 DEBUG=true
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

app.include_router(health.router, prefix="/api", tags=["运维"])
app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])
app.include_router(public.router, prefix="/api", tags=["公开"])
app.include_router(admin.router, prefix="/api/admin", tags=["后台"])
app.include_router(admin_faults.router, prefix="/api/admin", tags=["后台"])
app.include_router(admin_tickets.router, prefix="/api/admin", tags=["后台"])
app.include_router(stats.router, prefix="/api/admin/stats", tags=["统计"])
