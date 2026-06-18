"""
DeepSeek provider 包入口。

对外暴露：
- DeepSeekChat   —— 聊天适配器
- DeepSeekTokenCount —— Token 统计器
- create_chat / create_token_count —— 工厂函数
"""

from __future__ import annotations

from .chat import DeepSeekChat
from .token_count import DeepSeekTokenCount

__all__ = [
    "DeepSeekChat",
    "DeepSeekTokenCount",
    "create_chat",
    "create_token_count",
]


def create_chat(config: dict | None = None) -> DeepSeekChat:
    """工厂：根据 model.json 配置创建聊天适配器实例。

    参数
    ----
    config : dict | None
        model.json 的内容。为 None 时使用默认配置。

    返回
    ----
    DeepSeekChat
    """
    return DeepSeekChat(config=config)


def create_token_count(config: dict | None = None) -> DeepSeekTokenCount:
    """工厂：创建 Token 统计器实例。

    参数
    ----
    config : dict | None
        model.json 的内容。当前仅用于签名统一，
        Token 统计器不依赖 provider 配置。

    返回
    ----
    DeepSeekTokenCount
    """
    return DeepSeekTokenCount()
