"""操作审计：写入、筛选、权限、汇总、导出（契约 §6）。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import AuditLog, Fault, Part, Product, Ticket
from tests.conftest import auth_headers, login, make_line, make_user


def make_product(db, model: str = "3WWDZ-16A") -> Product:
    product = Product(name="植保无人机 16L", model=model, line_id=make_line(db).id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_part(db, product: Product, name: str = "隔膜泵") -> Part:
    part = Part(product_id=product.id, name=name)
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def make_fault(db, product: Product, part: Part, title: str = "喷洒不出水") -> Fault:
    fault = Fault(product_id=product.id, part_id=part.id, title=title)
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return fault


def admin_headers(client: TestClient, db) -> dict:
    make_user(db, role="super_admin")
    return auth_headers(login(client)["access_token"])


def audit_rows(db) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id)))


def test_login_success_is_audited(client: TestClient, db) -> None:
    make_user(db, username="kefu01", role="agent")

    login(client, "kefu01")

    rows = audit_rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "auth.login"
    assert row.username == "kefu01"
    assert row.result == "success"
    assert row.status == 200
    assert row.detail["reason"] == "success"
    # 审计要能定位「从哪来」：Nginx 传了 X-Real-IP 就优先用它
    assert row.ip is not None


def test_login_wrong_password_is_audited_with_reason(client: TestClient, db) -> None:
    make_user(db, username="kefu01", role="agent")

    response = client.post(
        "/api/auth/login",
        json={"username": "kefu01", "password": "wrong-password"},
        headers={"X-Real-IP": "203.0.113.9"},
    )

    assert response.status_code == 401
    row = audit_rows(db)[-1]
    assert row.action == "auth.login"
    assert row.result == "failure"
    assert row.error_code == "AUTH_INVALID_CREDENTIALS"
    assert row.detail["reason"] == "wrong_password"
    assert row.ip == "203.0.113.9"


def test_login_unknown_user_is_audited(client: TestClient, db) -> None:
    client.post("/api/auth/login", json={"username": "nobody", "password": "whatever"})

    row = audit_rows(db)[-1]
    assert row.result == "failure"
    assert row.detail["reason"] == "user_not_found"
    # 用户名不存在时也要记下「试的是哪个名字」，否则撞库行为看不出来
    assert row.username == "nobody"


def test_create_fault_is_audited_with_target(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    response = client.post(
        "/api/admin/faults",
        json={"product_id": product.id, "part_id": part.id, "title": "喷头堵塞"},
        headers=headers,
    )

    assert response.status_code in (200, 201)
    created_id = response.json()["id"]
    row = audit_rows(db)[-1]
    assert row.action == "fault.create"
    assert row.target_type == "fault"
    assert row.target_id == str(created_id)
    assert row.target_name == "喷头堵塞"


def test_ticket_update_records_status_transition(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part)
    ticket = Ticket(
        ticket_no="TK202610260001",
        product_id=product.id,
        part_id=part.id,
        fault_id=fault.id,
        contact="13800000000",
        description="喷头不出水，已按方案排查未解决",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    response = client.put(
        f"/api/admin/tickets/{ticket.id}",
        json={"status": "processing", "remark": "已电话指导清理滤网"},
        headers=headers,
    )

    assert response.status_code == 200
    row = audit_rows(db)[-1]
    assert row.action == "ticket.update"
    assert row.target_name == "TK202610260001"
    assert row.detail["from_status"] == "open"
    assert row.detail["to_status"] == "processing"


def test_failed_write_is_audited_as_failure(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.post("/api/admin/faults", json={"product_id": 9999, "part_id": 9999}, headers=headers)

    assert response.status_code in (400, 404, 422)
    row = audit_rows(db)[-1]
    assert row.action == "fault.create"
    assert row.result == "failure"
    assert row.error_code  # 失败原因必须可查


def test_agent_cannot_read_audit_logs(client: TestClient, db) -> None:
    make_user(db, username="kefu01", role="agent")
    token = login(client, "kefu01")["access_token"]

    response = client.get("/api/admin/audit-logs", headers=auth_headers(token))

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_auditor_role_can_read_audit_logs(client: TestClient, db) -> None:
    make_user(db, username="shenji", role="auditor")
    token = login(client, "shenji")["access_token"]

    response = client.get("/api/admin/audit-logs", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["total"] >= 1  # 至少包含它自己的这次登录


def test_list_filters_by_action_and_result(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    client.post(
        "/api/admin/faults",
        json={"product_id": product.id, "part_id": part.id, "title": "桨叶裂纹"},
        headers=headers,
    )
    client.post("/api/admin/faults", json={"product_id": 9999, "part_id": 9999}, headers=headers)

    only_create = client.get("/api/admin/audit-logs?action=fault.create", headers=headers).json()
    assert only_create["total"] == 2

    only_failed = client.get(
        "/api/admin/audit-logs?action=fault.create&result=failure", headers=headers
    ).json()
    assert only_failed["total"] == 1
    assert only_failed["items"][0]["result"] == "failure"

    only_login = client.get("/api/admin/audit-logs?action=auth.login", headers=headers).json()
    assert only_login["total"] == 1
    assert only_login["items"][0]["action"] == "auth.login"


def test_list_supports_keyword_and_target_filters(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    created = client.post(
        "/api/admin/faults",
        json={"product_id": product.id, "part_id": part.id, "title": "RTK 无法固定"},
        headers=headers,
    ).json()

    by_keyword = client.get("/api/admin/audit-logs?keyword=RTK", headers=headers).json()
    assert by_keyword["total"] == 1

    by_target = client.get(
        f"/api/admin/audit-logs?target_type=fault&target_id={created['id']}", headers=headers
    ).json()
    assert by_target["total"] == 1

    missing = client.get("/api/admin/audit-logs?target_id=99999999", headers=headers).json()
    assert missing["total"] == 0


def test_detail_returns_change_payload(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    log_id = client.get("/api/admin/audit-logs?action=auth.login", headers=headers).json()["items"][0]["id"]

    response = client.get(f"/api/admin/audit-logs/{log_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin"
    assert body["detail"]["reason"] == "success"
    assert "user_agent" in body


def test_detail_not_found(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.get("/api/admin/audit-logs/999999", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_summary_aggregates_by_actor(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    for title in ("喷头堵塞", "桨叶裂纹"):
        client.post(
            "/api/admin/faults",
            json={"product_id": product.id, "part_id": part.id, "title": title},
            headers=headers,
        )

    body = client.get("/api/admin/audit-logs/summary?days=7", headers=headers).json()

    assert body["period_days"] == 7
    actor = next(item for item in body["actors"] if item["username"] == "admin")
    assert actor["total"] >= 3  # 1 次登录 + 2 次建故障
    assert actor["failures"] == 0
    assert actor["distinct_ips"] >= 1


def test_export_returns_csv_with_bom(client: TestClient, db) -> None:
    headers = admin_headers(client, db)

    response = client.get("/api/admin/audit-logs/export", headers=headers)

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    # Excel 双击打开中文不乱码靠这个 BOM
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "账号" in response.content.decode("utf-8")


def test_audit_keeps_target_name_after_target_deleted(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    target = make_user(db, username="kefu02", role="agent")

    client.post(f"/api/admin/users/{target.id}/reset-password", headers=headers)
    db.delete(target)
    db.commit()

    row = audit_rows(db)[-1]
    assert row.action == "user.reset_password"
    # user_id 是操作人（admin），被操作的人记在 target_* 上
    assert row.username == "admin"
    assert row.target_id == str(target.id)
    # 对象已被删除，但冗余的名字仍能指认出「重置的是谁」
    assert row.target_name == "kefu02"


def test_audit_user_id_becomes_null_when_actor_deleted(client: TestClient, db) -> None:
    admin = make_user(db, username="wangguan", role="super_admin")
    login(client, "wangguan")

    db.delete(admin)
    db.commit()

    row = audit_rows(db)[-1]
    assert row.action == "auth.login"
    # 外键 ON DELETE SET NULL：账号没了，但用户名这层冗余还在，历史仍可追
    assert row.user_id is None
    assert row.username == "wangguan"


def test_fault_update_records_title_change(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part, title="旧标题")

    client.put(f"/api/admin/faults/{fault.id}", json={"title": "新标题"}, headers=headers)

    row = audit_rows(db)[-1]
    assert row.action == "fault.update"
    assert row.detail["title_from"] == "旧标题"
    assert row.detail["title_to"] == "新标题"


def test_fault_delete_keeps_name_of_deleted_row(client: TestClient, db) -> None:
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)
    fault = make_fault(db, product, part, title="待删除的故障")

    client.delete(f"/api/admin/faults/{fault.id}", headers=headers)

    row = audit_rows(db)[-1]
    assert row.action == "fault.delete"
    # 对象已删，target_name 只能靠删除前记下来的那份
    assert row.target_name == "待删除的故障"
    assert row.target_id == str(fault.id)


def test_audit_build_failure_does_not_break_business(client: TestClient, db, monkeypatch) -> None:
    """审计构建抛异常时，业务必须照常成功——审计只是旁观者（审查报告 P1-2）。"""
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    import app.core.audit as audit_core

    monkeypatch.setattr(
        audit_core, "_build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("build boom"))
    )

    response = client.post(
        "/api/admin/faults",
        json={"product_id": product.id, "part_id": part.id, "title": "审计挂了业务也要成"},
        headers=headers,
    )

    assert response.status_code in (200, 201)
    db.expire_all()
    assert db.scalar(select(Fault).where(Fault.title == "审计挂了业务也要成")) is not None


def test_unhandled_exception_records_error_class(client: TestClient, db, monkeypatch) -> None:
    """未捕获异常的审计要能看出异常类型（handler 在中间件外层，error_code 拿不到）。"""
    headers = admin_headers(client, db)
    product = make_product(db)
    part = make_part(db, product)

    import app.api.admin_faults as faults_api

    monkeypatch.setattr(
        faults_api, "_ensure_product_part", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    app.dependency_overrides[get_db] = lambda: db
    raw = TestClient(app, raise_server_exceptions=False)
    response = raw.post(
        "/api/admin/faults",
        json={"product_id": product.id, "part_id": part.id, "title": "触发 500"},
        headers=headers,
    )

    assert response.status_code == 500
    row = audit_rows(db)[-1]
    assert row.status == 500
    assert row.detail.get("error_class") == "RuntimeError"


def test_export_escapes_spreadsheet_formulas(client: TestClient, db) -> None:
    """导出 CSV 必须挡掉 Excel 公式注入（审查报告 P1-1）。"""
    headers = admin_headers(client, db)
    db.add(
        AuditLog(
            username="admin",
            action="fault.create",
            target_type="fault",
            target_id="1",
            target_name='=HYPERLINK("http://evil.example","click")',
            method="POST",
            path="/api/admin/faults",
            status=200,
            result="success",
            detail={},
        )
    )
    db.commit()

    response = client.get("/api/admin/audit-logs/export", headers=headers)
    text = response.content.decode("utf-8")
    line = next(row for row in text.splitlines() if "HYPERLINK" in row)

    # 前置单引号后 Excel 会当纯文本
    assert "'=HYPERLINK" in line


def test_export_itself_is_audited(client: TestClient, db) -> None:
    """导出审计记录本身要留痕（meta-audit，审查报告 P1-4）。"""
    headers = admin_headers(client, db)

    client.get("/api/admin/audit-logs/export", headers=headers)

    row = audit_rows(db)[-1]
    assert row.action == "audit.export"
    assert row.result == "success"


def test_login_failure_marks_identity_unverified(client: TestClient, db) -> None:
    """登录失败时用户名来自输入、未经验证，必须标记出来（审查报告 P1-6）。"""
    make_user(db, username="kefu01", role="agent")

    client.post("/api/auth/login", json={"username": "kefu01", "password": "wrong"})

    row = audit_rows(db)[-1]
    assert row.detail["reason"] == "wrong_password"
    assert row.detail["identity_verified"] is False

    client.post("/api/auth/login", json={"username": "kefu01", "password": "Admin@12345"})
    ok_row = audit_rows(db)[-1]
    assert ok_row.detail["identity_verified"] is True
