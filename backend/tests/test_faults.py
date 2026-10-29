"""故障知识库：公开列表/详情/反馈/日志上报 + 后台 CRUD（契约 §4）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Fault, Part, Product, QueryLog, Ticket
from tests.conftest import auth_headers, login, make_line, make_user


def make_product(db, name: str = "智能扫地机器人", model: str = "X1") -> Product:
    product = Product(name=name, model=model, line_id=make_line(db).id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_part(db, product: Product, name: str = "电源模组", **kwargs) -> Part:
    part = Part(product_id=product.id, name=name, **kwargs)
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def make_fault(
    db,
    product: Product,
    part: Part,
    title: str = "开机无反应",
    *,
    symptom: str = "按开机键后设备完全无响应",
    is_published: bool = True,
    view_count: int = 0,
    resolved_count: int = 0,
    attachment_urls: list | None = None,
) -> Fault:
    fault = Fault(
        product_id=product.id,
        part_id=part.id,
        title=title,
        symptom=symptom,
        root_cause="电源适配器损坏",
        solution_steps=[{"step": 1, "text": "检查电源", "image_url": None}],
        required_tools="无",
        is_published=is_published,
        view_count=view_count,
        resolved_count=resolved_count,
        attachment_urls=attachment_urls or [],
    )
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return fault


def admin_headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


# ---------------------------------------------------------------- 公开列表


def test_public_faults_only_published_sorted_by_view_count(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    make_fault(db, product, part, title="少人看", view_count=5)
    make_fault(db, product, part, title="多人看", view_count=50)
    make_fault(db, product, part, title="未发布", view_count=999, is_published=False)

    response = client.get(f"/api/faults?product_id={product.id}&part_id={part.id}")

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body] == ["多人看", "少人看"]
    assert set(body[0]) == {"id", "title", "symptom", "view_count", "part_name"}
    assert body[0]["part_name"] == part.name


def test_public_faults_keyword_matches_title_and_symptom(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    make_fault(db, product, part, title="开机无反应", symptom="指示灯不亮")
    make_fault(db, product, part, title="噪音大", symptom="滚刷异响")

    by_title = client.get(f"/api/faults?product_id={product.id}&part_id={part.id}&q=开机").json()
    assert [item["title"] for item in by_title] == ["开机无反应"]

    by_symptom = client.get(f"/api/faults?product_id={product.id}&part_id={part.id}&q=异响").json()
    assert [item["title"] for item in by_symptom] == ["噪音大"]


def test_public_faults_empty_result_is_empty_array(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)

    response = client.get(f"/api/faults?product_id={product.id}&part_id={part.id}")

    assert response.status_code == 200
    assert response.json() == []


def test_public_faults_requires_product(client: TestClient, db) -> None:
    response = client.get("/api/faults")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_public_faults_part_optional_returns_all(client: TestClient, db) -> None:
    """零件降级为可选过滤器（v1.6）：不传 part_id 应返回该产品下全部故障。"""
    product = make_product(db)
    part_a = make_part(db, product, name="隔膜泵")
    part_b = make_part(db, product, name="喷头")
    make_fault(db, product, part_a, title="泵不出水", view_count=10)
    make_fault(db, product, part_b, title="喷头堵塞", view_count=20)

    response = client.get(f"/api/faults?product_id={product.id}")

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body] == ["喷头堵塞", "泵不出水"]
    assert {item["part_name"] for item in body} == {"隔膜泵", "喷头"}

    # 传 part_id 时仍是过滤器语义
    filtered = client.get(f"/api/faults?product_id={product.id}&part_id={part_a.id}").json()
    assert [item["title"] for item in filtered] == ["泵不出水"]


# ---------------------------------------------------------------- 公开详情


def test_fault_detail_has_side_effects(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part, view_count=10)

    response = client.get(f"/api/faults/{fault.id}?q=开机")

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == product.name
    assert body["part_name"] == part.name
    assert body["solution_steps"][0]["step"] == 1
    assert body["view_count"] == 11  # 自增后的值
    assert body["query_log_id"]

    log = db.scalar(select(QueryLog).where(QueryLog.id == body["query_log_id"]))
    assert log is not None
    assert log.hit is True
    assert log.fault_id == fault.id
    assert log.raw_query == "开机"
    assert log.ip  # 服务端补的客户端 IP

    db.expire_all()
    assert db.get(Fault, fault.id).view_count == 11


def test_fault_detail_hidden_for_unpublished(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part, is_published=False)

    response = client.get(f"/api/faults/{fault.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "故障不存在", "code": "NOT_FOUND"}


def test_fault_detail_not_found(client: TestClient, db) -> None:
    response = client.get("/api/faults/9999")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- 反馈


def _open_detail(client: TestClient, fault: Fault) -> int:
    return client.get(f"/api/faults/{fault.id}").json()["query_log_id"]


def test_feedback_resolved_increments_count(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)
    log_id = _open_detail(client, fault)

    response = client.post(
        f"/api/faults/{fault.id}/feedback", json={"query_log_id": log_id, "resolved": True}
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "感谢反馈"}
    db.expire_all()
    assert db.get(Fault, fault.id).resolved_count == 1
    assert db.get(QueryLog, log_id).resolved is True


def test_feedback_is_idempotent(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)
    log_id = _open_detail(client, fault)

    for _ in range(3):
        response = client.post(
            f"/api/faults/{fault.id}/feedback", json={"query_log_id": log_id, "resolved": True}
        )
        assert response.status_code == 200

    db.expire_all()
    assert db.get(Fault, fault.id).resolved_count == 1  # 只加一次


def test_feedback_flip_to_false_decrements_with_floor(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)
    log_id = _open_detail(client, fault)

    client.post(f"/api/faults/{fault.id}/feedback", json={"query_log_id": log_id, "resolved": True})
    client.post(f"/api/faults/{fault.id}/feedback", json={"query_log_id": log_id, "resolved": False})

    db.expire_all()
    assert db.get(Fault, fault.id).resolved_count == 0

    # 再点一次 false：状态未变，不减到负数
    client.post(f"/api/faults/{fault.id}/feedback", json={"query_log_id": log_id, "resolved": False})
    db.expire_all()
    assert db.get(Fault, fault.id).resolved_count == 0


def test_feedback_rejects_mismatched_log(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    first = make_fault(db, product, part, title="故障一")
    second = make_fault(db, product, part, title="故障二")
    log_id = _open_detail(client, first)

    response = client.post(
        f"/api/faults/{second.id}/feedback", json={"query_log_id": log_id, "resolved": True}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "QUERY_LOG_MISMATCH"


def test_feedback_rejects_unknown_log(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)

    response = client.post(
        f"/api/faults/{fault.id}/feedback", json={"query_log_id": 999999, "resolved": True}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "QUERY_LOG_MISMATCH"


# ---------------------------------------------------------------- 日志上报


def test_query_log_records_miss_with_client_info(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/query-logs",
        json={"product_id": product.id, "part_id": part.id, "raw_query": "  漏水  "},
        headers={"User-Agent": "U" * 300},
    )

    assert response.status_code == 201
    log = db.scalar(select(QueryLog).where(QueryLog.id == response.json()["id"]))
    assert log.hit is False
    assert log.fault_id is None
    assert log.raw_query == "漏水"  # 去首尾空格
    assert log.ip
    assert len(log.user_agent) == 200  # 截断


def test_query_log_allows_null_raw_query(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/query-logs", json={"product_id": product.id, "part_id": part.id, "raw_query": None}
    )

    assert response.status_code == 201
    log = db.scalar(select(QueryLog).where(QueryLog.id == response.json()["id"]))
    assert log.raw_query is None


def test_query_log_rejects_overlong_raw_query(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/query-logs",
        json={"product_id": product.id, "part_id": part.id, "raw_query": "长" * 101},
    )

    assert response.status_code == 422


def test_query_log_allows_null_part_id(client: TestClient, db) -> None:
    """零件可选（v1.6）：用户没选零件也能上报未命中，part_id 落库为 NULL。"""
    product = make_product(db)

    response = client.post(
        "/api/query-logs",
        json={"product_id": product.id, "raw_query": "漏水"},
    )

    assert response.status_code == 201
    log = db.scalar(select(QueryLog).where(QueryLog.id == response.json()["id"]))
    assert log.part_id is None
    assert log.product_id == product.id
    assert log.raw_query == "漏水"


def test_query_log_rejects_unknown_product_even_without_part(client: TestClient, db) -> None:
    response = client.post("/api/query-logs", json={"product_id": 9999, "raw_query": "漏水"})

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- 后台


def test_admin_faults_requires_token(client: TestClient, db) -> None:
    response = client.get("/api/admin/faults")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_EXPIRED"


def test_admin_fault_list_without_solution_steps(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part, attachment_urls=[{"name": "a.pdf", "url": "/uploads/a.pdf", "size": 1}])

    response = client.get(f"/api/admin/faults?product_id={product.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert "solution_steps" not in item
    assert item["product_name"] == product.name
    assert item["part_name"] == part.name
    assert item["attachment_count"] == 1
    assert item["id"] == fault.id
    assert item["created_at"].endswith("+08:00")


def test_admin_fault_list_filters(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    other_product = make_product(db, name="净化器", model="A2")
    part = make_part(db, product)
    make_fault(db, product, part, title="开机无反应")
    make_fault(db, product, part, title="噪音大", is_published=False)
    other_part = make_part(db, other_product, name="滤芯")
    make_fault(db, other_product, other_part, title="滤芯堵塞")

    by_product = client.get(f"/api/admin/faults?product_id={product.id}", headers=headers).json()
    assert by_product["total"] == 2

    by_unpublished = client.get(
        f"/api/admin/faults?product_id={product.id}&is_published=false", headers=headers
    ).json()
    assert by_unpublished["total"] == 1
    assert by_unpublished["items"][0]["title"] == "噪音大"

    by_keyword = client.get("/api/admin/faults?keyword=滤芯", headers=headers).json()
    assert by_keyword["total"] == 1


def test_admin_fault_detail_has_no_side_effects(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)

    response = client.get(f"/api/admin/faults/{fault.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert "query_log_id" not in body
    assert body["solution_steps"]
    assert body["product_name"] == product.name
    assert body["part_name"] == part.name
    assert body["created_by"] is None or isinstance(body["created_by"], int)

    db.expire_all()
    assert db.get(Fault, fault.id).view_count == 0  # 后台回显不自增
    assert db.scalar(select(QueryLog).where(QueryLog.fault_id == fault.id)) is None


def test_create_fault_normalizes_steps_and_sets_author(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/admin/faults",
        json={
            "product_id": product.id,
            "part_id": part.id,
            "title": "开机无反应",
            "symptom": "指示灯不亮",
            "solution_steps": [
                {"step": 2, "text": "第二步"},
                {"step": 1, "text": "第一步"},
                {"step": 1, "text": "重复的第一步"},
            ],
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert [step["step"] for step in body["solution_steps"]] == [1, 2]
    assert body["created_by"] == 1
    assert body["is_published"] is True


def test_create_fault_part_product_mismatch(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    other = make_product(db, name="净化器", model="A2")
    foreign_part = make_part(db, other, name="滤芯")

    response = client.post(
        "/api/admin/faults",
        json={"product_id": product.id, "part_id": foreign_part.id, "title": "错配"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PART_PRODUCT_MISMATCH"


def test_create_fault_product_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.post(
        "/api/admin/faults", json={"product_id": 9999, "part_id": 9999, "title": "x"}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_update_fault_replaces_steps(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)

    response = client.put(
        f"/api/admin/faults/{fault.id}",
        json={"title": "新标题", "solution_steps": [{"step": 1, "text": "只保留这一步"}]},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "新标题"
    assert len(body["solution_steps"]) == 1


def test_update_fault_validates_part_product_relation(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    other = make_product(db, name="净化器", model="A2")
    part = make_part(db, product)
    foreign_part = make_part(db, other, name="滤芯")
    fault = make_fault(db, product, part)

    response = client.put(
        f"/api/admin/faults/{fault.id}", json={"part_id": foreign_part.id}, headers=headers
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PART_PRODUCT_MISMATCH"


def test_delete_fault_keeps_ticket_but_nulls_reference(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)
    ticket = Ticket(
        ticket_no="TK202610200009",
        product_id=product.id,
        part_id=part.id,
        fault_id=fault.id,
        contact="13800138000",
        description="客户反馈开机无反应，已按方案排查未解决",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    response = client.delete(f"/api/admin/faults/{fault.id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"success": True}
    db.expire_all()
    assert db.get(Fault, fault.id) is None
    kept = db.get(Ticket, ticket.id)
    assert kept is not None
    assert kept.fault_id is None  # 工单保留，引用置空


def test_delete_fault_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.delete("/api/admin/faults/9999", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- 审查后补的回归


def test_create_fault_rejects_unsafe_attachment_url(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/admin/faults",
        json={
            "product_id": product.id,
            "part_id": part.id,
            "title": "XSS 附件",
            "attachment_urls": [{"name": "x.pdf", "url": "javascript:alert(1)", "size": 1}],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "地址" in response.json()["detail"]


def test_create_fault_rejects_unsafe_step_image(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/admin/faults",
        json={
            "product_id": product.id,
            "part_id": part.id,
            "title": "XSS 配图",
            "solution_steps": [
                {"step": 1, "text": "点我", "image_url": "data:text/html;base64,PHNjcmlwdD4="}
            ],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "地址" in response.json()["detail"]


def test_create_fault_accepts_uploads_attachment(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/admin/faults",
        json={
            "product_id": product.id,
            "part_id": part.id,
            "title": "正常附件",
            "solution_steps": [
                {"step": 1, "text": "看图", "image_url": "/uploads/20261020-a1b2c3d4.jpg"}
            ],
            "attachment_urls": [{"name": "手册.pdf", "url": "/uploads/20261020-deadbeef.pdf", "size": 1024}],
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["attachment_urls"][0]["url"].startswith("/uploads/")


def test_public_faults_q_too_long(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)

    response = client.get(
        f"/api/faults?product_id={product.id}&part_id={part.id}&q={'长' * 51}"
    )

    assert response.status_code == 422


def test_fault_detail_q_too_long(client: TestClient, db) -> None:
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)

    response = client.get(f"/api/faults/{fault.id}?q={'长' * 101}")

    assert response.status_code == 422


def test_missing_fault_does_not_write_log(client: TestClient, db) -> None:
    client.get("/api/faults/9999")

    assert db.scalar(select(QueryLog).where(QueryLog.hit.is_(True))) is None


def test_query_log_rejects_part_product_mismatch(client: TestClient, db) -> None:
    product = make_product(db)
    other = make_product(db, name="净化器", model="A2")
    foreign_part = make_part(db, other, name="滤芯")

    response = client.post(
        "/api/query-logs",
        json={"product_id": product.id, "part_id": foreign_part.id, "raw_query": "漏水"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PART_PRODUCT_MISMATCH"
