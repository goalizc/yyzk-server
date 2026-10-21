#!/usr/bin/env python3
"""性能压测造数脚本（TC-70 / TC-71）。

在现有库里追加「压测专用」数据，不动演示数据：
  - 故障 5 万条，散布在已有 product/part 下，约 90% 已发布
  - query_logs 50 万条，时间跨度 90 天，命中/未命中约 7:3

全部走 SQL 的 generate_series 一次性生成，不做逐条 INSERT——
50 万次单行插入在容器里要跑几十分钟，批量生成只需几秒。

幂等：压测数据用固定标记识别（faults.title 以 PRESSURE_ 开头），
重复执行不会叠加；--clean 只删这些带标记的数据。

用法（在 deploy/ 目录执行）：
    python ../scripts/dev/seed_pressure.py             # 造数
    python ../scripts/dev/seed_pressure.py --clean     # 只清理压测数据
    python ../scripts/dev/seed_pressure.py --check     # 只看当前行数

    --faults 50000 --logs 500000   自定义规模
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 压测数据的识别标记。改这里要同步改 SQL 里的条件。
# 注意：SQL 的 LIKE 里下划线是通配符，写进 pattern 时统一用 MARK_LIKE 转义。
MARK = "PRESSURE_"
MARK_LIKE = "PRESSURE\\_"

DEFAULT_FAULTS = 50000
DEFAULT_LOGS = 500000
# 每零件下的故障数。真实知识库是十几到几十条，若把 5 万条塞进 5 个零件，
# 列表接口会一次返回上万行（实测 900KB），测出来的延迟没有参考价值。
DEFAULT_PER_PART = 20

# 补齐压测专用零件。product 沿用已有产品，part_no 带 PRESSURE 前缀便于清理。
SQL_PARTS = """
INSERT INTO parts (product_id, name, part_no, group_name, sort_order)
SELECT
    pr.id,
    'PRESSURE_压测零件 ' || s.i,
    'P-PRESSURE-' || s.i,
    '压测分组',
    s.i
FROM generate_series(1, {n}) AS s(i)
CROSS JOIN LATERAL (
    SELECT id FROM products ORDER BY id LIMIT 1 OFFSET (s.i % (SELECT count(*) FROM products))
) pr;
"""

SQL_CLEAN_PARTS = """
DELETE FROM parts WHERE name LIKE '{mark}%' ESCAPE '\\';
"""

SQL_COUNT = """
SELECT 'products' AS t, count(*) FROM products
UNION ALL SELECT 'parts', count(*) FROM parts
UNION ALL SELECT 'parts_pressure', count(*) FROM parts WHERE name LIKE '{mark}%' ESCAPE '\\'
UNION ALL SELECT 'faults', count(*) FROM faults
UNION ALL SELECT 'faults_pressure', count(*) FROM faults WHERE title LIKE '{mark}%' ESCAPE '\\'
UNION ALL SELECT 'query_logs', count(*) FROM query_logs
UNION ALL SELECT 'query_logs_pressure', count(*) FROM query_logs
    WHERE fault_id IN (SELECT id FROM faults WHERE title LIKE '{mark}%' ESCAPE '\\')
UNION ALL SELECT 'tickets', count(*) FROM tickets;
""".format(mark=MARK_LIKE)

# 5 万条故障：一条 INSERT ... SELECT，让 PG 在库内循环生成。
SQL_FAULTS = """
INSERT INTO faults (
    product_id, part_id, title, symptom, root_cause,
    solution_steps, required_tools, needs_professional,
    attachment_urls, view_count, resolved_count, is_published
)
SELECT
    c.product_id,
    c.part_id,
    'PRESSURE_故障样本 ' || i,
    '压测现象描述：设备在连续运行后出现异响，伴随指示灯闪烁（样本 ' || i || '）',
    '压测根因描述：疑似轴承磨损或装配公差超限（样本 ' || i || '）',
    jsonb_build_array(
        jsonb_build_object('step', 1, 'text', '断开电源，等待 30 秒后重新上电'),
        jsonb_build_object('step', 2, 'text', '检查卡扣是否到位，清理可见异物'),
        jsonb_build_object('step', 3, 'text', '若仍异常，联系工程师上门更换部件')
    ),
    '十字螺丝刀',
    (i % 20 = 0),
    '[]'::jsonb,
    (i * 37) % 10000,        -- view_count 拉开梯度，避免排序退化
    (i * 11) % 500,
    (i % 10 <> 0)            -- 约 90% 已发布
