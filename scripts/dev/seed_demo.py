#!/usr/bin/env python3
"""生成演示数据（无人机：农业植保 + 穿越机），用于前端联调与验收演示。

数据本体在 demo_data.py，本文件只负责「怎么写入」。

三种用法：
    python scripts/dev/seed_demo.py                  # 增量写入，按型号幂等跳过（走后台 API）
    python scripts/dev/seed_demo.py --via-sql        # 同上，但不登录、直接写库（忘记管理员密码时用）
    python scripts/dev/seed_demo.py --reset          # 清空业务数据后重建（保留用户）
    python scripts/dev/seed_demo.py --activity       # 重建查询日志与工单，让看板有数
    python scripts/dev/seed_demo.py --reset --activity   # 全量重建（换机型时用这个）

--reset / --activity / --via-sql 走 docker compose exec psql（db 端口未映射到宿主机），
所以需要在能执行 docker compose 的机器上跑，且 deploy/.env 存在。
--via-sql 会跳过附件上传（上传必须走 API 拿文件路径）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_data import MISS_QUERIES, PRODUCT_LINES, PRODUCTS, TICKET_DESCRIPTIONS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy"
COMPOSE_FILE = DEPLOY_DIR / "docker-compose.yml"


def read_env() -> dict[str, str]:
    """读 deploy/.env：数据库账号与管理员初始密码都从这里取，不额外要环境变量。"""
    text = (DEPLOY_DIR / ".env").read_text(encoding="utf-8")
    return dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.M))


def psql(sql: str, fetch: bool = False) -> str:
    """在 db 容器里执行 SQL。fetch=True 时返回 `|` 分隔、无表头的纯文本，方便解析。"""
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
        print(f"[seed] SQL 执行失败：\n{proc.stderr[:800]}", file=sys.stderr)
        raise SystemExit(1)
    if fetch:
        return proc.stdout
    if proc.stdout.strip():
        print(proc.stdout.strip())
    return ""


def api(base: str, token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base, headers=headers, timeout=30.0)


def login(base: str) -> str:
    password = os.getenv("ADMIN_INIT_PASSWORD") or read_env().get("ADMIN_INIT_PASSWORD")
    if not password:
        print("[seed] 需要 ADMIN_INIT_PASSWORD 环境变量或 deploy/.env", file=sys.stderr)
        raise SystemExit(2)

    with api(base) as client:
        resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
        if resp.status_code != 200:
            print(f"[seed] 登录失败：{resp.status_code} {resp.text[:120]}", file=sys.stderr)
            raise SystemExit(1)
        return resp.json()["access_token"]


# 清库顺序按外键依赖：工单日志 → 工单 → 查询日志 → 故障 → 零件 → 产品 → 产品线。
# RESTART IDENTITY 让 id 从 1 开始，方便 E2E 与文档引用稳定 id。
# 注意：CASCADE 会连带清空 user_product_lines（账号的产品线归属），
# 所以重建后要按「用户名 + 产品线名」把归属恢复回去，见 restore_assignments()。
SQL_RESET = """
TRUNCATE ticket_status_logs, tickets, query_logs, faults, parts, products, product_lines
RESTART IDENTITY CASCADE;
"""

SQL_FETCH_ASSIGNMENTS = """
SELECT u.username, pl.name, coalesce(extract(epoch FROM upl.expires_at)::bigint::text, '')
FROM user_product_lines upl
JOIN users u ON u.id = upl.user_id
JOIN product_lines pl ON pl.id = upl.line_id
ORDER BY 1, 2;
"""


def _q(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _jsonb(value: object) -> str:
    # dollar-quoting 省掉 JSON 里所有单引号的转义；演示文案里不会出现 $json$
    return "$json$" + json.dumps(value, ensure_ascii=False) + "$json$::jsonb"


def build_seed_sql() -> str:
    """把 demo_data 翻成幂等 SQL。

    为什么不直接用一条 INSERT ... VALUES：每张表的父 id 都要按业务名查回来，
    而 REPEATABLE READ 下用子查询按名字取父行，脚本就能反复执行而不依赖 id。
    幂等键：产品线 name、产品 model、零件 (product_id, name)、故障 (product_id, title)。
    """
    stmts: list[str] = []

    for line in PRODUCT_LINES:
        stmts.append(
            f"INSERT INTO product_lines (name, sort_order) VALUES ({_q(line['name'])}, {line['sort_order']}) "
            f"ON CONFLICT (name) DO UPDATE SET sort_order = EXCLUDED.sort_order;"
        )

    for spec in PRODUCTS:
        stmts.append(
            "INSERT INTO products (name, model, line_id, description, sort_order)\n"
            f"SELECT {_q(spec['name'])}, {_q(spec['model'])}, l.id, {_q(spec['description'])}, {spec['sort_order']}\n"
            f"FROM product_lines l WHERE l.name = {_q(spec['line'])}\n"
            "ON CONFLICT (model) DO NOTHING;"
        )

        for part in spec["parts"]:
            stmts.append(
                "INSERT INTO parts (product_id, part_no, name, group_name, sort_order)\n"
                f"SELECT p.id, {_q(part['part_no'])}, {_q(part['name'])}, {_q(part['group_name'])}, {part['sort_order']}\n"
                f"FROM products p WHERE p.model = {_q(spec['model'])}\n"
                f"  AND NOT EXISTS (SELECT 1 FROM parts x WHERE x.product_id = p.id AND x.name = {_q(part['name'])});"
            )

        for fault in spec["faults"]:
            steps = [
                {"step": index + 1, "text": text, "image_url": None}
                for index, text in enumerate(fault["steps"])
            ]
            stmts.append(
                "INSERT INTO faults (product_id, part_id, title, symptom, root_cause, solution_steps,\n"
                "                    required_tools, needs_professional, created_by)\n"
                f"SELECT p.id, pt.id, {_q(fault['title'])}, {_q(fault['symptom'])}, {_q(fault['root_cause'])},\n"
                f"       {_jsonb(steps)}, {_q(fault['tools'])}, {'TRUE' if fault['needs_professional'] else 'FALSE'},\n"
                "       (SELECT id FROM users WHERE username = 'admin')\n"
                f"FROM products p JOIN parts pt ON pt.product_id = p.id AND pt.name = {_q(fault['part'])}\n"
                f"WHERE p.model = {_q(spec['model'])}\n"
                f"  AND NOT EXISTS (SELECT 1 FROM faults f WHERE f.product_id = p.id AND f.title = {_q(fault['title'])});"
            )

    return "\n".join(stmts) + "\n"


def fetch_assignments() -> list[tuple[str, str, str]]:
    out = psql(SQL_FETCH_ASSIGNMENTS, fetch=True)
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[0].strip():
            rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return rows


def restore_assignments(rows: list[tuple[str, str, str]]) -> None:
    """按产品线名恢复账号归属。新库没有同名产品线时自然跳过（JOIN 不命中）。"""
    if not rows:
        return
    values = ", ".join(
        "('{}', '{}', {})".format(
            user.replace("'", "''"),
            line_name.replace("'", "''"),
            f"to_timestamp({epoch})" if epoch else "NULL::timestamptz",
        )
        for user, line_name, epoch in rows
    )
    psql(
        f"""
        INSERT INTO user_product_lines (user_id, line_id, expires_at)
        SELECT u.id, l.id, v.expires_at
        FROM (VALUES {values}) AS v(username, line_name, expires_at)
        JOIN users u ON u.username = v.username
        JOIN product_lines l ON l.name = v.line_name
        ON CONFLICT DO NOTHING;
        """
    )
    print(f"[seed] 已恢复 {len(rows)} 条账号产品线归属")

# 查询日志：600 条、30 天、约 70% 命中、命中里约 70% 标记已解决。
# 数字都写死在小范围里而不是 random()——演示库每次重建的看板数值应可复现，
# random() 会让截图和报告对不上。
SQL_ACTIVITY = """
-- 幂等：活动数据整表重建，避免重复执行时工单号撞唯一约束
TRUNCATE ticket_status_logs, tickets, query_logs RESTART IDENTITY;

