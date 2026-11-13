#!/usr/bin/env python3
"""生成进销存演示数据（PRD §11），用于前端联调、验收演示与对账测试。

用法（在仓库根执行，需 .venv）：
    .venv/bin/python scripts/dev/demo_inventory.py                  # 增量：已有单据则跳过，只做对账校验
    .venv/bin/python scripts/dev/demo_inventory.py --reset          # 清空库存业务数据后全量重建
    .venv/bin/python scripts/dev/demo_inventory.py --verify         # 只做对账校验，不写任何数据
    .venv/bin/python scripts/dev/demo_inventory.py --reset --base-url http://localhost:8000

前置：
    1. docker compose up -d（backend/frontend/nginx/db 全起，镜像须含库存代码）
    2. 已跑过 seed_demo.py（本脚本要关联现有 parts；缺零件会明确报错）
    3. deploy/.env 存在（psql 取 DB 账号、登录口令兜底）

口令：优先 ADMIN_PASSWORD 环境变量 → deploy/.env 的 ADMIN_INIT_PASSWORD。
      deploy/.env 里的口令可能与库中实际 admin 口令不一致（本地库历史原因），
      此时用 ADMIN_PASSWORD=真实口令 覆盖，不要在仓库里硬编码口令。

设计要点：
    - 数据本体是 SKU_SPECS / DOCUMENT_PLAN 两个常量，确定性、可复现，不用随机。
    - 单据一律走后台 API 写入；端点内部就是 service 层 create_document()，
      余额与 stock_movements 由过账逻辑生成，脚本**不手工插任何流水/余额**（PRD §11）。
    - simulate() 在写库前按同一份计划推演余额：任何出库超卖会提前失败，
      并断言最终恰好 3 条低库存，避免「脚本跑完才发现页面没标红」。
    - --reset 清 stock_movements 必须先禁用 append-only 触发器：005 迁移给它挂了
      行级（UPDATE/DELETE）和语句级（TRUNCATE）两个触发器，TRUNCATE 也会抛错。
      与 cleanup-audit.sh 同范式，全部放进一个事务，失败回滚时触发器自动恢复。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy"
COMPOSE_FILE = DEPLOY_DIR / "docker-compose.yml"
API = "/api/admin/inventory"

# ---------------------------------------------------------------- 数据本体
# part: 关联 parts 的槽位（0-based，运行时按 id 顺序映射到真实 part_id）；
#       None 表示纯物资（part_id 为空）。槽位 0 与 2 各出现两次 → 2 组「一零件多 SKU」。
# cost: 入库明细的 unit_cost，只写留档、不返回不计算（PRD §3.6）。
SKU_SPECS: list[dict] = [
    {"no": "INV-M01",   "name": "无刷电机-原厂", "spec": "KV100 原厂件", "unit": "台", "category": "动力系统", "part": 0,    "min": 10, "cost": 420},
    {"no": "INV-M02",   "name": "无刷电机-副厂", "spec": "KV100 兼容件", "unit": "台", "category": "动力系统", "part": 0,    "min": 8,  "cost": 265},
    {"no": "INV-E01",   "name": "电调 60A",      "spec": "60A 无刷",     "unit": "个", "category": "动力系统", "part": 1,    "min": 6,  "cost": 188},
    {"no": "INV-P01",   "name": "折叠桨叶-碳纤", "spec": "1855 碳纤",    "unit": "对", "category": "动力系统", "part": 2,    "min": 12, "cost": 96},
    {"no": "INV-P02",   "name": "折叠桨叶-尼龙", "spec": "1855 尼龙",    "unit": "对", "category": "动力系统", "part": 2,    "min": 10, "cost": 42},
    {"no": "INV-T01",   "name": "药箱 16L",      "spec": "16L 原装",     "unit": "个", "category": "喷洒系统", "part": 3,    "min": 5,  "cost": 310},
    {"no": "INV-PM01",  "name": "隔膜泵",        "spec": "12V 双泵",     "unit": "台", "category": "喷洒系统", "part": 4,    "min": 4,  "cost": 235},
    {"no": "INV-N01",   "name": "离心喷头",      "spec": "标准雾化",     "unit": "个", "category": "喷洒系统", "part": 5,    "min": 8,  "cost": 78},
    {"no": "INV-L01",   "name": "药液管路与滤网", "spec": "整套",        "unit": "套", "category": "喷洒系统", "part": 6,    "min": 6,  "cost": 55},
    {"no": "INV-F01",   "name": "飞控",          "spec": "V5+",          "unit": "个", "category": "飞控导航", "part": 7,    "min": 3,  "cost": 680},
    {"no": "INV-R01",   "name": "RTK 与罗盘",    "spec": "双天线",       "unit": "套", "category": "飞控导航", "part": 8,    "min": 3,  "cost": 920},
    {"no": "INV-B01",   "name": "智能电池",      "spec": "22.2V 16Ah",   "unit": "块", "category": "能源系统", "part": 9,    "min": 6,  "cost": 1250},
    {"no": "INV-BOX01", "name": "包装纸箱",      "spec": "五层 60×40",   "unit": "个", "category": "包材",     "part": None, "min": 20, "cost": 8},
    {"no": "INV-TIE01", "name": "尼龙扎带",      "spec": "200mm 100根",  "unit": "包", "category": "耗材",     "part": None, "min": 15, "cost": 6},
    {"no": "INV-TUBE01", "name": "热缩管",       "spec": "φ3 黑",        "unit": "卷", "category": "耗材",     "part": None, "min": 5,  "cost": 12},
    {"no": "INV-SCR01", "name": "螺丝包",        "spec": "M3 混装",      "unit": "包", "category": "紧固件",   "part": None, "min": 10, "cost": 9},
    {"no": "INV-GRE01", "name": "润滑脂",        "spec": "50g",          "unit": "支", "category": "耗材",     "part": None, "min": 4,  "cost": 18},
    {"no": "INV-CLO01", "name": "无尘布",        "spec": "100片",        "unit": "包", "category": "耗材",     "part": None, "min": 8,  "cost": 15},
    {"no": "INV-LAB01", "name": "标签纸",        "spec": "40×30 热敏",   "unit": "卷", "category": "耗材",     "part": None, "min": 6,  "cost": 11},
    {"no": "INV-CAP01", "name": "防尘塞",        "spec": "硅胶通用",     "unit": "个", "category": "耗材",     "part": None, "min": 12, "cost": 2},
]

# 单据计划：(类型, [(SKU 序号 1-based, 数量), ...], 备注)
# 类型 inbound / outbound / adjust_in / adjust_out，分别对应 4 个端点。
# 顺序即过账顺序：先 8 张入库铺底，再 12 张出库，最后 2 张调整。
# 最终余额由 simulate() 推演；SKU 2/3/6 会低于 min_stock，共 3 条低库存。
DOCUMENT_PLAN: list[tuple[str, list[tuple[int, int]], str]] = [
    ("inbound", [(1, 50), (2, 40), (3, 30)], "演示-采购入库-动力件"),
    ("inbound", [(4, 40), (5, 30), (6, 20)], "演示-采购入库-喷洒件A"),
    ("inbound", [(7, 20), (8, 30), (9, 25)], "演示-采购入库-喷洒件B"),
    ("inbound", [(10, 15), (11, 15), (12, 20)], "演示-采购入库-航电"),
    ("inbound", [(13, 80), (14, 100), (15, 30)], "演示-采购入库-包材耗材A"),
    ("inbound", [(16, 60), (17, 25), (18, 40)], "演示-采购入库-包材耗材B"),
    ("inbound", [(19, 30), (20, 50)], "演示-采购入库-包材耗材C"),
    ("inbound", [(1, 20), (4, 20), (12, 10)], "演示-补货入库"),

    ("outbound", [(1, 20), (2, 35)], "演示-维修领用-01"),
    ("outbound", [(3, 26), (4, 10)], "演示-维修领用-02"),
    ("outbound", [(5, 10), (6, 16)], "演示-维修领用-03"),
    ("outbound", [(7, 8), (8, 10)], "演示-维修领用-04"),
    ("outbound", [(9, 10)], "演示-维修领用-05"),
    ("outbound", [(10, 5), (11, 5)], "演示-维修领用-06"),
    ("outbound", [(12, 10), (13, 30)], "演示-维修领用-07"),
    ("outbound", [(14, 20)], "演示-维修领用-08"),
    ("outbound", [(15, 10), (16, 20)], "演示-维修领用-09"),
    ("outbound", [(17, 8)], "演示-维修领用-10"),
    ("outbound", [(18, 10), (19, 10)], "演示-维修领用-11"),
    ("outbound", [(20, 15)], "演示-维修领用-12"),

    ("adjust_in", [(8, 5), (13, 10)], "演示-月度盘点盘盈"),
    ("adjust_out", [(7, 2), (16, 3)], "演示-月度盘点盘亏"),
]

IN_TYPES = frozenset({"inbound", "adjust_in"})
LOW_STOCK_EXPECTED = 3

# --reset：清库存业务表（SKU / 单据 / 余额 / 流水），保留默认仓与分类主数据。
# stock_movements 有 append-only 触发器（行级 + TRUNCATE 级），必须先禁用；
# 所有语句在一个事务里，DELETE/TRUNCATE 抛错会回滚，触发器自动恢复启用。
SQL_RESET = """
BEGIN;
ALTER TABLE stock_movements DISABLE TRIGGER USER;
TRUNCATE inventory_document_items, inventory_documents, inventory_balances,
         inventory_skus, stock_movements
