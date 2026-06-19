"""
模型路由器。

读取 ``config/models.json``，将暴露给外部的模型名（如
``deepseek-deepseek-v4-flash``）解析为 provider + vendor_model。

同时处理模型的启用/禁用、可见性、额外参数注入。

用法::

    router = Router(project_root="/path/to/project")
    result = router.resolve("deepseek-deepseek-v4-flash")
    # → {"provider": "deepseek", "model": "deepseek-v4-flash", ...}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RouterError(Exception):
    """模型路由错误。"""


# endpoint 路径 → 期望的顶层能力
ENDPOINT_CAPABILITY: dict[str, str] = {
    "/v1/chat/completions": "chat",
    "/step_plan/v1/chat/completions": "chat",
    "/v1/audio/speech": "audio",
    "/v1/audio/transcriptions": "audio",
    "/v1/audio/speech-to-speech": "audio",
    "/v1/images/generations": "image",
    "/v1/images/edits": "image",
    "/v1/videos/generations": "video",
    "/v1/embeddings": "embedding",
    "/v1/rerank": "rerank",
}


class Router:
    """模型别名解析器。"""

    def __init__(self, project_root: str | Path = "."):
        self._root = Path(project_root)
        self._models: dict[str, dict[str, Any]] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load(self) -> None:
        """加载 models.json。"""
        path = self._root / "config" / "models.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._models = data
            self._loaded = True
            logger.info("loaded %d model aliases", len(data))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("failed to load models.json: %s", exc)
            raise RouterError(f"models.json load error: {exc}") from exc

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------

    def resolve(self, model_name: str) -> dict[str, Any]:
        """解析暴露模型名 → 路由信息。

        参数
        ----
        model_name : str
            外部模型名，例如 ``deepseek-deepseek-v4-flash``。

        返回
        ----
        dict
            包含 provider / model / capability / endpoint / enabled / visible / extra。
        """
        if not self._loaded:
            self.load()

        if model_name not in self._models:
            raise RouterError(f"unknown model: '{model_name}'")

        entry = self._models[model_name]

        if not entry.get("enabled", True):
            raise RouterError(f"model '{model_name}' is disabled")

        capabilities = self._get_capabilities(entry)

        return {
            "provider": entry["provider"],
            "model": entry["model"],
            "capabilities": capabilities,
            "capability": capabilities[0] if capabilities else "chat",  # 向后兼容
            "endpoint": entry.get("endpoint", "/v1/chat/completions"),
            "enabled": entry.get("enabled", True),
            "visible": entry.get("visible", True),
            "extra": entry.get("extra", {}),
        }

    def resolve_by_endpoint(self, model_name: str, endpoint: str) -> dict[str, Any]:
        """解析模型，并校验 capability 匹配端点。

        如果模型的 capability 不匹配 endpoint 对应的能力，
        抛出 RouterError("capability_mismatch", ...)。
        """
        route = self.resolve(model_name)
        capabilities = route["capabilities"]

        # endpoint → 期望的顶层能力
        expected = ENDPOINT_CAPABILITY.get(endpoint)
        if expected is None:
            # 未知 endpoint，放行(由 handler 自行校验)
            return route

        # 顶层匹配：任一 capability 匹配 endpoint 即可
        if not any(cap.split(".")[0] == expected for cap in capabilities):
            caps_str = ", ".join(capabilities)
            raise RouterError(
                f"model '{model_name}' capabilities [{caps_str}] do not "
                f"support endpoint '{endpoint}' (expected '{expected}.*')"
            )
        return route

    # ------------------------------------------------------------------
    # 列出
    # ------------------------------------------------------------------

    def list_visible(self) -> list[dict[str, Any]]:
        """列出所有对外可见的模型。"""
        if not self._loaded:
            self.load()

        result: list[dict[str, Any]] = []
        for name, entry in self._models.items():
            if entry.get("visible", True):
                capabilities = self._get_capabilities(entry)
                item = {
                    "id": name,
                    "provider": entry["provider"],
                    "model": entry["model"],
                    "capabilities": capabilities,
                    "capability": capabilities[0] if capabilities else "chat",
                    "endpoint": entry.get("endpoint", "/v1/chat/completions"),
                }
                if entry.get("modalities"):
                    item["modalities"] = entry["modalities"]
                result.append(item)
        return result

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有模型（含不可见）。"""
        if not self._loaded:
            self.load()

        result: list[dict[str, Any]] = []
        for name, entry in self._models.items():
            capabilities = self._get_capabilities(entry)
            item = {
                "id": name,
                "provider": entry["provider"],
                "model": entry["model"],
                "capabilities": capabilities,
                "capability": capabilities[0] if capabilities else "chat",
                "endpoint": entry.get("endpoint", "/v1/chat/completions"),
                "enabled": entry.get("enabled", True),
                "visible": entry.get("visible", True),
            }
            if entry.get("modalities"):
                item["modalities"] = entry["modalities"]
            result.append(item)
        return result

    def _get_capabilities(self, entry: dict[str, Any]) -> list[str]:
        """归一化能力字段：支持新的 'capabilities' 数组和旧的 'capability' 单值。"""
        if "capabilities" in entry:
            return entry["capabilities"]
        if "capability" in entry:
            return [entry["capability"]]
        return ["chat"]
        """获取模型的 extra 参数（如 thinking / reasoning_effort）。"""
        if not self._loaded:
            self.load()
        return self._models.get(model_name, {}).get("extra", {})
