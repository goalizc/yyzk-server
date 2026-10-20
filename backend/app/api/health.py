"""运维接口：健康检查。"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.database import get_db
from app.schemas.common import ErrorBody, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# 数据库长时间不可用时 healthcheck 每 15 秒失败一次，日志按分钟限频，
# 避免故障期间把日志刷满（每个 worker 各自计时）
_WARN_INTERVAL_SECONDS = 60.0
_last_warn_at = 0.0


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="只检查数据库连通性，供容器 healthcheck 与外部拨测使用。",
    responses={503: {"model": ErrorBody, "description": "数据库不可用"}},
)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    global _last_warn_at

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        now = time.monotonic()
        if now - _last_warn_at >= _WARN_INTERVAL_SECONDS:
            _last_warn_at = now
            logger.warning("健康检查失败：数据库不可用", extra={"error": str(exc)[:200]})
        # 业务异常不能让容器被判死，这里只回 503，细节留在日志
        raise BusinessError("SERVICE_UNAVAILABLE", "数据库不可用", 503) from exc
    return HealthResponse(status="ok", db="ok")
