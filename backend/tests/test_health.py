"""健康检查：只查 DB 连通性，失败返回 503 且不暴露堆栈。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_returns_503_when_db_down(db) -> None:
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

        def close(self) -> None:
            pass

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "数据库不可用", "code": "SERVICE_UNAVAILABLE"}
    assert "Traceback" not in response.text


def test_request_id_header_present(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.headers.get("X-Request-ID")


def test_unknown_path_uses_error_body(client: TestClient) -> None:
    response = client.get("/api/not-exists")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["detail"] == "接口不存在"
