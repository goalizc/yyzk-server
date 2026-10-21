#!/usr/bin/env python3
"""性能压测脚本（TC-70 / TC-71）。

验收口径（需求 §性能）：
  TC-70  列表/详情接口 P95 < 500ms
  TC-71  100 并发持续 10 分钟，无 5xx

设计说明
--------
* 走 nginx（默认 http://127.0.0.1），即真实链路「客户端 → nginx → backend」，
  而不是直连 backend 容器，否则测不到 nginx 的代理层。
* 混合场景而非单一接口：列表 55%、详情 30%、健康检查 15%，
  接近客户实际排查时的点击分布；详情接口每次都会写 query_logs 并自增 view_count，
  是本次压测的主要写入压力来源。
* 只统计成功计入吞吐的请求；4xx 单独归类（详情接口 404 属正常，不计为故障），
  5xx 与网络异常一律视为失败并计入退出码。
* 结束时按耗时排序取真实百分位，不做近似。

用法：
    python scripts/dev/load_test.py                        # 默认：100 并发 / 600 秒
    python scripts/dev/load_test.py -c 20 -d 60            # 快速冒烟
    python scripts/dev/load_test.py -c 100 -d 600 --json out.json

退出码：0 = 达标；1 = 未达标（有 5xx 或 P95 超线）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# ---------------------------------------------------------------- 阈值

P95_LIMIT_MS = 500.0  # TC-70
P99_LIMIT_MS = 1500.0  # 内部参考线，不作为验收项
ERROR_RATE_LIMIT = 0.0  # TC-71：5xx 必须为 0


# ---------------------------------------------------------------- 结果容器


@dataclass
class Sample:
    """单次请求的结果。latency 单位毫秒。"""

    path: str
    status: int
    latency_ms: float
    error: str | None = None


@dataclass
class Recorder:
    samples: list[Sample] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    started_at: float = 0.0
    finished_at: float = 0.0

    async def add(self, s: Sample) -> None:
        async with self.lock:
            self.samples.append(s)


# ---------------------------------------------------------------- 场景


@dataclass
class Target:
    """压测目标：一组 product/part 组合 + 若干已发布故障 id。"""

    base_url: str
    pairs: list[tuple[int, int]]
    fault_ids: list[int]
    terms: list[str]


async def discover(client: httpx.AsyncClient, base_url: str) -> Target:
    """探测可用的 product/part/fault，避免写死 id 让脚本换个库就跑不了。"""
    resp = await client.get(f"{base_url}/api/products")
    resp.raise_for_status()
    products = resp.json()
    if not products:
        raise SystemExit("库里没有已上架产品，无法压测。请先执行 seed_pressure.py。")

    pairs: list[tuple[int, int]] = []
    fault_ids: list[int] = []
    for p in products[:5]:
        r = await client.get(f"{base_url}/api/products/{p['id']}/parts")
        if r.status_code != 200:
            continue
        for part in r.json()[:5]:
            pairs.append((p["id"], part["id"]))
            fr = await client.get(
                f"{base_url}/api/faults",
                params={"product_id": p["id"], "part_id": part["id"]},
            )
            if fr.status_code == 200:
                fault_ids.extend(f["id"] for f in fr.json()[:20])

    if not pairs:
        raise SystemExit("找不到任何 product/part 组合，无法压测。")
    if not fault_ids:
        raise SystemExit("找不到已发布故障，无法压测详情接口。")

    # 去重但保持顺序，让请求分布更均匀
    fault_ids = list(dict.fromkeys(fault_ids))
    return Target(
        base_url=base_url.rstrip("/"),
        pairs=pairs,
        fault_ids=fault_ids,
        terms=["异响", "不转动", "闪烁", "不出水", "无法开机"],
    )


async def worker(
    client: httpx.AsyncClient,
    target: Target,
    rec: Recorder,
    stop_at: float,
    rng: random.Random,
) -> None:
    """单个虚拟用户：按配比循环发请求，直到时间到。"""
    local: list[Sample] = []
    while time.monotonic() < stop_at:
        roll = rng.random()
        if roll < 0.55:
            # 列表：最热路径，带关键词的占一半
            pid, ptid = rng.choice(target.pairs)
            params: dict[str, object] = {"product_id": pid, "part_id": ptid}
            if rng.random() < 0.5:
                params["q"] = rng.choice(target.terms)
            path = "/api/faults"
            url = f"{target.base_url}{path}"
        elif roll < 0.85:
            fid = rng.choice(target.fault_ids)
            path = "/api/faults/{id}"
            url = f"{target.base_url}/api/faults/{fid}"
            params = {}
        else:
            path = "/api/health"
            url = f"{target.base_url}{path}"
            params = {}

        t0 = time.perf_counter()
        try:
            r = await client.get(url, params=params)
            elapsed = (time.perf_counter() - t0) * 1000
            local.append(Sample(path=path, status=r.status_code, latency_ms=elapsed))
        except Exception as exc:  # 网络层异常单独归为 error
            elapsed = (time.perf_counter() - t0) * 1000
            local.append(
                Sample(
                    path=path,
                    status=0,
                    latency_ms=elapsed,
                    error=f"{type(exc).__name__}: {exc}"[:200],
                )
            )

        # 攒一批再入锁，减少锁竞争对测量本身的干扰
        if len(local) >= 20:
            async with rec.lock:
                rec.samples.extend(local)
            local = []

    if local:
        async with rec.lock:
            rec.samples.extend(local)


# ---------------------------------------------------------------- 统计


def percentile(sorted_values: list[float], p: float) -> float:
    """按真实排序取分位（nearest-rank），不插值，结果更贴近运维口径。"""
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, int(round(p / 100 * len(sorted_values))) - 1))
    return sorted_values[k]


def summarize(rec: Recorder, concurrency: int, duration: float) -> dict:
    samples = rec.samples
    elapsed = max(rec.finished_at - rec.started_at, 0.001)

    by_path: dict[str, list[Sample]] = {}
    for s in samples:
        by_path.setdefault(s.path, []).append(s)

    def stats(items: list[Sample]) -> dict:
        ok = [s for s in items if 200 <= s.status < 400]
        lats = sorted(s.latency_ms for s in ok)
        return {
            "count": len(items),
            "ok": len(ok),
            "lat_p50": round(percentile(lats, 50), 1),
            "lat_p95": round(percentile(lats, 95), 1),
            "lat_p99": round(percentile(lats, 99), 1),
            "lat_max": round(max(lats), 1) if lats else 0.0,
            "status_hist": _hist(items),
        }

    all_ok = [s for s in samples if 200 <= s.status < 400]
    all_lats = sorted(s.latency_ms for s in all_ok)
    server_errors = [s for s in samples if s.status >= 500]
    net_errors = [s for s in samples if s.status == 0]

    return {
        "concurrency": concurrency,
        "duration_s": round(elapsed, 1),
        "total_requests": len(samples),
        "ok_requests": len(all_ok),
        "qps": round(len(samples) / elapsed, 1),
        "ok_qps": round(len(all_ok) / elapsed, 1),
        "lat_p50": round(percentile(all_lats, 50), 1),
        "lat_p95": round(percentile(all_lats, 95), 1),
        "lat_p99": round(percentile(all_lats, 99), 1),
        "lat_max": round(max(all_lats), 1) if all_lats else 0.0,
        "lat_mean": round(statistics.fmean(all_lats), 1) if all_lats else 0.0,
        "status_hist": _hist(samples),
        "server_errors": len(server_errors),
        "network_errors": len(net_errors),
        "error_rate": round(len(server_errors) / max(len(samples), 1) * 100, 3),
        "error_samples": [
            {"path": s.path, "status": s.status, "error": s.error}
            for s in (server_errors + net_errors)[:10]
        ],
        "by_path": {p: stats([s for s in v]) for p, v in sorted(by_path.items())},
    }


def _hist(items: list[Sample]) -> dict[str, int]:
    hist: dict[str, int] = {}
    for s in items:
        key = str(s.status) if s.status else "network"
        hist[key] = hist.get(key, 0) + 1
    return dict(sorted(hist.items()))


# ---------------------------------------------------------------- 主流程


async def run(args: argparse.Namespace) -> int:
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=30.0)
    limits = httpx.Limits(
        max_connections=args.concurrency + 50,
        max_keepalive_connections=args.concurrency + 50,
    )

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        target = await discover(client, args.base_url)
        print(f"压测目标: {target.base_url}")
        print(f"product/part 组合: {len(target.pairs)} 个")
        print(f"已发布故障: {len(target.fault_ids)} 条")
        print(f"并发: {args.concurrency}   时长: {args.duration}s")
        print("场景配比: 列表 55% / 详情 30% / 健康检查 15%")
        print("-" * 62)

    rec = Recorder()
    stop_at = time.monotonic() + args.duration

    # 每个 worker 独立连接池，避免共享 session 造成测量噪声
    async def one(ii: int) -> None:
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=4)
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as c:
            await worker(c, target, rec, stop_at, random.Random(hash(ii) & 0xFFFF))

    rec.started_at = time.monotonic()
    await asyncio.gather(*(one(i) for i in range(args.concurrency)))
    rec.finished_at = time.monotonic()

    report = summarize(rec, args.concurrency, args.duration)

    print(f"\n总请求   : {report['total_requests']}  有效 {report['ok_requests']}")
    print(f"吞吐     : {report['qps']} req/s（有效 {report['ok_qps']}）")
    print(
        f"延迟(ms) : P50 {report['lat_p50']}  P95 {report['lat_p95']}  "
        f"P99 {report['lat_p99']}  max {report['lat_max']}  mean {report['lat_mean']}"
    )
    print(f"状态分布 : {report['status_hist']}")
    print(
        f"错误     : 5xx {report['server_errors']}  网络 {report['network_errors']}"
        f"  错误率 {report['error_rate']}%"
    )

    print("\n按接口拆分：")
    for path, st in report["by_path"].items():
        print(
            f"  {path:<22} n={st['count']:<7} p50={st['lat_p50']:<7} "
            f"p95={st['lat_p95']:<7} p99={st['lat_p99']:<7} max={st['lat_max']:<7} "
            f"{st['status_hist']}"
        )

    # ---------------- 判定 ----------------
    print("\n" + "=" * 62)
    failures: list[str] = []
    if report["lat_p95"] <= P95_LIMIT_MS:
        print(f"[PASS] TC-70  P95 {report['lat_p95']}ms <= {P95_LIMIT_MS}ms")
    else:
        print(f"[FAIL] TC-70  P95 {report['lat_p95']}ms > {P95_LIMIT_MS}ms")
        failures.append("TC-70 P95 超线")

    if report["server_errors"] == 0 and report["network_errors"] == 0:
        print(f"[PASS] TC-71  {args.concurrency} 并发 {report['duration_s']}s 无 5xx/网络错误")
    else:
        print(
            f"[FAIL] TC-71  5xx {report['server_errors']} / 网络 {report['network_errors']}"
        )
        failures.append("TC-71 出现错误")

    for path, st in report["by_path"].items():
        if st["lat_p95"] > P95_LIMIT_MS:
            print(f"[WARN] {path} 单独看 P95={st['lat_p95']}ms 超线")

    if report["error_samples"]:
        print("\n错误样本（前 10 条）：")
        for e in report["error_samples"]:
            print(f"  {e}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n明细已写入 {out}")

    return 0 if not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="性能压测（TC-70 / TC-71）")
    parser.add_argument(
        "-c", "--concurrency", type=int, default=100, help="并发数（默认 100）"
    )
    parser.add_argument(
        "-d", "--duration", type=int, default=600, help="持续秒数（默认 600 = 10 分钟）"
    )
    parser.add_argument(
        "--base-url", default="http://127.0.0.1", help="默认走 nginx: http://127.0.0.1"
    )
    parser.add_argument("--json", default="", help="把汇总结果写入 JSON 文件")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
