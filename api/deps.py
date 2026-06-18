"""依赖注入 — 项目根路径 + AppContext。"""

from __future__ import annotations

import sys
from pathlib import Path

# 项目根 = api/ 的父目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 确保根在 sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_ctx = None


def get_ctx():
    """懒加载 AppContext，首次调用时 bootstrap。"""
    global _ctx
    if _ctx is None:
        from core import bootstrap
        _ctx = bootstrap(str(PROJECT_ROOT))
    return _ctx