WITH f AS (
    SELECT array_agg(id ORDER BY id) AS ids,
           array_agg(product_id ORDER BY id) AS pids,
           array_agg(part_id ORDER BY id) AS ptids
    FROM faults WHERE is_published
), miss AS (
    SELECT ARRAY[{miss_queries}]::text[] AS words
), k AS (
    SELECT array_length(ids, 1) AS n FROM f
), g AS (
    SELECT i,
           (i % 10) < 7 AS hit,
           now()
             - ((i % 30) || ' days')::interval
             - (((i * 13) % 24) || ' hours')::interval
             - (((i * 7) % 60) || ' minutes')::interval AS created
    FROM generate_series(1, 600) AS s(i)
), picked AS (
    -- 故障命中分布刻意做成「长尾」：真实知识库里少数故障吃掉大半访问量。
    -- idx = u²/n（u 均匀 0..n-1）会让小 id 被选中的概率明显偏高，
    -- 且全程无 random()，重建后 Top10 榜单可复现。
    SELECT g.*, 1 + (((g.i * 37) % k.n) * ((g.i * 37) % k.n)) / k.n AS idx
    FROM g CROSS JOIN k
)
INSERT INTO query_logs (product_id, part_id, fault_id, raw_query, hit, resolved, ip, user_agent, created_at)
SELECT
    CASE WHEN p.hit THEN f.pids[p.idx] END,
    CASE WHEN p.hit THEN f.ptids[p.idx] END,
    CASE WHEN p.hit THEN f.ids[p.idx] END,
    CASE WHEN p.hit THEN NULL ELSE miss.words[1 + p.i % array_length(miss.words, 1)] END,
    p.hit,
    CASE WHEN p.hit THEN (p.i % 10) < 5 ELSE NULL END,
    '10.20.' || (p.i % 200) || '.' || (p.i % 250),
    (ARRAY[
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        'Mozilla/5.0 (Linux; Android 14; 23013RK75C) AppleWebKit/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
    ])[1 + p.i % 3],
    p.created
