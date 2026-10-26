"""审计中间件：按动作规则给写请求留痕，业务代码无需逐端点埋点。

只处理 `services.audit.resolve()` 命中的请求（后台写操作、登录、客户建单），
读请求不进审计表——客户侧每次查询已经有 query_logs 表，再记一遍是重复存储。
"""

from __future__ import annotations

import logging

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.exceptions import BusinessError
from app.core.logging import request_id_ctx
from app.core.security import decode_access_token
from app.services.audit import AuditEvent, Match, client_ip, record, resolve

logger = logging.getLogger(__name__)


def _identity(request: Request) -> tuple[int | None, str]:
    """优先取业务层显式声明的身份（登录成功时 token 还没发出去），否则解析请求头。"""
    override = getattr(request.state, "audit", None) or {}
    user_id = override.get("user_id")
    username = override.get("username")
    if username:
        return user_id, str(username)

    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        try:
            payload = decode_access_token(header[7:])
            sub = payload.get("sub")
            return (int(sub) if sub else None), str(payload.get("username") or "-")
        except BusinessError:
            # token 过期/伪造：照样记一条失败动作，但不知道是谁
            return None, "-"
    return None, "-"


def _build(request: Request, match: Match, status: int) -> AuditEvent:
    override = getattr(request.state, "audit", None) or {}
    user_id, username = _identity(request)
    error_code = getattr(request.state, "audit_error_code", None)

    detail = dict(override.get("detail") or {})
    if not detail:
        # 没给业务摘要时，至少把查询参数记下来（不含 body，密码不会泄漏）
        query = dict(request.query_params)
        if query:
            detail["query"] = query
    if error_code:
        detail.setdefault("error_code", error_code)

    return AuditEvent(
        action=match.action,
        method=request.method,
        path=request.url.path,
        status=status,
        result="success" if status < 400 else "failure",
        username=username,
        user_id=user_id if user_id is not None else override.get("user_id"),
        target_type=override.get("target_type", match.target_type),
        target_id=override.get("target_id", match.target_id),
        target_name=override.get("target_name"),
        error_code=error_code,
        request_id=getattr(request.state, "request_id", None) or request_id_ctx.get(),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=detail,
    )


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        match = resolve(request.method, request.url.path)
        if match is None:
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception:
            # 未捕获异常由外层 ServerErrorMiddleware 转 500；这里先补一条失败记录
            await run_in_threadpool(record, _build(request, match, 500))
            raise

        await run_in_threadpool(record, _build(request, match, response.status_code))
        return response
