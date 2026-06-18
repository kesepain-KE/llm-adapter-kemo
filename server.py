#!/usr/bin/env python3
"""
Kemo LLM Adapter — API Server entry point.

启动::

    python server.py
    python server.py --port 8000 --host 0.0.0.0
    uvicorn api.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

if __name__ == "__main__":
    import argparse
    import os
    import uvicorn

    parser = argparse.ArgumentParser(description="Kemo LLM Adapter Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
