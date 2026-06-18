"""
StepFun provider 包入口。

对外暴露：
- StepFunChat         —— 聊天适配器
- StepFunTokenCount   —— Token 统计器
- StepFunAudio        —— 音频适配器 (TTS / ASR)
- StepFunImage        —— 图像适配器
- create_chat / create_token_count / create_audio / create_image —— 工厂函数
"""

from __future__ import annotations

from .chat import StepFunChat
from .token_count import StepFunTokenCount
from .audio import StepFunAudio
from .image import StepFunImage

__all__ = [
    "StepFunChat",
    "StepFunTokenCount",
    "StepFunAudio",
    "StepFunImage",
    "create_chat",
    "create_token_count",
    "create_audio",
    "create_image",
]


def create_chat(config: dict | None = None) -> StepFunChat:
    """工厂：根据 model.json 配置创建聊天适配器实例。"""
    return StepFunChat(config=config)


def create_token_count(config: dict | None = None) -> StepFunTokenCount:
    """工厂：创建 Token 统计器实例。"""
    return StepFunTokenCount()


def create_audio(config: dict | None = None) -> StepFunAudio:
    """工厂：创建音频适配器实例。"""
    return StepFunAudio(config=config)


def create_image(config: dict | None = None) -> StepFunImage:
    """工厂：创建图像适配器实例。"""
    return StepFunImage(config=config)
