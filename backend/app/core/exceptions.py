"""业务异常与统一错误体。

契约（API接口契约.md §0.2 / §7）：所有错误响应固定为
`{"detail": 中文可读, "code": 稳定机器码}`，禁止把堆栈返回给前端。
"""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_CHINESE = re.compile(r"[\u4e00-\u9fff]")

# HTTP 状态码 → 默认错误码（契约 §7 已登记的机器码，不在此新增）
_STATUS_CODE_MAP = {
    400: "VALIDATION_ERROR",
    401: "AUTH_TOKEN_EXPIRED",
    403: "AUTH_USER_DISABLED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "UPLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}

_DEFAULT_DETAIL = {
    "AUTH_TOKEN_EXPIRED": "登录已过期，请重新登录",
    "NOT_FOUND": "接口不存在",
    "METHOD_NOT_ALLOWED": "接口不支持该请求方法",
    "RATE_LIMITED": "操作过于频繁，请稍后再试",
    "UPLOAD_TOO_LARGE": "文件超过 20MB 限制",
    "INTERNAL_ERROR": "服务器内部错误，请稍后重试",
    "SERVICE_UNAVAILABLE": "服务暂时不可用，请稍后重试",
    "VALIDATION_ERROR": "参数校验失败",
}


class BusinessError(Exception):
    """业务异常。由全局处理器转成 {detail, code}。"""

    def __init__(self, code: str, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def error_response(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})


def _validation_detail(exc: RequestValidationError) -> str:
    """取首条错误，优先使用自定义 validator 抛出的中文提示。"""
    errors = exc.errors()
    if not errors:
        return _DEFAULT_DETAIL["VALIDATION_ERROR"]

    first = errors[0]
    message = str(first.get("msg", "")).removeprefix("Value error, ").strip()
    if _CHINESE.search(message):
        return message

    location = [str(part) for part in first.get("loc", ()) if part != "body"]
    return f"参数校验失败：{'.'.join(location)}" if location else "参数校验失败"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def _business_error(_: Request, exc: BusinessError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "VALIDATION_ERROR", _validation_detail(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODE_MAP.get(exc.status_code, "VALIDATION_ERROR")
        detail = exc.detail if isinstance(exc.detail, str) and _CHINESE.search(exc.detail) else ""
        return error_response(exc.status_code, code, detail or _DEFAULT_DETAIL.get(code, "请求失败"))

    @app.exception_handler(Exception)
    async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # 堆栈只进日志，不进响应体
        logger.exception("未捕获异常 path=%s", request.url.path, exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", _DEFAULT_DETAIL["INTERNAL_ERROR"])
