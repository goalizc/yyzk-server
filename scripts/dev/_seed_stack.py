#!/usr/bin/env python3
"""双栈演示数据目标校验（审查报告 21 · C-01）。

seed_demo.py / demo_inventory.py 有两条彼此独立的写入通道：

  - API 通道：--base-url 决定演示数据写进哪个栈
  - DB  通道：docker compose exec db 决定 --reset / --activity / --verify
              的 SQL 在哪个库里执行

两者错配会造成「TRUNCATE 了生产库，数据却写进测试栈」。历史上默认
SEED_ENV_FILE=deploy/.env、SEED_COMPOSE_PROJECT 为空，而 docker compose 不带
-p 时项目名就是 deploy（生产栈），所以「只把 --base-url 改成 :8080」是
最容易踩中的危险路径。

本模块以 SEED_ENV_FILE 为唯一真源：
  1. 从 env 文件读 HTTP_PORT / STACK_PREFIX，判定目标是生产栈还是测试栈；
  2. 校验 --base-url 的端口与该栈匹配，不匹配直接退出；
  3. 测试栈下自动补齐 SEED_COMPOSE_PROJECT 与 SEED_COMPOSE_ENV_FILE，
     避免「只设了 env 文件、漏了项目名」造成另一种错配；
  4. 任何写库发生前，打印一次目标栈摘要，让人一眼看清会动哪个库。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# 生产 .env 允许的 API 端口：80 = nginx，8000 = 本机 uvicorn（同一套 DB）
PROD_PORTS = {80, 8000}
PROD_STACK_PREFIX = "fault"


def _read_env(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    return dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.M))


def guard_target_stack(
    base_url: str,
    env_file: Path,
    compose_project: str,
    compose_env_file: str,
    label: str = "seed",
) -> tuple[str, str]:
    """校验目标栈一致性，返回 (compose 项目名, --env-file 值)。

    compose 项目名返回空字符串表示「不传 -p」，即 compose 默认项目名 deploy
    （与 deploy.sh 的生产栈一致）。不一致时打印中文说明并以退出码 2 终止。
    """
    if not env_file.is_file():
        print(f"[{label}] 环境变量文件不存在：{env_file}", file=sys.stderr)
        raise SystemExit(2)

    env = _read_env(env_file)
    try:
        http_port = int(env.get("HTTP_PORT") or 80)
    except ValueError:
        http_port = 80
    stack_prefix = env.get("STACK_PREFIX") or PROD_STACK_PREFIX
    is_test = stack_prefix != PROD_STACK_PREFIX

    parsed = urlparse(base_url)
    try:
        port = parsed.port
    except ValueError:
        port = None
    # 不带端口时 urlparse 返回 None，必须显式折算成默认端口再比较：
    # 否则「测试栈 env + --base-url http://127.0.0.1」会绕过检查，
    # 变成「清库在测试栈、写数据进生产 80」的反向错配。
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    allowed = {http_port} | (set() if is_test else PROD_PORTS)
    if port not in allowed:
        print(
            f"[{label}] 拒绝执行：--base-url 的端口 {port} 与 {env_file.name} 的 "
            f"HTTP_PORT={http_port} 不匹配。\n"
            "  API 目标与清库目标可能落在不同栈，--reset 会清空错误的数据库。\n"
            "  测试栈请同时设置：\n"
            "    SEED_ENV_FILE=deploy/.env.test SEED_COMPOSE_PROJECT=fault-test \\\n"
            "    SEED_COMPOSE_ENV_FILE=deploy/.env.test \\\n"
            "    --base-url http://127.0.0.1:8080\n"
            "  生产栈请用默认 --base-url（:80 / :8000）且不设 SEED_COMPOSE_PROJECT。",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if is_test:
        # 自动补齐项目名与 env-file：只设 SEED_ENV_FILE 也不至于把 SQL 打到生产库
        if compose_project and compose_project != stack_prefix:
            print(
                f"[{label}] 拒绝执行：SEED_COMPOSE_PROJECT={compose_project} 与 "
                f"{env_file.name} 的 STACK_PREFIX={stack_prefix} 不一致。",
                file=sys.stderr,
            )
            raise SystemExit(2)
        project = compose_project or stack_prefix
        compose_env = compose_env_file or str(env_file)
        if not compose_project:
            print(f"[{label}] 已按 {env_file.name} 自动绑定测试栈项目 {project}")
    else:
        if compose_project and compose_project not in ("", "deploy"):
            print(
                f"[{label}] 拒绝执行：当前是生产 env（{env_file.name}），却指定了 "
                f"SEED_COMPOSE_PROJECT={compose_project}；清库目标会落到测试栈。",
                file=sys.stderr,
            )
            raise SystemExit(2)
        project = ""  # 空 = compose 默认项目名 deploy
        compose_env = compose_env_file

    db_user = env.get("DB_USER", "?")
    db_name = env.get("DB_NAME", "?")
    print(
        f"[{label}] 目标栈确认：API={base_url} | "
        f"compose 项目={project or 'deploy(默认)'} | "
        f"DB={db_user}@{db_name} | env={env_file.name}"
    )
    return project, compose_env