FROM picked p CROSS JOIN f CROSS JOIN miss;

-- 工单：24 张，状态轮转分布，时间散在 28 天内（看板默认按最近 7 天/30 天筛选）
WITH base AS (
    SELECT i,
           now()
             - ((i % 28) || ' days')::interval
             - (((i * 5) % 12) || ' hours')::interval AS created,
           (ARRAY['open', 'processing', 'resolved', 'closed'])[1 + (i % 4)] AS status
    FROM generate_series(1, 24) AS s(i)
), picked AS (
    SELECT b.*,
           row_number() OVER (PARTITION BY b.created::date ORDER BY b.i) AS seq
    FROM base b
), with_fault AS (
    SELECT p.*, fl.id AS fault_id, fl.product_id, fl.part_id
    FROM picked p
    CROSS JOIN LATERAL (
        SELECT id, product_id, part_id FROM faults
        WHERE is_published ORDER BY id
        OFFSET (p.i * 3) % (SELECT count(*) FROM faults) LIMIT 1
    ) fl
)
INSERT INTO tickets (
    ticket_no, product_id, part_id, fault_id, contact, contact_name,
    description, need_on_site, status, assignee_id, remark, created_at, updated_at
)
SELECT
    'TK' || to_char(w.created, 'YYYYMMDD') || lpad(w.seq::text, 4, '0'),
    w.product_id, w.part_id, w.fault_id,
    (ARRAY['138', '139', '137', '150', '186', '188'])[1 + w.i % 6]
        || lpad((10000000 + w.i * 137)::text, 8, '0'),
    '客户' || w.i,
    (ARRAY[{ticket_desc}]::text[])[1 + w.i % {ticket_n}],
    w.i % 5 = 0,
    w.status,
    CASE WHEN w.status = 'open' THEN NULL ELSE (SELECT id FROM users WHERE username = 'admin') END,
    CASE w.status
        WHEN 'open' THEN NULL
        WHEN 'processing' THEN '已联系客户，安排本周上门检测'
        WHEN 'resolved' THEN '更换配件后试飞正常，客户确认解决'
        ELSE '客户已自行处理，工单关闭'
    END,
    w.created,
    w.created + interval '3 hours'