RESTART IDENTITY CASCADE;
ALTER TABLE stock_movements ENABLE TRIGGER USER;
COMMIT;
"""

# 对账：Σdelta 按 (sku_id, warehouse_id) 分组必须等于余额快照。
# FULL JOIN 同时暴露「有流水没余额」与「有余额没流水」两种缺口。
SQL_RECONCILE = """
SELECT count(*) FROM (
    SELECT sku_id, warehouse_id, sum(delta) AS total_delta
    FROM stock_movements GROUP BY sku_id, warehouse_id
) m
FULL JOIN inventory_balances b USING (sku_id, warehouse_id)
WHERE coalesce(b.quantity, 0) <> coalesce(m.total_delta, 0);
"""

SQL_STATS = """
SELECT
  (SELECT count(*) FROM inventory_skus),
  (SELECT count(*) FROM inventory_skus WHERE part_id IS NULL),
  (SELECT count(*) FROM inventory_documents),
  (SELECT count(*) FROM inventory_document_items),
  (SELECT count(*) FROM stock_movements),
  (SELECT count(*) FROM inventory_warehouses);
"""


# ---------------------------------------------------------------- 基础设施


def read_env() -> dict[str, str]:
    """读 deploy/.env：DB 账号与管理员口令兜底都从这里取，不额外要环境变量。"""
    text = (DEPLOY_DIR / ".env").read_text(encoding="utf-8")
    return dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.M))


def psql(sql: str, fetch: bool = False) -> str:
    """在 db 容器里执行 SQL（db 端口未映射到宿主机）。fetch=True 返回纯文本。"""
    env = read_env()
    cmd = [
        "docker", "compose", "-f", str(COMPOSE_FILE),
        "exec", "-T", "db",
        "psql", "-v", "ON_ERROR_STOP=1",
        "-U", env["DB_USER"], "-d", env["DB_NAME"],
    ]
    if fetch:
        cmd += ["-t", "-A", "-F", "|"]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"[demo-inventory] SQL 执行失败：\n{proc.stderr[:800]}", file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout if fetch else ""


def login(base: str) -> str:
    """登录 admin 拿 token。口令不写进仓库，用环境变量或 deploy/.env。"""
    password = os.getenv("ADMIN_PASSWORD") or read_env().get("ADMIN_INIT_PASSWORD")
    if not password:
        print("[demo-inventory] 需要 ADMIN_PASSWORD 环境变量或 deploy/.env", file=sys.stderr)
        raise SystemExit(2)
    with httpx.Client(base_url=base, timeout=30.0) as client:
        resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
    if resp.status_code != 200:
        print(
            f"[demo-inventory] 登录失败：{resp.status_code} {resp.text[:120]}\n"
            "  若 deploy/.env 的 ADMIN_INIT_PASSWORD 与库中实际口令不一致，"
            "请用 ADMIN_PASSWORD=真实口令 覆盖。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return resp.json()["access_token"]


def api_client(base: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base, timeout=30.0, headers={"Authorization": f"Bearer {token}"}
    )


def _ok(resp: httpx.Response, what: str) -> dict:
    # 创建端点统一 201；列表等 GET 是 200。
    if resp.status_code not in (200, 201):
        print(
            f"[demo-inventory] {what} 失败：{resp.status_code} {resp.text[:300]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return resp.json()


# ---------------------------------------------------------------- 自检


def simulate() -> dict[int, int]:
    """按 DOCUMENT_PLAN 推演余额，写库前拦住超卖与口径偏差。

    这不是重复实现过账逻辑，只是把计划里静态的 (+/-) 数量累加一遍，
    用来保证演示数据本身自洽；真正的余额与流水仍由后端 service 层生成。
    """
    assert len(SKU_SPECS) == 20, "SKU 应为 20 条"
    linked = [s for s in SKU_SPECS if s["part"] is not None]
    assert len(linked) == 12, "关联 parts 的 SKU 应为 12 条"
    assert len(SKU_SPECS) - len(linked) == 8, "纯物资 SKU 应为 8 条"
    slots = [s["part"] for s in linked]
    assert sum(1 for p in set(slots) if slots.count(p) > 1) == 2, "应有 2 组一零件多 SKU"

    counts = {t: sum(1 for d in DOCUMENT_PLAN if d[0] == t) for t in
              ("inbound", "outbound", "adjust_in", "adjust_out")}
    assert counts["inbound"] == 8 and counts["outbound"] == 12, "入库 8 / 出库 12"
    assert counts["adjust_in"] + counts["adjust_out"] == 2, "调整单 2 张"
    assert len(DOCUMENT_PLAN) == 22, "单据应为 22 张"
    detail_count = sum(len(items) for _, items, _ in DOCUMENT_PLAN)
    assert 40 <= detail_count <= 55, f"明细约 45 条，当前 {detail_count}"

    balance: dict[int, int] = {i: 0 for i in range(1, len(SKU_SPECS) + 1)}
    for seq, (doc_type, items, remark) in enumerate(DOCUMENT_PLAN, 1):
        for sku_no, qty in items:
            assert 1 <= sku_no <= len(SKU_SPECS), f"第 {seq} 张单据引用了不存在的 SKU 序号 {sku_no}"
            assert qty > 0, f"第 {seq} 张单据数量必须为正"
            if doc_type in IN_TYPES:
                balance[sku_no] += qty
            else:
                if balance[sku_no] < qty:
                    print(
                        f"[demo-inventory] 计划自洽性失败：第 {seq} 张「{remark}」"
                        f"要出库 SKU#{sku_no} {qty} 件，但当时余额只有 {balance[sku_no]} 件。\n"
                        "  请调整 DOCUMENT_PLAN 的入库量或出库量后重跑（不要放宽这里）。",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)
                balance[sku_no] -= qty
        assert min(balance.values()) >= 0, "余额不得为负"

    low = [i for i, qty in balance.items() if qty < SKU_SPECS[i - 1]["min"]]
    assert len(low) == LOW_STOCK_EXPECTED, (
        f"应恰好 {LOW_STOCK_EXPECTED} 条低库存，当前 {len(low)} 条：{low}"
    )
    print(
        f"[demo-inventory] 计划自检通过：20 SKU（12 关联 / 8 纯物资 / 2 组一零件多 SKU）、"
        f"22 单据、{detail_count} 明细、低库存 {len(low)} 条（SKU#{low}）"
    )
    return balance


# ---------------------------------------------------------------- 写入


def fetch_part_refs() -> list[tuple[int, int]]:
    """取现有零件的 (id, product_id)（按 id 升序），供 SKU 弱关联与产品关联使用。"""
    out = psql("SELECT id || '|' || product_id FROM parts ORDER BY id LIMIT 20;", fetch=True)
    refs: list[tuple[int, int]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        part_id, product_id = line.strip().split("|")
        refs.append((int(part_id), int(product_id)))
    if len(refs) < 10:
        print(
            f"[demo-inventory] 库里只有 {len(refs)} 个零件，需要至少 10 个。\n"
            "  请先跑 .venv/bin/python scripts/dev/seed_demo.py --reset --activity",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return refs


def ensure_warehouse(client: httpx.Client) -> int:
    page = _ok(client.get(f"{API}/warehouses"), "读取仓库")
    active = [w for w in page["items"] if w["is_active"]]
    if not active:
        print("[demo-inventory] 没有启用中的仓库，请检查 005_inventory 迁移", file=sys.stderr)
        raise SystemExit(1)
    return active[0]["id"]


def ensure_categories(client: httpx.Client) -> dict[str, int]:
    """分类主数据幂等创建，返回「名称 → id」。"""
    existing = {
        item["name"]: item["id"]
        for item in _ok(
            client.get(f"{API}/categories", params={"page_size": 100}), "读取分类"
        )["items"]
    }
    wanted = sorted({spec["category"] for spec in SKU_SPECS})
    created = 0
    for name in wanted:
        if name in existing:
            continue
        body = _ok(client.post(f"{API}/categories", json={"name": name}), f"创建分类 {name}")
        existing[name] = body["id"]
        created += 1
    print(f"[demo-inventory] 分类 {len(wanted)} 个（新建 {created}，复用 {len(wanted) - created}）")
    return existing


def _link_patch(
    row: dict,
    spec: dict,
    category_ids: dict[str, int],
    part_refs: list[tuple[int, int]],
) -> dict:
    """算出一个已存在 SKU 需要补的关联字段（已齐则返回空 dict）。"""
    patch: dict = {}
    if not row.get("categories"):
        patch["category_ids"] = [category_ids[spec["category"]]]
    if not row.get("products") and spec["part"] is not None:
        patch["product_ids"] = [part_refs[spec["part"]][1]]
    return patch


def backfill_sku_links(
    client: httpx.Client,
    category_ids: dict[str, int],
    part_refs: list[tuple[int, int]],
) -> int:
    """给已存在的 SKU 补齐分类/产品关联，不新建、不过账。

    迁移 007 删掉了旧的自由文本 category 列，历史 SKU 变成「无分类」；
    而 create_skus 在已有流水时会被主流程跳过，故单独提供这一步。
    """
    existing = {
        item["sku_no"]: item
        for item in _ok(client.get(f"{API}/skus", params={"page_size": 100}), "读取 SKU")["items"]
    }
    specials = {spec["no"]: spec for spec in SKU_SPECS}
    patched = 0
    for sku_no, row in existing.items():
        spec = specials.get(sku_no)
        if spec is None:
            continue
        patch = _link_patch(row, spec, category_ids, part_refs)
        if patch:
            _ok(client.put(f"{API}/skus/{row['id']}", json=patch), f"补齐 SKU {sku_no} 关联")
            patched += 1
    print(f"[demo-inventory] SKU 关联补齐 {patched} 条（已齐的跳过）")
    return patched


def create_skus(
    client: httpx.Client,
    warehouse_id: int,
    part_refs: list[tuple[int, int]],
    category_ids: dict[str, int],
) -> dict[int, int]:
    """按 sku_no 幂等创建，返回「SKU 序号 → 真实 id」。

    分类走多对多（category_ids），产品按所关联零件所属产品弱关联（product_ids）。
    已存在的 SKU 不重建，但会补齐缺失的分类/产品关联（迁移后旧数据无关联，
    幂等脚本应向目标状态收敛而非简单跳过）。
    """
    existing = {
        item["sku_no"]: item
        for item in _ok(client.get(f"{API}/skus", params={"page_size": 100}), "读取 SKU")["items"]
    }
    mapping: dict[int, int] = {}
    created = 0
    backfilled = 0
    for seq, spec in enumerate(SKU_SPECS, 1):
        part_id = None if spec["part"] is None else part_refs[spec["part"]][0]
        product_ids = [] if spec["part"] is None else [part_refs[spec["part"]][1]]
        if spec["no"] in existing:
            row = existing[spec["no"]]
            mapping[seq] = row["id"]
            patch = _link_patch(row, spec, category_ids, part_refs)
            if patch:
                _ok(client.put(f"{API}/skus/{row['id']}", json=patch), f"补齐 SKU {spec['no']} 关联")
                backfilled += 1
            continue
        payload = {
            "sku_no": spec["no"],
            "name": spec["name"],
            "spec": spec["spec"],
            "unit": spec["unit"],
            "category_ids": [category_ids[spec["category"]]],
            "product_ids": product_ids,
            "part_id": part_id,
            "warehouse_id": warehouse_id,
            "min_stock": spec["min"],
            "unit_cost": spec["cost"],
            "remark": "进销存演示数据",
        }
        body = _ok(client.post(f"{API}/skus", json=payload), f"创建 SKU {spec['no']}")
        mapping[seq] = body["id"]
        created += 1
    print(
        f"[demo-inventory] SKU 新建 {created} 条，复用 {len(SKU_SPECS) - created} 条"
        f"（其中补齐关联 {backfilled} 条）"
    )
    return mapping


_ENDPOINTS = {
    "inbound": "/inbound-orders",
    "outbound": "/outbound-orders",
    "adjust_in": "/adjustments",
    "adjust_out": "/adjustments",
}


def create_documents(client: httpx.Client, warehouse_id: int, sku_ids: dict[int, int]) -> None:
    for doc_type, items, remark in DOCUMENT_PLAN:
        payload: dict = {
            "warehouse_id": warehouse_id,
            "remark": remark,
            "items": [
                {
                    "sku_id": sku_ids[seq],
                    "quantity": qty,
                    # 入库明细带单价留档；出库/调整不写（§3.6：只写留档、不返回不计算）
                    "unit_cost": SKU_SPECS[seq - 1]["cost"] if doc_type in IN_TYPES else None,
                }
                for seq, qty in items
            ],
        }
        if doc_type.startswith("adjust_"):
            payload["adjust_type"] = "in" if doc_type == "adjust_in" else "out"
        body = _ok(
            client.post(f"{API}{_ENDPOINTS[doc_type]}", json=payload),
            f"创建单据「{remark}」",
        )
        print(f"  {body['doc_no']}  {doc_type:<10} {len(items)} 明细  {remark}")
    print(f"[demo-inventory] 单据写入完成：{len(DOCUMENT_PLAN)} 张")


# ---------------------------------------------------------------- 对账


def verify(expect_low_stock: int | None = None) -> int:
    """交付关卡 5：Σdelta 按 SKU 分组 == balances.quantity。

    expect_low_stock 只在「刚写完演示数据」时传值校验数据规格；独立 --verify
    用于任意数据集的纯对账，不检查内容规格，否则会误报。
    """
    mismatches = psql(SQL_RECONCILE, fetch=True).strip()
    if mismatches != "0":
        print(f"[demo-inventory] 对账失败：{mismatches} 个 (sku, 仓库) 组合的流水与余额不一致", file=sys.stderr)
        return 1

    out = psql(SQL_STATS, fetch=True).strip()
    skus, pure, docs, details, movements, warehouses = (int(x) for x in out.split("|"))
    low = psql(
        "SELECT count(*) FROM inventory_balances b JOIN inventory_skus s ON s.id=b.sku_id "
        "WHERE s.is_active AND b.quantity < s.min_stock;",
        fetch=True,
    ).strip()
    print(
        f"[demo-inventory] 对账通过（0 处不一致）：SKU {skus}（纯物资 {pure}）· "
        f"仓库 {warehouses} · 单据 {docs} · 明细 {details} · 流水 {movements} · 低库存 {low}"
    )
    if expect_low_stock is not None and int(low) != expect_low_stock:
        print(f"[demo-inventory] 低库存应为 {expect_low_stock} 条，实际 {low} 条", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- 入口


def main() -> int:
    parser = argparse.ArgumentParser(description="生成进销存演示数据（PRD §11）")
    parser.add_argument("--base-url", default="http://127.0.0.1", help="后台根地址，默认经 nginx :80")
    parser.add_argument("--reset", action="store_true", help="清空库存业务数据后全量重建（保留默认仓与用户）")
    parser.add_argument("--verify", action="store_true", help="只做对账校验，不写任何数据")
    args = parser.parse_args()

    if args.verify:
        return verify()

    balance = simulate()

    if args.reset:
        print("[demo-inventory] 清空库存业务数据（保留默认仓）…")
        psql(SQL_RESET)

    token = login(args.base_url)
    with api_client(args.base_url, token) as client:
        part_refs = fetch_part_refs()
        warehouse_id = ensure_warehouse(client)
        category_ids = ensure_categories(client)
        doc_count = _ok(client.get(f"{API}/movements", params={"page_size": 1}), "读取流水")["total"]
        if not args.reset and doc_count > 0:
            print(
                f"[demo-inventory] 已有 {doc_count} 条流水，跳过写入以免重复过账。"
                "  如需重建请加 --reset。"
            )
            # 分类/产品关联是后加的，老数据要单独补，不能跟着过账一起跳过
            backfill_sku_links(client, category_ids, part_refs)
            return verify()

        sku_ids = create_skus(client, warehouse_id, part_refs, category_ids)
        create_documents(client, warehouse_id, sku_ids)

    print("[demo-inventory] 低库存 SKU（由 simulate 推演，仅供核对）："
          + " ".join(f"{SKU_SPECS[i-1]['no']}={q}" for i, q in balance.items() if q < SKU_SPECS[i-1]["min"]))
    return verify(expect_low_stock=LOW_STOCK_EXPECTED)


if __name__ == "__main__":
    raise SystemExit(main())
