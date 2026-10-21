#!/usr/bin/env python3
"""测试函数重名检查器。

Python 允许在同一模块里重复定义同名函数，后定义会**静默覆盖**前定义。
对测试文件来说这是个隐形陷阱：被覆盖的用例永远不会执行，
而 pytest 照常收集（按函数名去重）、覆盖率照常是绿的、lint 也不报——
失败的测试会喊，被覆盖的测试永远安静。

真实案例：`backend/tests/test_upload.py` 曾有 3 份完全相同的
`test_ensure_upload_dir_creates_missing`，其中 2 份从未执行。

用法：
    python scripts/dev/check_duplicate_tests.py [--quiet]

退出码：0 无重名；1 存在重名。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SKIP_DIRS = {
    ".git",
    ".workbuddy",
    "node_modules",
    ".venv",
    ".tmp",
    ".pipcache",
    ".npmcache",
    "data",
    "__pycache__",
    "dist",
}

# 只查测试文件：用例名重名在其他代码里通常是刻意覆盖（如 monkeypatch 前的桩），
# 在测试里则一定是写重了。
TEST_GLOB = "test_*.py"


def iter_test_files() -> list[Path]:
    out = []
    for p in ROOT.rglob(TEST_GLOB):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        out.append(p)
    return sorted(out)


def find_duplicates(path: Path) -> list[tuple[str, list[int]]]:
    """返回 [(函数名, [行号...]), ...]，仅保留出现次数 > 1 的。"""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        print(f"  ! 无法解析 {path.relative_to(ROOT)}：{exc}", file=sys.stderr)
        return []

    seen: dict[str, list[int]] = {}
    # 只看模块顶层：类内的方法各自独立命名空间，同名但属于不同类是正常的
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seen.setdefault(node.name, []).append(node.lineno)

    return [(name, lines) for name, lines in seen.items() if len(lines) > 1]


def main() -> int:
    parser = argparse.ArgumentParser(description="检查测试文件里的重名函数")
    parser.add_argument("--quiet", action="store_true", help="只在发现问题时输出")
    args = parser.parse_args()

    files = iter_test_files()
    problems: list[tuple[Path, str, list[int]]] = []
    for path in files:
        for name, lines in find_duplicates(path):
            problems.append((path, name, lines))

    for path, name, lines in problems:
        rel = path.relative_to(ROOT)
        line_list = "、".join(str(n) for n in lines)
        print(f"  ✗ {rel}: `{name}` 定义了 {len(lines)} 次（行 {line_list}）")
        # Python 语义：只有最后一个生效，前面的全部空转
        print(f"      生效的是第 {lines[-1]} 行，其余 {len(lines) - 1} 个从未执行")

    if not args.quiet:
        print()
        print(f"检查 {len(files)} 个测试文件，发现 {len(problems)} 处重名" if problems
              else f"检查 {len(files)} 个测试文件，0 处重名")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