FROM with_fault w;

-- 流转记录：每单一条建单日志；非 open 的再补一条状态变更
INSERT INTO ticket_status_logs (ticket_id, from_status, to_status, operator_id, remark, created_at)
SELECT id, NULL, 'open', NULL, NULL, created_at FROM tickets
UNION ALL
SELECT id, 'open', status,
       (SELECT id FROM users WHERE username = 'admin'),
       remark, created_at + interval '1 hour'
FROM tickets WHERE status <> 'open';

-- 故障累计浏览/解决数：客户侧列表按 view_count 排序，全 0 时顺序没有意义，
-- 所以按 id 生成一组确定性数值（可复现），解决率落在 55%~79% 的正常区间。
UPDATE faults
SET view_count = 5 + (id * 37) % 120,
    resolved_count = (5 + (id * 37) % 120) * (55 + (id * 13) % 25) / 100;
"""


def build_activity_sql() -> str:
    def arr(items: list[str]) -> str:
        return ", ".join("'" + item.replace("'", "''") + "'" for item in items)

    return SQL_ACTIVITY.format(
        miss_queries=arr(MISS_QUERIES),
        ticket_desc=arr(TICKET_DESCRIPTIONS),
        ticket_n=len(TICKET_DESCRIPTIONS),
    )


def upload_demo_pdf(client: httpx.Client) -> str | None:
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    files = {"file": ("3WWDZ-16A 作业手册.pdf", pdf, "application/pdf")}
    resp = client.post("/api/admin/upload", files=files)
    if resp.status_code != 200:
        print(f"[seed] 附件上传失败（跳过附件）：{resp.status_code} {resp.text[:100]}")
        return None
    return resp.json()


def ensure_lines(client: httpx.Client) -> dict[str, int]:
    existing = {item["name"]: item for item in client.get("/api/admin/product-lines").json()["items"]}
    mapping = {}
    for spec in PRODUCT_LINES:
        name = spec["name"]
        if name not in existing:
            resp = client.post("/api/admin/product-lines", json=spec)
            if resp.status_code != 200:
                print(f"[seed] 产品线「{name}」创建失败：{resp.status_code} {resp.text[:200]}", file=sys.stderr)
                raise SystemExit(1)
            existing[name] = resp.json()
        mapping[name] = existing[name]["id"]
    return mapping


def create_faults(client: httpx.Client, product: dict, part_ids: dict[str, int], spec: dict) -> int:
    """逐条建故障。part 名写错时给出可定位的报错，而不是裸 KeyError。"""
    created = 0
    for fault in spec["faults"]:
        part_name = fault["part"]
        if part_name not in part_ids:
            print(
                f"[seed] 产品 {spec['model']} 的故障「{fault['title']}」引用了不存在的零件「{part_name}」",
                file=sys.stderr,
            )
            raise SystemExit(1)

        payload = {
            "product_id": product["id"],
            "part_id": part_ids[part_name],
            "title": fault["title"],
            "symptom": fault["symptom"],
            "root_cause": fault["root_cause"],
            "solution_steps": [
                {"step": index + 1, "text": text, "image_url": None}
                for index, text in enumerate(fault["steps"])
            ],
            "required_tools": fault["tools"],
            "needs_professional": fault["needs_professional"],
        }
        resp = client.post("/api/admin/faults", json=payload)
        if resp.status_code != 200:
            print(
                f"[seed] 故障「{fault['title']}」创建失败：{resp.status_code} {resp.text[:300]}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        created += 1
    return created


def seed_via_api(base_url: str, skip_attachment: bool = False) -> dict[str, int]:
    token = login(base_url)
    created = {"products": 0, "parts": 0, "faults": 0}

    with api(base_url, token) as client:
        existing = {
            item["model"]
            for item in client.get("/api/admin/products", params={"page_size": 100}).json()["items"]
        }
        lines = ensure_lines(client)

        for spec in PRODUCTS:
            if spec["model"] in existing:
                print(f"[seed] 产品 {spec['model']} 已存在，跳过")
                continue

            resp = client.post(
                "/api/admin/products",
                json={
                    "name": spec["name"],
                    "model": spec["model"],
                    "line_id": lines[spec["line"]],
                    "description": spec["description"],
                    "sort_order": spec["sort_order"],
                },
            )
            if resp.status_code != 200:
                print(f"[seed] 产品 {spec['model']} 创建失败：{resp.status_code} {resp.text[:200]}", file=sys.stderr)
                raise SystemExit(1)
            product = resp.json()
            created["products"] += 1

            part_ids: dict[str, int] = {}
            for part in spec["parts"]:
                resp = client.post("/api/admin/parts", json={"product_id": product["id"], **part})
                if resp.status_code != 200:
                    print(f"[seed] 零件「{part['name']}」创建失败：{resp.status_code} {resp.text[:200]}", file=sys.stderr)
                    raise SystemExit(1)
                part_ids[part["name"]] = resp.json()["id"]
                created["parts"] += 1

            created["faults"] += create_faults(client, product, part_ids, spec)

        if not skip_attachment:
            # 给第一条故障挂一个附件，用于验证详情页附件区（也是上传链路的冒烟）
            faults = client.get("/api/admin/faults", params={"page_size": 1}).json()["items"]
            if faults:
                detail = client.get(f"/api/admin/faults/{faults[0]['id']}").json()
                if not detail["attachment_urls"]:
                    attachment = upload_demo_pdf(client)
                    if attachment:
                        detail["attachment_urls"] = [
                            {"name": attachment["filename"], "url": attachment["url"], "size": attachment["size"]}
                        ]
                        client.put(f"/api/admin/faults/{faults[0]['id']}", json={"attachment_urls": detail["attachment_urls"]})
                        print(f"[seed] 已给「{detail['title']}」挂附件 {attachment['url']}")
    return created


def count_totals() -> dict[str, int]:
    out = psql(
        "SELECT (SELECT count(*) FROM products), (SELECT count(*) FROM parts), "
        "(SELECT count(*) FROM faults);",
        fetch=True,
    ).strip()
    products, parts, faults = (int(x) for x in out.split("|"))
    return {"products": products, "parts": parts, "faults": faults}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成无人机演示数据")
    parser.add_argument("--base-url", default="http://127.0.0.1")
    parser.add_argument("--reset", action="store_true", help="清空业务数据后重建（保留用户）")
    parser.add_argument("--activity", action="store_true", help="重建查询日志与工单演示数据")
    parser.add_argument("--via-sql", action="store_true", help="不登录后台、直接写库（忘记管理员密码时用）")
    parser.add_argument("--skip-attachment", action="store_true", help="跳过附件上传")
    args = parser.parse_args()

    assignments: list[tuple[str, str, str]] = []
    if args.reset:
        # 先记下账号的产品线归属，清库会连带删掉这张关联表
        assignments = fetch_assignments()
        print("[seed] 清空业务数据（工单/查询日志/故障/零件/产品/产品线）…")
        psql(SQL_RESET)

    if args.via_sql:
        print("[seed] 直接写库（跳过后台 API 与附件上传）…")
        psql(build_seed_sql())
        created = count_totals()
    else:
        created = seed_via_api(args.base_url, args.skip_attachment)

    if args.activity:
        print("[seed] 重建查询日志与工单…")
        psql(build_activity_sql())

    if args.reset:
        restore_assignments(assignments)

    print(
        f"[seed] 完成：库内共产品 {created['products']}、零件 {created['parts']}、故障 {created['faults']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