FROM generate_series(1, {n}) AS s(i)
CROSS JOIN LATERAL (
    -- 组合物化后按下标取。用 OFFSET 每行都要扫一遍会让 5 万行退化成 O(n²)
    SELECT comb.product_id, comb.part_id
    FROM (
        SELECT row_number() OVER (ORDER BY pa.product_id, pa.id) - 1 AS k,
               pa.product_id, pa.id AS part_id
        FROM parts pa
        JOIN products pr ON pr.id = pa.product_id
    ) comb
    WHERE comb.k = i % (SELECT count(*) FROM parts pa
                        JOIN products pr ON pr.id = pa.product_id)
    LIMIT 1
) c;
"""

# 50 万条日志：时间散布在过去 90 天，7 成命中。
# 关键点：不能用 OFFSET 随机取故障——50 万行 × 5 万行偏移是 O(n²)，跑不完。
# 压测故障 id 连续（同一批 INSERT），所以用 min(id) + i % count 直接算出来。
SQL_LOGS = """
WITH base AS (
    SELECT min(id) AS lo, count(*) AS cnt
    FROM faults
    WHERE title LIKE '{mark}%' ESCAPE '\\'
),
pick AS (
    SELECT s.i,
           b.lo + (s.i % b.cnt) AS fault_id,
           (s.i % 10 < 7) AS is_hit
    FROM generate_series(1, {n}) AS s(i)
    CROSS JOIN base b
)
INSERT INTO query_logs (
    product_id, part_id, fault_id, raw_query,
    hit, resolved, ip, user_agent, created_at
)
SELECT
    f.product_id,
    f.part_id,
    CASE WHEN p.is_hit THEN f.id ELSE NULL END,
    CASE WHEN p.is_hit THEN NULL
         ELSE '未命中的搜索词 ' || (p.i % 500) END,
    p.is_hit,
    (p.i % 20 = 0),          -- 约 5% 标记为已解决
    '10.0.' || (p.i % 256) || '.' || ((p.i / 256) % 256),
    'pressure-bot/1.0',
    now() - ((p.i % 90) || ' days')::interval
        - ((p.i % 86400) || ' seconds')::interval
FROM pick p
JOIN faults f ON f.id = p.fault_id;
"""

SQL_CLEAN_LOGS = """
DELETE FROM query_logs
WHERE fault_id IN (SELECT id FROM faults WHERE title LIKE '{mark}%' ESCAPE '\\')
   OR (ip LIKE '10.0.%' AND user_agent = 'pressure-bot/1.0');
