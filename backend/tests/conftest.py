"""测试夹具：SQLite 内存库 + 依赖覆盖。

生产与集成验证走 deploy/docker-compose.yml 里的真实 PostgreSQL，
这里只验证接口行为与错误码，不验证 PG 专属 DDL。
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 必须在导入 app 之前注入，config.py 在导入时就会校验
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
os.environ["JWT_EXPIRE_HOURS"] = "24"
os.environ["TZ"] = "Asia/Shanghai"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="fault-uploads-")
os.environ["MAX_UPLOAD_MB"] = "20"

from app.core.security import hash_password  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ProductLine, User  # noqa: E402

DEFAULT_PASSWORD = "Admin@12345"
DEFAULT_PASSWORD_HASH = hash_password(DEFAULT_PASSWORD)

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _record) -> None:
    """SQLite 默认不执行外键约束，不打开就测不到 ON DELETE SET NULL / RESTRICT。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _prepare_schema() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _audit_uses_test_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """审计写入用的是独立会话（new_session），默认指向 settings 里的库。

    测试库是 StaticPool 内存库，而 `new_session()` 会新建连接 → 拿到另一个空库，
    审计记录会写失败并被吞掉。这里把审计的会话工厂换成测试引擎，
    否则「审计写入」这类用例会一直假绿。
    """
    import app.services.audit as audit_module

    monkeypatch.setattr(audit_module, "new_session", TestingSession)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSession()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def make_user(
    db: Session,
    username: str = "admin",
    password: str = DEFAULT_PASSWORD,
    *,
    real_name: str = "系统管理员",
    role: str = "super_admin",
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        password_hash=DEFAULT_PASSWORD_HASH if password == DEFAULT_PASSWORD else hash_password(password),
        real_name=real_name,
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, username: str = "admin", password: str = DEFAULT_PASSWORD) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_line(db: Session, name: str = "测试产品线") -> ProductLine:
    line = db.scalar(select(ProductLine).where(ProductLine.name == name))
    if line is None:
        line = ProductLine(name=name)
        db.add(line)
        db.commit()
        db.refresh(line)
    return line
