"""查询日志写入：客户端信息提取与日志构造（契约 §4）。"""

from __future__ import annotations

from fastapi import Request

from app.models import QueryLog

IP_MAX_LEN = 50
UA_MAX_LEN = 200


def client_info(request: Request) -> tuple[str | None, str | None]:
    """返回 (ip, user_agent)。uvicorn 开了 --proxy-headers，request.client 已是真实来源 IP。"""
    ip = request.client.host if request.client else None
    if not ip:
        ip = request.headers.get("x-real-ip")
    ua = request.headers.get("user-agent")
    return (ip[:IP_MAX_LEN] if ip else None, ua[:UA_MAX_LEN] if ua else None)


def build_log(
    request: Request,
    *,
    hit: bool,
    product_id: int | None,
    part_id: int | None,
    fault_id: int | None = None,
    raw_query: str | None = None,
) -> QueryLog:
    """构造一条待写入的日志（由调用方负责 add/commit，便于与业务同事务）。"""
    ip, user_agent = client_info(request)
    return QueryLog(
        product_id=product_id,
        part_id=part_id,
        fault_id=fault_id,
        raw_query=raw_query,
        hit=hit,
        ip=ip,
        user_agent=user_agent,
    )