"""

SQL_CLEAN_FAULTS = """
DELETE FROM faults WHERE title LIKE '{mark}%' ESCAPE '\\';
"""

# 清完之后回收空间，避免压测数据把磁盘撑住
SQL_VACUUM = "VACUUM ANALYZE faults; VACUUM ANALYZE query_logs; VACUUM ANALYZE parts;"


def run_sql(sql: str, *, tuples_only: bool = False) -> str:
    """把 SQL 灌进 db 容器执行。走 stdin，不需要临时文件。"""
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "db",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "fault",
        "-d",
        "fault_db",
    ]
    if tuples_only:
        cmd += ["-t", "-A"]
    proc = subprocess.run(
        cmd, input=sql, text=True, capture_output=True, cwd=str(DEPLOY_DIR)
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"SQL 执行失败（退出码 {proc.returncode}）")
    return proc.stdout


def show_counts(title: str) -> None:
    print(f"\n== {title} ==")
    print(run_sql(SQL_COUNT, tuples_only=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="性能压测造数")
    parser.add_argument(
        "--faults", type=int, default=DEFAULT_FAULTS, help="故障条数（含已有数据）"
    )
    parser.add_argument(
        "--logs", type=int, default=DEFAULT_LOGS, help="查询日志条数"
    )
    parser.add_argument(
        "--per-part",
        type=int,
        default=DEFAULT_PER_PART,
        help=f"每个零件下的故障数（默认 {DEFAULT_PER_PART}）；按此反推要补多少压测零件",
    )
    parser.add_argument("--clean", action="store_true", help="只清理压测数据后退出")
    parser.add_argument("--check", action="store_true", help="只打印行数后退出")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1",
        help="造数后用它做 schema 自检（默认走 nginx）",
    )
    args = parser.parse_args()

    if args.check:
        show_counts("当前行数")
        return

    if args.clean:
        print("清理压测数据…")
        run_sql(SQL_CLEAN_LOGS.format(mark=MARK_LIKE))
        run_sql(SQL_CLEAN_FAULTS.format(mark=MARK_LIKE))
        run_sql(SQL_CLEAN_PARTS.format(mark=MARK_LIKE))
        run_sql(SQL_VACUUM)
        show_counts("清理后行数")
        return

    show_counts("造数前")

    existing = int(
        run_sql(
            "SELECT count(*) FROM faults "
            f"WHERE title LIKE '{MARK_LIKE}%' ESCAPE '\\';",
            tuples_only=True,
        ).strip()
        or 0
    )
    if existing:
        print(
            f"\n检测到已有 {existing} 条压测故障。"
            "如需重新造数请先执行 --clean。"
        )
        return

    # 按「每零件故障数」反推需要的零件数。零件不够就补，否则列表接口
    # 会一次吐出上万行，测出来的延迟不代表真实客户体验。
    current_parts = int(
        run_sql("SELECT count(*) FROM parts;", tuples_only=True).strip() or 0
    )
    need_parts = max(1, args.faults // max(args.per_part, 1))
    if current_parts < need_parts:
        extra = need_parts - current_parts
        print(f"\n补齐压测零件 {extra} 个（当前 {current_parts}，目标 {need_parts}）…")
        run_sql(SQL_PARTS.format(n=extra))
    else:
        print(f"\n零件数 {current_parts} 已够（目标 {need_parts}），不补。")

    print(f"生成 {args.faults} 条故障…")
    run_sql(SQL_FAULTS.format(n=args.faults))

    print(f"生成 {args.logs} 条查询日志…")
    run_sql(SQL_LOGS.format(n=args.logs, mark=MARK_LIKE))

    print("更新统计信息（让查询计划器看到新数据分布）…")
    run_sql(SQL_VACUUM)

    show_counts("造数后")

    # 自检：造出来的数据必须能通过后端 schema 校验。
    # 曾经踩过——solution_steps 写成字符串数组，库里看着正常，
    # 但详情接口 pydantic 校验失败直接 500，压测全红。
    verify_sample(args.base_url)
    print(
        "\n提示：造数后请执行一次 analyze 再压测，"
        "否则 pg 可能仍按旧基数选计划。"
    )


def verify_sample(base_url: str) -> None:
    """抽一条压测故障打详情接口，确认返回 2xx 而不是 500。"""
    import urllib.error
    import urllib.request

    fid = run_sql(
        "SELECT id FROM faults "
        f"WHERE title LIKE '{MARK_LIKE}%' ESCAPE '\\' ORDER BY id LIMIT 1;",
        tuples_only=True,
    ).strip()
    if not fid:
        print("\n[schema 自检] 跳过：没找到压测故障")
        return

    url = f"{base_url.rstrip('/')}/api/faults/{fid}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read(200).decode("utf-8", "replace")
            print(f"\n[schema 自检] OK  {url} -> {resp.status}  {body[:120]}…")
    except urllib.error.HTTPError as exc:
        detail = exc.read(400).decode("utf-8", "replace")
        print(f"\n[schema 自检] 失败 {url} -> {exc.code}  {detail}")
        raise SystemExit(
            "造出来的数据后端读不了（多半是 JSONB 字段结构与 schema 不符），"
            "请先修好再压测，否则压测结果没有意义。"
        )
    except Exception as exc:  # 服务没起来之类
        print(f"\n[schema 自检] 跳过：{type(exc).__name__}: {exc}")


DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy"

if __name__ == "__main__":
    main()
