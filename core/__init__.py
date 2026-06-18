"""
Kemo LLM Adapter Core — 多厂商 LLM 统一适配层。

核心模块::

    core.registry   — 扫描 provider/*/model.json，加载模块
    core.router     — 解析暴露模型名 → provider + model
    core.auth       — API 密钥鉴权 + 模型白名单
    core.call_log   — 统一调用日志 (每次请求一条，全量统计字段)
    core.usage      — Token 统计归一化 + 汇总查询

快速使用::

    from core import bootstrap
    ctx = bootstrap("/path/to/project")
    key_info = ctx.auth.authenticate(token, model)
    route = ctx.router.resolve(model)
    chat = ctx.registry.get_chat(route["provider"])
    response = await chat.invoke(request)
    usage = ctx.usage.count(route["provider"], response)
    ctx.call_log.log(key_id=..., provider=..., model=..., usage=usage, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .auth import AuthManager, AuthError
from .router import Router, RouterError
from .registry import Registry
from .call_log import CallLogger
from .usage import UsageManager

__all__ = [
    "bootstrap",
    "AppContext",
    "AuthManager",
    "AuthError",
    "Router",
    "RouterError",
    "Registry",
    "CallLogger",
    "UsageManager",
]


@dataclass
class AppContext:
    """应用上下文：持有所有 core 模块实例。"""

    project_root: str
    registry: Registry = field(default_factory=Registry)
    router: Router = field(default_factory=Router)
    auth: AuthManager = field(default_factory=AuthManager)
    call_log: CallLogger = field(default_factory=CallLogger)
    usage: UsageManager = field(default_factory=UsageManager)


def bootstrap(project_root: str | Path = ".") -> AppContext:
    """一键初始化所有 core 模块。

    加载顺序：
      1. registry → 扫描 provider 目录
      2. router   → 加载 models.json
      3. auth     → 加载 api_keys.json
      4. call_log / usage → 绑定调用日志

    参数
    ----
    project_root : str | Path
        项目根目录。

    返回
    ----
    AppContext
        持有所有已初始化模块的上下文。
    """
    root = Path(project_root)

    registry = Registry(root)
    registry.load_all()

    router = Router(root)
    router.load()

    auth = AuthManager(root)
    auth.load()

    call_log = CallLogger(root)

    usage = UsageManager(root, registry=registry)
    usage.bind_call_log(call_log)

    return AppContext(
        project_root=str(root),
        registry=registry,
        router=router,
        auth=auth,
        call_log=call_log,
        usage=usage,
    )
