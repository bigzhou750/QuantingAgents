#!/usr/bin/env python3
"""后端构建自检：验证发布镜像中的包路径、CLI 入口和核心模块可导入。"""

from __future__ import annotations

import sys


def main() -> int:
    checks = [
        ("tradingagents package", "import tradingagents"),
        ("graph entrypoint", "from tradingagents.graph.trading_graph import zhitouagentGraph"),
        ("cli entrypoint", "from cli.main import main"),
    ]
    for name, code in checks:
        try:
            exec(code, {})
            print(f"PASS {name}")
        except Exception as exc:  # pragma: no cover - failure path only
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            return 1
    print("PASS backend build self-check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
