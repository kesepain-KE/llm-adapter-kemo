#!/usr/bin/env python3
"""
VOTX LLM Adapter — API Server entry point.

启动::

    python server.py
    python server.py --port 8741 --host 0.0.0.0
    uvicorn api.app:app --host 0.0.0.0 --port 8741
"""

from __future__ import annotations

if __name__ == "__main__":
    import argparse
    import os
    import uvicorn

    # ── 启动前置 ──────────────────────────────────────────────
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 加载 provider.env
    env_file = "provider.env"
    if os.path.isfile(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                m = line.strip().split("=", 1)
                if len(m) == 2 and not line.lstrip().startswith("#"):
                    os.environ.setdefault(m[0].strip(), m[1].strip())
        print("[votx] loaded provider.env")

    # 创建运行数据目录
    os.makedirs("data_status/call_log", exist_ok=True)

    # ── 启动服务 ──────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="VOTX LLM Adapter Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8741)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
