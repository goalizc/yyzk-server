"""工单：提交、列表、详情、状态流转（契约 §5）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Fault, Part, Product, Ticket, TicketStatusLog
from tests.conftest import auth_headers, login, make_user

TZ = timezone(timedelta(hours=8))


def make_product(db, name: str = "智能扫地机器人", model: str = "X1") -> Product:
    product = Product(name=name, model=model)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_part(db, product: Product) -> Part:
    part = Part(product_id=product.id, name="电源模组")
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def make_fault(db, product: Product, part: Part) -> Fault:
    fault = Fault(product_id=product.id, part_id=part.id, title="开机无反应")
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return fault


def admin_headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


def submit_ticket(client: TestClient, **overrides) -> dict:
    body = {
        "contact": "13800138000",
        "contact_name": "张先生",
        "description": "按步骤试了还是不行，电池刚换过",
        "need_on_site": True,
    }
    body.update(overrides)
    response = client.post("/api/tickets", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_ticket(
    db,
    *,
    status: str = "open",
    created_at: datetime | None = None,
    seq: int | None = None,
    assignee_id: int | None = None,
) -> Ticket:
    if seq is None:
        seq = (db.scalar(select(func.count(Ticket.id))) or 0) + 1
    ticket = Ticket(
        ticket_no=f"TK20261020{seq:04d}",
        contact="13800138000",
        contact_name="张先生",
        description="按步骤试了还是不行",
        need_on_site=False,
        status=status,
        assignee_id=assignee_id,
    )
    if created_at is not None:
        ticket.created_at = created_at
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


# ---------------------------------------------------------------- 提交


def test_submit_ticket_generates_daily_sequence(client: TestClient, db) -> None:
    first = submit_ticket(client)
    second = submit_ticket(client)

    assert first["ticket_no"].startswith("TK")
    assert len(first["ticket_no"]) == 14
    assert first["ticket_no"].endswith("0001")
    assert second["ticket_no"].endswith("0002")
    assert first["created_at"].endswith("+08:00")

    logs = db.scalars(select(TicketStatusLog)).all()
    assert len(logs) == 2  # 每单一条首日志
    assert logs[0].from_status is None
    assert logs[0].to_status == "open"
    assert logs[0].operator_id is None


def test_submit_ticket_with_optional_context(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)

    body = submit_ticket(
        client, product_id=product.id, part_id=part.id, fault_id=fault.id
    )
    assert body["ticket_no"]

    ticket = db.scalar(select(Ticket))
    assert ticket.product_id == product.id
    assert ticket.fault_id == fault.id


def test_submit_ticket_requires_contact(client: TestClient, db) -> None:
    response = client.post(
        "/api/tickets",
        json={"contact": "123", "description": "描述至少五个字", "need_on_site": False},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "请填写联系方式", "code": "VALIDATION_ERROR"}


def test_submit_ticket_requires_description(client: TestClient, db) -> None:
    response = client.post(
        "/api/tickets",
        json={"contact": "13800138000", "description": "短", "need_on_site": False},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- 列表


def test_admin_ticket_list_requires_token(client: TestClient, db) -> None:
    response = client.get("/api/admin/tickets")

    assert response.status_code == 401


def test_admin_ticket_list_masks_contact_and_paginates(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    submit_ticket(client)
    submit_ticket(client, contact="zhangsan@example.com")

    response = client.get("/api/admin/tickets?page=1&page_size=1", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert "****" in item["contact"]
    assert item["contact"] != "13800138000"
    assert set(item) >= {
        "id", "ticket_no", "product_name", "product_model", "part_name", "fault_title",
        "contact", "contact_name", "need_on_site", "status", "assignee_name",
        "created_at", "updated_at",
    }


def test_admin_ticket_list_filters_status_and_date(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    # 写库统一用 UTC：SQLite 不存时区，用 UTC 才与 PostgreSQL 归一化后的行为一致
    today = datetime(2026, 10, 20, 23, 59, 59, 500000, tzinfo=TZ).astimezone(timezone.utc)
    make_ticket(db, status="open", created_at=today)
    make_ticket(db, status="closed", created_at=today - timedelta(days=3))

    by_status = client.get("/api/admin/tickets?status=closed", headers=headers).json()
    assert by_status["total"] == 1

    # 结束日期按半开区间处理：23:59:59.5 也必须落在 10-20 当天内
    in_range = client.get(
        "/api/admin/tickets?start_date=2026-10-20&end_date=2026-10-20", headers=headers
    ).json()
    assert in_range["total"] == 1
    assert in_range["items"][0]["created_at"].startswith("2026-10-20")


def test_admin_ticket_list_keyword_matches_no_or_contact(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    body = submit_ticket(client)

    by_no = client.get(f"/api/admin/tickets?keyword={body['ticket_no']}", headers=headers).json()
    assert by_no["total"] == 1

    by_contact = client.get("/api/admin/tickets?keyword=13800138000", headers=headers).json()
    assert by_contact["total"] == 1


# ---------------------------------------------------------------- 详情


def test_ticket_detail_has_full_contact_and_history(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)
    body = submit_ticket(client, product_id=product.id, part_id=part.id, fault_id=fault.id)

    ticket_id = db.scalar(select(Ticket.id))
    response = client.get(f"/api/admin/tickets/{ticket_id}", headers=headers)

    assert response.status_code == 200
    detail = response.json()
    assert detail["contact"] == "13800138000"  # 详情不脱敏
    assert detail["product"] == {"id": product.id, "name": product.name, "model": product.model}
    assert detail["part"] == {"id": part.id, "name": part.name}
    assert detail["fault"]["title"] == fault.title
    assert len(detail["history"]) == 1
    assert detail["history"][0]["to_status"] == "open"
    assert detail["history"][0]["operator_name"] is None
    assert body["ticket_no"] == detail["ticket_no"]


def test_ticket_detail_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.get("/api/admin/tickets/9999", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- 状态流转


def test_status_change_requires_remark(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    submit_ticket(client)
    ticket_id = db.scalar(select(Ticket.id))

    response = client.put(
        f"/api/admin/tickets/{ticket_id}", json={"status": "processing"}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "备注" in response.json()["detail"]


def test_status_change_writes_log_and_assigns_current_user(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    submit_ticket(client)
    ticket_id = db.scalar(select(Ticket.id))

    response = client.put(
        f"/api/admin/tickets/{ticket_id}",
        json={"status": "processing", "remark": "已电话联系用户"},
        headers=headers,
    )

    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "processing"
    assert detail["remark"] == "已电话联系用户"
    assert detail["assignee_name"] == "系统管理员"  # 未传 assignee_id → 当前用户
    assert [h["to_status"] for h in detail["history"]] == ["open", "processing"]
    assert detail["history"][1]["operator_name"] == "系统管理员"
    assert detail["history"][1]["remark"] == "已电话联系用户"


def test_invalid_status_transition_rejected(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    ticket = make_ticket(db, status="resolved")

    response = client.put(
        f"/api/admin/tickets/{ticket.id}",
        json={"status": "open", "remark": "想重开"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "不能从 resolved 直接流转到 open",
        "code": "TICKET_STATUS_INVALID",
    }


def test_closed_is_terminal(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    ticket = make_ticket(db, status="closed")

    response = client.put(
        f"/api/admin/tickets/{ticket.id}",
        json={"status": "processing", "remark": "再处理一下"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "TICKET_STATUS_INVALID"


def test_remark_only_does_not_write_history(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    ticket = make_ticket(db, status="open")

    response = client.put(
        f"/api/admin/tickets/{ticket.id}",
        json={"remark": "客户催过一次", "need_on_site": True},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["remark"] == "客户催过一次"
    assert response.json()["need_on_site"] is True
    assert len(response.json()["history"]) == 0  # 未变更状态不写流转日志


def test_empty_update_rejected(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    ticket = make_ticket(db, status="open")

    response = client.put(f"/api/admin/tickets/{ticket.id}", json={}, headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_update_all_null_rejected(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    ticket = make_ticket(db, status="open")

    response = client.put(
        f"/api/admin/tickets/{ticket.id}",
        json={"status": None, "remark": None},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- 处理人归属（v1.3）


def test_unassigned_ticket_claimed_by_operator(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    ticket = make_ticket(db, status="open")

    response = client.put(
        f"/api/admin/tickets/{ticket.id}", json={"remark": "先登记一下"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["assignee_name"] == "系统管理员"


def test_existing_assignee_is_not_stolen(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    other = make_user(db, username="agent2", real_name="李工")
    ticket = make_ticket(db, status="processing", assignee_id=other.id)

    response = client.put(
        f"/api/admin/tickets/{ticket.id}", json={"remark": "补充说明"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["assignee_id"] == other.id
    assert response.json()["assignee_name"] == "李工"


def test_explicit_transfer_reassigns(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    other = make_user(db, username="agent2", real_name="李工")
    ticket = make_ticket(db, status="processing")

    response = client.put(
        f"/api/admin/tickets/{ticket.id}", json={"assignee_id": other.id}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["assignee_name"] == "李工"
