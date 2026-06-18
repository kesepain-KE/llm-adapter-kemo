"""
add_diy — 新厂商接入工具包。

只提供最小脚手架和连通测试，不做自动探测/注册。
厂商 API 千差万别，适配逻辑交给调用方的 agent 处理。

用法::

    from add_diy import scaffold, ConnectivityTest

    # 生成样板
    created = scaffold("minimax", base_url="https://api.minimax.com")

    # 测试连通
    import asyncio
    t = ConnectivityTest(provider_dir="provider/minimax")
    ok, err, resp = asyncio.run(t.test_chat(api_key="$KEY"))
"""

from __future__ import annotations

from .scaffold import scaffold
from .test import ConnectivityTest

__all__ = [
    "scaffold",
    "ConnectivityTest",
]
