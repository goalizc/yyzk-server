#!/usr/bin/env python3
"""生成演示数据（产品/零件/故障/附件），用于前端联调与验收演示。

幂等：按产品型号判断，已存在则跳过。
用法：
    python scripts/dev/seed_demo.py [--base-url http://127.0.0.1] [--reset]
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import httpx

PRODUCTS = [
    {
        "name": "智能扫地机器人",
        "model": "X1",
        "category": "扫地机",
        "description": "家用激光导航扫拖一体机",
        "sort_order": 1,
        "parts": [
            # sort_order 决定客户侧下拉里的展示顺序：动力 → 清洁 的排查习惯
            {"name": "主刷模组", "part_no": "P-X1-001", "group_name": "动力系统", "sort_order": 1},
            {"name": "电源模组", "part_no": "P-X1-003", "group_name": "动力系统", "sort_order": 2},
            {"name": "水箱模组", "part_no": "P-X1-002", "group_name": "清洁系统", "sort_order": 3},
        ],
        "faults": [
            {
                "part": "主刷模组",
                "title": "主刷不转动",
                "symptom": "开机后主刷不转，机器原地不动或反复重启",
                "root_cause": "主刷被毛发缠绕 / 主刷卡扣未到位 / 主刷电机故障",
                "steps": [
                    "翻转机器，取下主刷盖，检查主刷两端是否有毛发缠绕",
                    "清理缠绕物后重新装回，确认两端卡扣卡紧并听到“咔哒”声",
                    "开机观察 10 秒，若仍不转，提交工单由工程师跟进更换主刷电机",
                ],
                "tools": "十字螺丝刀、剪刀",
                "needs_professional": False,
            },
            {
                "part": "水箱模组",
                "title": "拖地不出水",
                "symptom": "水箱有水但拖地时地面不出水，或出水很小",
                "root_cause": "水箱滤网堵塞 / 出水孔堵塞 / 水箱未卡到位",
                "steps": [
                    "取下抹布支架，检查水箱出水孔是否被水垢堵住",
                    "取出滤网用清水冲洗，晾干后装回",
                    "重新安装水箱，确认卡到位（听到“咔哒”声）",
                ],
                "tools": "清水、软毛刷",
                "needs_professional": False,
            },
            {
                "part": "电源模组",
                "title": "充电时指示灯不亮",
                "symptom": "放回充电座后指示灯不亮，机器不充电",
                "root_cause": "电源适配器损坏 / 充电电极接触不良 / 电池老化",
                "steps": [
                    "检查适配器指示灯是否亮起，不亮则更换同规格适配器测试",
                    "用干布擦拭机器与充电座的充电电极",
                    "仍无法充电时请勿自行拆机，提交工单由工程师安排电池检测",
                ],
                "tools": "干布",
                "needs_professional": True,
            },
            {
                "part": "水箱模组",
                "title": "拖地后地面有明显水痕",
                "symptom": "拖完地地面湿滑，长时间不干",
                "root_cause": "出水过大 / 抹布过湿 / 水箱密封圈老化",
                "steps": [
                    "在 App 中把出水量调至“低”档",
                    "取下抹布拧干后再装回",
                    "检查水箱密封圈是否变形，变形需更换",
                ],
                "tools": "无",
                "needs_professional": False,
            },
        ],
    },
    {
        "name": "空气净化器",
        "model": "A2",
        "category": "净化器",
        "description": "卧室用除甲醛空气净化器",
        "sort_order": 2,
        "parts": [
            {"name": "滤芯", "part_no": "P-A2-001", "group_name": "过滤系统", "sort_order": 1},
            {"name": "风机", "part_no": "P-A2-002", "group_name": "动力系统", "sort_order": 2},
        ],
        "faults": [
            {
                "part": "滤芯",
                "title": "滤芯更换提示不消失",
                "symptom": "已更换新滤芯，但面板仍提示更换滤芯",
                "root_cause": "滤芯复位未执行 / 滤芯未识别",
                "steps": [
                    "长按“复位”键 5 秒，听到提示音后松手",
                    "确认滤芯型号与机器匹配，重新装入并盖紧滤芯仓",
                    "若仍提示，断电 1 分钟后重新上电",
                ],
                "tools": "无",
                "needs_professional": False,
            },
            {
                "part": "风机",
                "title": "运行时噪音明显变大",
                "symptom": "夜间模式下仍能听到明显风噪或异响",
                "root_cause": "进风口堵塞 / 风机积尘 / 风机轴承磨损",
                "steps": [
                    "检查进风口是否有异物遮挡，清理周围 30cm 空间",
                    "取下滤芯，用吸尘器清理风机叶片积尘",
                    "异响持续时提交工单，由工程师判断是否需更换风机",
                ],
                "tools": "吸尘器",
                "needs_professional": False,
            },
        ],
    },
]


def api(base: str, token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base, headers=headers, timeout=30.0)


def login(base: str) -> str:
    password = os.getenv("ADMIN_INIT_PASSWORD")
    if not password:
        env_path = os.path.join(os.path.dirname(__file__), "../../deploy/.env")
        try:
            text = open(env_path, encoding="utf-8").read()
            password = re.search(r"^ADMIN_INIT_PASSWORD=(.*)$", text, re.M).group(1).strip()
        except Exception:
            print("[seed] 需要 ADMIN_INIT_PASSWORD 环境变量或 deploy/.env", file=sys.stderr)
            raise SystemExit(2)

    with api(base) as client:
        resp = client.post("/api/auth/login", json={"username": "admin", "password": password})
        if resp.status_code != 200:
            print(f"[seed] 登录失败：{resp.status_code} {resp.text[:120]}", file=sys.stderr)
            raise SystemExit(1)
        return resp.json()["access_token"]


def upload_demo_pdf(client: httpx.Client) -> str | None:
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    files = {"file": ("X1 使用手册.pdf", pdf, "application/pdf")}
    resp = client.post("/api/admin/upload", files=files)
    if resp.status_code != 200:
        print(f"[seed] 附件上传失败（跳过附件）：{resp.status_code} {resp.text[:100]}")
        return None
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成演示数据")
    parser.add_argument("--base-url", default="http://127.0.0.1")
    args = parser.parse_args()

    token = login(args.base_url)
    created = {"products": 0, "parts": 0, "faults": 0}

    with api(args.base_url, token) as client:
        existing = {
            item["model"]
            for item in client.get("/api/admin/products", params={"page_size": 100}).json()["items"]
        }

        for spec in PRODUCTS:
            if spec["model"] in existing:
                print(f"[seed] 产品 {spec['model']} 已存在，跳过")
                continue

            product = client.post(
                "/api/admin/products",
                json={key: spec[key] for key in ("name", "model", "category", "description", "sort_order")},
            ).json()
            created["products"] += 1

            part_ids: dict[str, int] = {}
            for part in spec["parts"]:
                row = client.post("/api/admin/parts", json={"product_id": product["id"], **part}).json()
                part_ids[part["name"]] = row["id"]
                created["parts"] += 1

            for fault in spec["faults"]:
                payload = {
                    "product_id": product["id"],
                    "part_id": part_ids[fault["part"]],
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
                client.post("/api/admin/faults", json=payload)
                created["faults"] += 1

        # 给第一条故障挂一个附件，用于验证详情页附件区
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

    print(
        f"[seed] 完成：产品 {created['products']}、零件 {created['parts']}、故障 {created['faults']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
