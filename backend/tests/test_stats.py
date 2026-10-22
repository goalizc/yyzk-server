"""统计看板：overview / top-faults / missed（契约 §6）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models import Fault, Part, Product, QueryLog, Ticket
from tests.conftest import auth_headers, login, make_line, make_user

NOW = datetime.now(timezone.utc)


def make_product_part(db, model: str = "X1"):
    product = Product(name="智能扫地机器人", model=model, line_id=make_line(db).id)
    db.add(product)
    db.commit()
    db.refresh(product)
    part = Part(product_id=product.id, name="水箱模组")
    db.add(part)
    db.commit()
    db.refresh(part)
    return product, part


def add_log(
    db,
    *,
    hit: bool,
    product=None,
    part=None,
    fault=None,
    resolved: bool | None = None,
    raw_query: str | None = None,
    days_ago: float = 0,
) -> QueryLog:
    log = QueryLog(
        product_id=product.id if product else None,
        part_id=part.id if part else None,
        fault_id=fault.id if fault else None,
        hit=hit,
        resolved=resolved,
        raw_query=raw_query,
        created_at=NOW - timedelta(days=days_ago),
        ip="127.0.0.1",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def add_ticket(db, *, status: str = "open", days_ago: float = 0, seq: int = 1) -> Ticket:
    ticket = Ticket(
        ticket_no=f"TK20261020{seq:04d}",
        contact="13800138000",
        description="统计用",
        need_on_site=False,
        status=status,
        created_at=NOW - timedelta(days=days_ago),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def admin_headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/stats/overview",
        "/api/admin/stats/top-faults",
        "/api/admin/stats/missed",
    ],
)
def test_stats_require_token(client: TestClient, db, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_EXPIRED"


# ---------------------------------------------------------------- overview


def test_overview_empty_database(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    body = client.get("/api/admin/stats/overview", headers=headers).json()

    assert body == {
        "period_days": 30,
        "total_queries": 0,
        "view_queries": 0,
        "resolved_queries": 0,
        "resolve_rate": None,  # 分母为 0
        "total_tickets": 0,
        "open_tickets": 0,
        "missed_queries": 0,
    }


def test_overview_counts_and_resolve_rate(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product, part = make_product_part(db)
    fault = Fault(product_id=product.id, part_id=part.id, title="漏水")
    db.add(fault)
    db.commit()

    add_log(db, hit=True, product=product, part=part, fault=fault, resolved=True)
    add_log(db, hit=True, product=product, part=part, fault=fault, resolved=True)
    add_log(db, hit=True, product=product, part=part, fault=fault, resolved=False)
    add_log(db, hit=False, product=product, part=part, raw_query="异响")
    add_log(db, hit=False, product=product, part=part, raw_query=None)

    add_ticket(db, status="open", seq=1)
    add_ticket(db, status="closed", seq=2)
    add_ticket(db, status="processing", days_ago=40, seq=3)  # 窗口外，但仍是当前积压

    body = client.get("/api/admin/stats/overview", headers=headers).json()

    assert body["total_queries"] == 5
    assert body["view_queries"] == 3
    assert body["resolved_queries"] == 2
    assert body["resolve_rate"] == 0.667
    assert body["missed_queries"] == 2
    assert body["total_tickets"] == 2
    # open_tickets 不随窗口变化：窗口外的 processing 也算当前积压
    assert body["open_tickets"] == 2


def test_overview_window_and_days_zero(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product, part = make_product_part(db)
    add_log(db, hit=True, product=product, part=part, resolved=True)
    add_log(db, hit=True, product=product, part=part, days_ago=40)

    month = client.get("/api/admin/stats/overview?days=30", headers=headers).json()
    assert month["total_queries"] == 1

    everything = client.get("/api/admin/stats/overview?days=0", headers=headers).json()
    assert everything["total_queries"] == 2
    assert everything["period_days"] == 0  # 0 表示全部


def test_overview_rejects_out_of_range_days(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    assert client.get("/api/admin/stats/overview?days=366", headers=headers).status_code == 422


# ---------------------------------------------------------------- top-faults


def test_top_faults_orders_by_period_views(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product, part = make_product_part(db)
    hot = Fault(product_id=product.id, part_id=part.id, title="人多看的", view_count=10, resolved_count=5)
    cold = Fault(product_id=product.id, part_id=part.id, title="少人看的", view_count=999, resolved_count=1)
    db.add_all([hot, cold])
    db.commit()

    for _ in range(3):
        add_log(db, hit=True, product=product, part=part, fault=hot)
    add_log(db, hit=True, product=product, part=part, fault=cold)

    body = client.get("/api/admin/stats/top-faults", headers=headers).json()

    assert [item["title"] for item in body] == ["人多看的", "少人看的"]
    assert body[0]["period_views"] == 3
    assert body[0]["view_count"] == 10  # 历史累计值照旧返回
    assert body[1]["view_count"] == 999  # 排序不看它，只看 period_views
    assert body[0]["product_name"] == product.name
    assert body[0]["part_name"] == part.name


def test_top_faults_respects_window_and_limit(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product, part = make_product_part(db)
    old = Fault(product_id=product.id, part_id=part.id, title="窗口外")
    new = Fault(product_id=product.id, part_id=part.id, title="窗口内")
    db.add_all([old, new])
    db.commit()

    for _ in range(5):
        add_log(db, hit=True, product=product, part=part, fault=old, days_ago=40)
    add_log(db, hit=True, product=product, part=part, fault=new)

    window = client.get("/api/admin/stats/top-faults?days=30", headers=headers).json()
    assert [item["title"] for item in window] == ["窗口内"]

    limited = client.get("/api/admin/stats/top-faults?days=0&limit=1", headers=headers).json()
    assert len(limited) == 1
    assert limited[0]["title"] == "窗口外"  # 全部时间下它 period_views 最多


# ---------------------------------------------------------------- missed


def test_missed_groups_normalized_queries(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product, part = make_product_part(db)

    add_log(db, hit=False, product=product, part=part, raw_query="  漏水 ")
    add_log(db, hit=False, product=product, part=part, raw_query="漏水")
    add_log(db, hit=False, product=product, part=part, raw_query="LEAK")
    add_log(db, hit=False, product=product, part=part, raw_query="leak")
    add_log(db, hit=False, product=product, part=part, raw_query=None)
    add_log(db, hit=False, product=product, part=part, raw_query="   ")

    body = client.get("/api/admin/stats/missed", headers=headers).json()

    by_key = {item["raw_query"]: item["count"] for item in body}
    assert by_key["漏水"] == 2  # 去首尾空格后合并
    assert by_key["leak"] == 2  # 转小写后合并
    assert by_key["(未输入关键词)"] == 2  # null 与空白都归这一桶
    assert body[0]["raw_query"] == "漏水" or body[0]["count"] == 2
    assert set(body[0]) == {
        "raw_query", "count", "sample_product_name", "sample_part_name", "last_seen_at",
    }
    assert body[0]["sample_product_name"] == product.name
    assert body[0]["sample_part_name"] == part.name
    assert body[0]["last_seen_at"].endswith("+08:00")


def test_missed_excludes_hits_and_respects_limit(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product, part = make_product_part(db)
    fault = Fault(product_id=product.id, part_id=part.id, title="漏水")
    db.add(fault)
    db.commit()

    add_log(db, hit=True, product=product, part=part, fault=fault, resolved=True)
    for word in ("甲", "乙", "丙"):
        add_log(db, hit=False, product=product, part=part, raw_query=word)

    body = client.get("/api/admin/stats/missed?limit=2", headers=headers).json()

    assert len(body) == 2
    assert {item["raw_query"] for item in body} <= {"甲", "乙", "丙"}
