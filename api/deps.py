"""依赖注入 — 项目根路径 + AppContext。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 自举：先把项目根加入 sys.path，确保 path.py 可导入
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from path import PROJECT_ROOT  # 统一入口，不再自己算

_ctx = None


def load_provider_env() -> None:
    """加载 provider.env 到进程环境，已有环境变量不覆盖。"""
    env_path = PROJECT_ROOT / "provider.env"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_provider_env()


def get_ctx():
    """懒加载 AppContext，首次调用时 bootstrap。"""
    global _ctx
    if _ctx is None:
        from core import bootstrap
        _ctx = bootstrap(str(PROJECT_ROOT))
    return _ctx


async def close_ctx() -> None:
    """Close the lazily-created application context without creating one."""
    global _ctx
    ctx = _ctx
    _ctx = None
    if ctx is not None:
        await ctx.aclose()
