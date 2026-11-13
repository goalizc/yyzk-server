"""进销存审计规则验收（PRD 任务卡 #5 / §9）。

文件名带 `inventory_` 前缀防 pytest 重名静默覆盖。
- 纯函数组：验证 `_RULES` / `_NAME_FIELDS` 登记正确、读路径不产生噪声；
- 端点组：验证命中规则的写操作与导出确实落到 audit_logs（含 403 失败留痕）。

PG 专属的行锁 / append-only 触发器留任务卡 #9 真机验证。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditLog, InventoryWarehouse
from app.services.audit import _lookup_target_name, known_actions, resolve
from tests.conftest import auth_headers, login, make_user

BASE = "/api/admin/inventory"

# (method, path, action, target_type, target_id) —— 与 PRD §9 的 11 行规则一一对应
_RULES_CASES = [
    ("POST", f"{BASE}/skus", "inventory.sku.create", "inventory_sku", None),
    ("PUT", f"{BASE}/skus/7", "inventory.sku.update", "inventory_sku", "7"),
    ("DELETE", f"{BASE}/skus/7", "inventory.sku.disable", "inventory_sku", "7"),
    ("POST", f"{BASE}/categories", "inventory.category.create", "inventory_category", None),
    ("PUT", f"{BASE}/categories/3", "inventory.category.update", "inventory_category", "3"),
    ("POST", f"{BASE}/inbound-orders", "inventory.inbound.create", "inventory_document", None),
    ("POST", f"{BASE}/outbound-orders", "inventory.outbound.create", "inventory_document", None),
    ("POST", f"{BASE}/adjustments", "inventory.adjust.create", "inventory_document", None),
    ("POST", f"{BASE}/documents/12/reverse", "inventory.document.reverse", "inventory_document", "12"),
    ("PUT", f"{BASE}/documents/12", "inventory.document.edit", "inventory_document", "12"),
    ("GET", f"{BASE}/export", "inventory.export", "inventory", None),
]


# ---------------------------------------------------------------- 辅助


def inv_headers(client: TestClient, db) -> dict:
    make_user(db)
    return auth_headers(login(client)["access_token"])


def inv_warehouse(db) -> InventoryWarehouse:
    row = InventoryWarehouse(code="DEFAULT", name="默认仓")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def inv_sku(client: TestClient, headers: dict, warehouse_id: int) -> dict:
    response = client.post(
        f"{BASE}/skus",
        json={"sku_no": "WL-AUDIT-1", "name": "六角螺栓", "warehouse_id": warehouse_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def inv_last_audit(db, action: str) -> AuditLog:
    db.expire_all()
    row = db.scalar(
        select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id.desc())
    )
    assert row is not None, f"未写入审计记录: {action}"
    return row


# ---------------------------------------------------------------- 规则表（纯函数）


@pytest.mark.parametrize("method,path,action,target_type,target_id", _RULES_CASES)
def test_inventory_audit_rule_resolves(
    method: str, path: str, action: str, target_type: str, target_id: str | None
) -> None:
    match = resolve(method, path)
    assert match is not None, f"未命中审计规则: {method} {path}"
    assert (match.action, match.target_type, match.target_id) == (
        action,
        target_type,
        target_id,
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", f"{BASE}/skus"),
        ("GET", f"{BASE}/skus/7"),
        ("GET", f"{BASE}/movements"),
        ("GET", f"{BASE}/inbound-orders"),
        ("GET", f"{BASE}/low-stock"),
        ("GET", f"{BASE}/summary"),
        ("POST", f"{BASE}/skus/7/extra"),  # 末尾 $ 锚点，防子路径误命中 sku.create
    ],
)
def test_inventory_audit_read_paths_not_audited(method: str, path: str) -> None:
    assert resolve(method, path) is None


def test_inventory_audit_known_actions_exposes_group() -> None:
    actions = set(known_actions())
    expected = {case[2] for case in _RULES_CASES}
    assert len(expected) == 11
    assert expected <= actions, f"动作清单缺少: {expected - actions}"


# ---------------------------------------------------------------- _NAME_FIELDS 兜底


def test_inventory_audit_name_lookup_uses_model_fields(client: TestClient, db) -> None:
    """router 未给 target_name 时，_NAME_FIELDS 能按 id 查回 name / doc_no。"""
    headers = inv_headers(client, db)
    wh = inv_warehouse(db)
    sku = inv_sku(client, headers, wh.id)
    doc = client.post(
        f"{BASE}/inbound-orders",
        json={"warehouse_id": wh.id, "items": [{"sku_id": sku["id"], "quantity": 3}]},
        headers=headers,
    )
    assert doc.status_code == 201, doc.text

    assert _lookup_target_name("inventory_sku", str(sku["id"])) == "六角螺栓"
    assert (
        _lookup_target_name("inventory_document", str(doc.json()["id"]))
        == doc.json()["doc_no"]
    )


# ---------------------------------------------------------------- 端点落库


def test_inventory_audit_sku_create_logs_target(client: TestClient, db) -> None:
    headers = inv_headers(client, db)
    wh = inv_warehouse(db)
    sku = inv_sku(client, headers, wh.id)

    row = inv_last_audit(db, "inventory.sku.create")
    assert row.username == "admin"
    assert row.result == "success"
    assert row.target_type == "inventory_sku"
    assert row.target_id == str(sku["id"])
    assert "WL-AUDIT-1" in row.target_name


def test_inventory_audit_document_create_logs_doc_no(client: TestClient, db) -> None:
    headers = inv_headers(client, db)
    wh = inv_warehouse(db)
    sku = inv_sku(client, headers, wh.id)
    doc = client.post(
        f"{BASE}/inbound-orders",
        json={"warehouse_id": wh.id, "items": [{"sku_id": sku["id"], "quantity": 5}]},
        headers=headers,
    )
    assert doc.status_code == 201, doc.text

    row = inv_last_audit(db, "inventory.inbound.create")
    assert row.target_type == "inventory_document"
    assert row.target_id == str(doc.json()["id"])
    assert row.target_name == doc.json()["doc_no"]


def test_inventory_audit_document_edit_logs_doc_no(client: TestClient, db) -> None:
    headers = inv_headers(client, db)
    wh = inv_warehouse(db)
    sku = inv_sku(client, headers, wh.id)
    doc = client.post(
        f"{BASE}/inbound-orders",
        json={"warehouse_id": wh.id, "items": [{"sku_id": sku["id"], "quantity": 5}]},
        headers=headers,
    ).json()

    updated = client.put(
        f"{BASE}/documents/{doc['id']}",
        json={"items": [{"sku_id": sku["id"], "quantity": 6}]},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    row = inv_last_audit(db, "inventory.document.edit")
    assert row.target_type == "inventory_document"
    assert row.target_id == str(doc["id"])
    assert row.target_name == doc["doc_no"]
    assert row.detail.get("item_count") == 1


def test_inventory_audit_category_create_logs_name(client: TestClient, db) -> None:
    headers = inv_headers(client, db)
    created = client.post(f"{BASE}/categories", json={"name": "螺丝"}, headers=headers)
    assert created.status_code == 201, created.text

    row = inv_last_audit(db, "inventory.category.create")
    assert row.target_type == "inventory_category"
    assert row.target_id == str(created.json()["id"])
    assert row.target_name == "螺丝"


def test_inventory_audit_export_is_logged_even_as_get(client: TestClient, db) -> None:
    """导出是 GET 但含全量数据，必须 meta-audit（PRD §9）。"""
    headers = inv_headers(client, db)
    response = client.get(f"{BASE}/export", params={"type": "balance"}, headers=headers)
    assert response.status_code == 200, response.text

    row = inv_last_audit(db, "inventory.export")
    assert row.method == "GET"
    assert row.result == "success"
    assert row.target_type == "inventory"


def test_inventory_audit_forbidden_write_logged_as_failure(client: TestClient, db) -> None:
    """403 也要留痕（PRD §9：安全留痕含失败动作）。"""
    make_user(db, username="agent1", role="agent")
    token = login(client, "agent1")["access_token"]

    response = client.post(
        f"{BASE}/skus",
        json={"sku_no": "X-1", "name": "越权物资", "warehouse_id": 1},
        headers=auth_headers(token),
    )
    assert response.status_code == 403, response.text

    row = inv_last_audit(db, "inventory.sku.create")
    assert row.username == "agent1"
    assert row.result == "failure"
    assert row.error_code == "PERMISSION_DENIED"
