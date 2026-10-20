"""结构化日志：单行 JSON 到 stdout，由 docker logs 收集。

字段（系统架构设计.md §7）：time / level / request_id / method / path / status / duration_ms
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# 健康检查每 15 秒一次，写日志只会淹没真正的访问记录（契约 §8）
_SILENT_PATHS = frozenset({"/api/health"})

# LogRecord 自带属性，序列化其余字段时跳过
_RESERVED = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {"message", "asctime", "request_id", "taskName", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or request_id_ctx.get(),
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str | None = None) -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel((level or settings.log_level).upper())

    # uvicorn 自己的 handler 会输出非 JSON 行，统一交给 root
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # 访问日志由 RequestContextMiddleware 统一输出（含 request_id 与耗时），
    # 关掉 uvicorn 自带的那条，否则每个请求会打两行
    logging.getLogger("uvicorn.access").disabled = True


# 客户端传入的 request_id 只接受安全字符，避免伪造日志字段或回显超长头
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def safe_request_id(raw: str | None) -> str:
    """上游（Nginx/网关）带来的 request_id 需校验后再落日志与响应头。"""
    if raw:
        candidate = raw.strip()
        if _REQUEST_ID_RE.match(candidate):
            return candidate
    return uuid.uuid4().hex[:12]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 request_id，并在结束时输出一条访问日志。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = safe_request_id(request.headers.get("X-Request-ID"))
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logging.getLogger("app.access").exception(
                "请求异常",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": duration_ms,
                },
            )
            raise
        finally:
            request_id_ctx.reset(token)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        if request.url.path not in _SILENT_PATHS:
            logging.getLogger("app.access").info(
                "请求完成",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response
