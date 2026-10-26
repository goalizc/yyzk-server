"""后台操作审计查询（契约 §6）。

三个入口对应三种排查路径：
- 列表：按人 / 动作 / 对象 / IP / 时间段筛，回答「这件事是谁干的」
- 汇总：按人聚合，回答「最近谁在干什么、谁老失败、谁从多个 IP 来」
- 导出：CSV 拖出来交给 HR 或走流程，回答「把证据给我」
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import BusinessError
from app.core.permissions import AUDIT_READ, require
from app.core.time import to_app_tz, to_db_datetime
from app.database import get_db
from app.models import AuditLog, User
from app.schemas.audit import (
    ActorSummary,
    AuditLogDetail,
    AuditLogItem,
    AuditLogPage,
    AuditSummary,
)
from app.services.audit import known_actions
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()


def _apply_filters(
    db: Session,
    stmt: Select,
    *,
    user_id: int | None,
    username: str | None,
    action: str | None,
    target_type: str | None,
    target_id: str | None,
    result: str | None,
    ip: str | None,
    start_date: date | None,
    end_date: date | None,
    keyword: str | None,
) -> Select:
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if username and username.strip():
        stmt = stmt.where(AuditLog.username.like(like_pattern(username), escape=LIKE_ESCAPE))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if target_id:
        stmt = stmt.where(AuditLog.target_id == target_id.strip())
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if ip and ip.strip():
        stmt = stmt.where(AuditLog.ip.like(like_pattern(ip), escape=LIKE_ESCAPE))

    tz = get_settings().timezone
    if start_date is not None:
        stmt = stmt.where(
            AuditLog.created_at
            >= to_db_datetime(db, datetime.combine(start_date, time.min, tzinfo=tz))
        )
    if end_date is not None:
        # 半开区间：< 次日 00:00，避免漏掉 23:59:59.001–.999
        stmt = stmt.where(
            AuditLog.created_at
            < to_db_datetime(db, datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz))
        )
    if keyword and keyword.strip():
        pattern = like_pattern(keyword)
        stmt = stmt.where(
            or_(
                AuditLog.target_name.like(pattern, escape=LIKE_ESCAPE),
                AuditLog.path.like(pattern, escape=LIKE_ESCAPE),
                AuditLog.username.like(pattern, escape=LIKE_ESCAPE),
            )
        )
    return stmt


def _to_item(row: AuditLog) -> AuditLogItem:
    return AuditLogItem(
        id=row.id,
        created_at=row.created_at,
        username=row.username,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        target_name=row.target_name,
        method=row.method,
        path=row.path,
        status=row.status,
        result=row.result,
        ip=row.ip,
        request_id=row.request_id,
    )


@router.get(
    "/audit-logs/actions",
    response_model=list[str],
    summary="可选的动作清单（前端筛选用）",
)
def list_actions(_: User = Depends(require(AUDIT_READ))) -> list[str]:
    return known_actions()


@router.get(
    "/audit-logs/summary",
    response_model=AuditSummary,
    summary="按人聚合（谁在操作、谁老失败、谁多 IP）",
)
def audit_summary(
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(AUDIT_READ)),
) -> AuditSummary:
    since = datetime.now(get_settings().timezone) - timedelta(days=days)
    base = select(
        AuditLog.user_id,
        AuditLog.username,
        func.count().label("total"),
        func.sum(case((AuditLog.result == "failure", 1), else_=0)).label("failures"),
        func.count(func.distinct(AuditLog.ip)).label("distinct_ips"),
        func.max(AuditLog.created_at).label("last_at"),
    ).where(AuditLog.created_at >= to_db_datetime(db, since))
    rows = db.execute(
        base.group_by(AuditLog.user_id, AuditLog.username)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()

    total = db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.created_at >= to_db_datetime(db, since)
        )
    ) or 0
    failures = db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.created_at >= to_db_datetime(db, since),
            AuditLog.result == "failure",
        )
    ) or 0

    return AuditSummary(
        period_days=days,
        total=total,
        failures=failures,
        actors=[
            ActorSummary(
                user_id=row[0],
                username=row[1],
                total=row[2],
                failures=int(row[3] or 0),
                distinct_ips=row[4],
                last_at=row[5],
            )
            for row in rows
        ],
    )


@router.get(
    "/audit-logs/export",
    summary="导出当前筛选结果为 CSV（上限 5000 行）",
    response_class=Response,
)
def export_audit_logs(
    user_id: int | None = Query(None),
    username: str | None = Query(None, max_length=50),
    action: str | None = Query(None, max_length=50),
    target_type: str | None = Query(None, max_length=30),
    target_id: str | None = Query(None, max_length=50),
    result: str | None = Query(None, pattern="^(success|failure)$"),
    ip: str | None = Query(None, max_length=50),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    keyword: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(AUDIT_READ)),
) -> Response:
    stmt = _apply_filters(
        db,
        select(AuditLog),
        user_id=user_id,
        username=username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result=result,
        ip=ip,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
    ).order_by(AuditLog.created_at.desc()).limit(5000)
    rows = list(db.scalars(stmt))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["时间", "账号", "动作", "对象类型", "对象ID", "对象名称", "结果", "状态码", "IP", "请求ID", "路径"]
    )
    for row in rows:
        writer.writerow(
            [
                to_app_tz(row.created_at).isoformat(),
                row.username,
                row.action,
                row.target_type or "",
                row.target_id or "",
                row.target_name or "",
                "成功" if row.result == "success" else "失败",
                row.status,
                row.ip or "",
                row.request_id or "",
                row.path,
            ]
        )
    # BOM：Excel 直接双击打开时中文不乱码
    body = "\ufeff" + buffer.getvalue()
    stamp = datetime.now(get_settings().timezone).strftime("%Y%m%d-%H%M")
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="audit-logs-{stamp}.csv"'},
    )


@router.get("/audit-logs", response_model=AuditLogPage, summary="操作日志列表")
def list_audit_logs(
    user_id: int | None = Query(None, description="按操作人 ID"),
    username: str | None = Query(None, max_length=50, description="按账号模糊匹配"),
    action: str | None = Query(None, max_length=50),
    target_type: str | None = Query(None, max_length=30),
    target_id: str | None = Query(None, max_length=50),
    result: str | None = Query(None, pattern="^(success|failure)$"),
    ip: str | None = Query(None, max_length=50),
    start_date: date | None = Query(None, description="时间起（含），YYYY-MM-DD"),
    end_date: date | None = Query(None, description="时间止（含当日）"),
    keyword: str | None = Query(None, max_length=100, description="匹配对象名/路径/账号"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(AUDIT_READ)),
) -> AuditLogPage:
    stmt = _apply_filters(
        db,
        select(AuditLog),
        user_id=user_id,
        username=username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result=result,
        ip=ip,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

    # 不用 services.pagination.paginate：那个返回 Row 元组，适合多列查询；
    # 这里是单模型查询，要的是实体对象
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return AuditLogPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_item(row) for row in rows],
    )


@router.get("/audit-logs/{log_id}", response_model=AuditLogDetail, summary="操作日志详情")
def get_audit_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(AUDIT_READ)),
) -> AuditLogDetail:
    row = db.get(AuditLog, log_id)
    if row is None:
        raise BusinessError("NOT_FOUND", "日志不存在", 404)
    item = _to_item(row)
    return AuditLogDetail(
        **item.model_dump(),
        user_id=row.user_id,
        error_code=row.error_code,
        user_agent=row.user_agent,
        detail=row.detail or {},
    )
