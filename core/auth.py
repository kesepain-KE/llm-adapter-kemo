"""
API 鉴权模块。

读取 ``config/api_keys.json``，校验 Bearer token：
  1. 密钥是否存在
  2. 密钥是否启用
  3. 请求的模型是否在该密钥的模型白名单中

返回密钥元信息，供后续日志 / 用量模块使用。

用法::

    auth = AuthManager(project_root="/path/to/project")
    key_info = auth.authenticate("sk-kemo-admin", "deepseek-deepseek-v4-flash")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from collections.abc import Callable

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """鉴权失败。"""


class KeyNotFoundError(AuthError):
    """密钥不存在。"""


class KeyDisabledError(AuthError):
    """密钥已被禁用。"""


class ModelNotAllowedError(AuthError):
    """模型不在密钥的白名单中。"""


from .usage import QuotaExceededError


# ---------------------------------------------------------------------------
# 鉴权管理器
# ---------------------------------------------------------------------------


class AuthManager:
    """API 密钥鉴权。"""

    def __init__(self, project_root: str | Path = "."):
        self._root = Path(project_root)
        self._keys: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._file_signature: tuple[int, int] | None = None
        self._quota_reader: Callable[[str, int], int] | None = None

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load(self, force: bool = False) -> None:
        """加载 api_keys.json。"""
        path = self._root / "config" / "api_keys.json"
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if self._loaded and not force and signature == self._file_signature:
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            self._keys = data.get("keys", {})
            self._loaded = True
            self._file_signature = signature
            logger.info("loaded %d API keys", len(self._keys))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("failed to load api_keys.json: %s", exc)
            raise AuthError(f"api_keys.json load error: {exc}") from exc

    def bind_quota_reader(self, reader: Callable[[str, int], int]) -> None:
        self._quota_reader = reader

    # ------------------------------------------------------------------
    # 鉴权
    # ------------------------------------------------------------------

    def authenticate(
        self, token: str, model: str
    ) -> dict[str, Any]:
        """校验 Bearer token 并返回密钥信息。

        参数
        ----
        token : str
            请求中的 Bearer token。
        model : str
            暴露模型名，如 ``deepseek-deepseek-v4-flash``。

        返回
        ----
        dict
            密钥信息: id / name / enabled / models / quota
        """
        # 每次鉴权都重新加载，支持 api_keys.json 热修改
        self.load()

        # 1. 查找密钥
        if token not in self._keys:
            raise KeyNotFoundError(f"invalid API key: {token[:12]}...")

        key_info = self._keys[token]

        # 2. 检查启用
        if not key_info.get("enabled", True):
            raise KeyDisabledError(
                f"API key '{key_info.get('name', token[:12])}' is disabled"
            )

        # 3. 检查模型白名单
        allowed_models: list[str] = key_info.get("models", [])
        if model not in allowed_models:
            raise ModelNotAllowedError(
                f"model '{model}' not allowed for key "
                f"'{key_info.get('name', token[:12])}'"
            )

        # 4. 检查额度
        quota = key_info.get("quota", {})
        if quota:
            total = quota.get("total_tokens", 0)
            configured_used = quota.get("used_tokens", 0)
            used = (
                self._quota_reader(token, configured_used)
                if self._quota_reader is not None
                else configured_used
            )
            if total > 0 and used >= total:
                raise QuotaExceededError(
                    f"quota exceeded for key "
                    f"'{key_info.get('name', token[:12])}' "
                    f"({used:,}/{total:,} tokens)"
                )
            quota = {**quota, "used_tokens": used}

        return {
            "id": token,
            "name": key_info.get("name", token[:12]),
            "enabled": key_info.get("enabled", True),
            "models": allowed_models,
            "quota": quota,
        }

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_key(self, token: str) -> dict[str, Any] | None:
        """获取密钥信息（不做校验）。"""
        if not self._loaded:
            self.load()
        return self._keys.get(token)

    def list_keys(self) -> list[dict[str, Any]]:
        """列出所有密钥摘要（隐藏 token 本身）。"""
        if not self._loaded:
            self.load()
        result: list[dict[str, Any]] = []
        for token, info in self._keys.items():
            quota = info.get("quota", {})
            if quota and self._quota_reader is not None:
                quota = {
                    **quota,
                    "used_tokens": self._quota_reader(
                        token, quota.get("used_tokens", 0)
                    ),
                }
            result.append({
                "id": token,
                "name": info.get("name", ""),
                "enabled": info.get("enabled", True),
                "model_count": len(info.get("models", [])),
                "quota": quota,
            })
        return result

    def check_model(self, token: str, model: str) -> bool:
        """检查密钥是否有权使用某个模型。"""
        if not self._loaded:
            self.load()

        key_info = self._keys.get(token)
        if not key_info:
            return False
        if not key_info.get("enabled", True):
            return False
        return model in key_info.get("models", [])
