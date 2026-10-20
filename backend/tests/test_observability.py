"""横切关注点：request_id 处理与未捕获异常兜底。"""

from __future__ import annotations

import string

from fastapi.testclient import TestClient

from app.main import app


def _remove_route(path: str) -> None:
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != path]


def test_safe_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "gw-abc_123.XYZ"})

    assert response.headers["x-request-id"] == "gw-abc_123.XYZ"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    # 客户端可伪造该头，不能让任意内容进入日志字段或响应头
    response = client.get("/api/health", headers={"X-Request-ID": 'x"injected":1'})

    request_id = response.headers["x-request-id"]
    assert request_id != 'x"injected":1'
    assert len(request_id) == 12
    assert all(ch in string.hexdigits for ch in request_id)


def test_overlong_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "Z" * 2000})

    assert len(response.headers["x-request-id"]) == 12


def test_unhandled_exception_returns_internal_error(db) -> None:
    def boom() -> None:
        raise RuntimeError("内部细节 seCrEt 不应外泄")

    app.add_api_route("/api/_boom", boom, methods=["GET"])
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/_boom")
    finally:
        _remove_route("/api/_boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "服务器内部错误，请稍后重试", "code": "INTERNAL_ERROR"}
    assert response.headers["content-type"].startswith("application/json")
    assert "seCrEt" not in response.text
    assert "Traceback" not in response.text


def test_method_not_allowed_has_its_own_code(client: TestClient) -> None:
    # 405 不能沿用 NOT_FOUND，否则前端会把它当"接口不存在"排查
    response = client.get("/api/auth/login")

    assert response.status_code == 405
    assert response.json() == {"detail": "接口不支持该请求方法", "code": "METHOD_NOT_ALLOWED"}


def test_docs_closed_when_debug_disabled(client: TestClient) -> None:
    # 默认 DEBUG=false：对外不暴露接口清单
    assert client.get("/api/openapi.json").status_code == 404
    assert client.get("/api/docs").status_code == 404
