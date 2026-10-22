"""统计看板接口（契约 §6）。口径全部在 services/stats.py，路由只做参数校验。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import STATS_READ, require
from app.database import get_db
from app.models import User
from app.schemas.stats import MissedItem, StatsOverview, TopFaultItem
from app.services import stats as stats_service

router = APIRouter()

_DAYS = Query(30, ge=0, le=365, description="统计窗口天数，0 表示全部")


@router.get("/overview", response_model=StatsOverview, summary="看板四张卡")
def get_overview(
    days: int = _DAYS,
    db: Session = Depends(get_db),
    _: User = Depends(require(STATS_READ)),
) -> StatsOverview:
    return StatsOverview(**stats_service.overview(db, days))


@router.get("/top-faults", response_model=list[TopFaultItem], summary="热门故障 TOP N")
def get_top_faults(
    days: int = _DAYS,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require(STATS_READ)),
) -> list[TopFaultItem]:
    return [TopFaultItem(**item) for item in stats_service.top_faults(db, days, limit)]


@router.get("/missed", response_model=list[MissedItem], summary="未命中检索词")
def get_missed(
    days: int = _DAYS,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(STATS_READ)),
) -> list[MissedItem]:
    return [MissedItem(**item) for item in stats_service.missed(db, days, limit)]
