"""
Token 用量 + 额度管理模块。

- count()         — 从 API 响应提取归一化 usage
- check_quota()   — 请求前：结合 api_keys.json 总额度检查 SQLite 实时用量
- deduct_quota()  — 请求后：原子增加 SQLite used_tokens
- get_usage()     — 从 call_log 读取汇总
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .quota_store import QuotaStore

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Token 额度超限。"""


class UsageManager:
    """Token 用量 + 额度管理器。"""

    def __init__(
        self,
        project_root: str | Path = ".",
        registry: Any = None,
    ):
        self._root = Path(project_root)
        self._registry = registry
        self._call_log: Any = None
        self._quota_store = QuotaStore(self._root)

    def bind_call_log(self, call_log: Any) -> None:
        """绑定统一日志实例（供 bootstrap 调用）。"""
        self._call_log = call_log

    # ------------------------------------------------------------------
    # token 计数
    # ------------------------------------------------------------------

    def count(
        self,
        provider: str,
        response: dict[str, Any],
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """从 API 响应提取归一化 usage。"""
        raw_usage = response.get("usage")

        if self._registry is not None:
            try:
                tc = self._registry.get_token_count(provider)
                if raw_usage:
                    return tc.normalize_usage(raw_usage)
                if request is not None:
                    return tc.count(request)
            except ModuleNotFoundError:
                logger.debug("no token_count for '%s', fallback", provider)

        if raw_usage:
            return {
                "prompt_tokens": raw_usage.get("prompt_tokens", 0),
                "completion_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
                "prompt_cache_hit_tokens": raw_usage.get("prompt_cache_hit_tokens", 0),
                "prompt_cache_miss_tokens": raw_usage.get("prompt_cache_miss_tokens", 0),
                "reasoning_tokens": 0,
            }
        return {}

    # ------------------------------------------------------------------
    # 额度管理
    # ------------------------------------------------------------------

    def check_quota(self, token: str) -> dict[str, Any]:
        """请求前检查额度。

        返回密钥 quota 信息；已超限则抛 QuotaExceededError。

        参数
        ----
        token : str
            API 密钥 token。

        返回
        ----
        dict
            {total_tokens, used_tokens, remaining}
        """
        keys = self._load_keys()
        if token not in keys:
            return {"total_tokens": 0, "used_tokens": 0, "remaining": 0}

        key_info = keys[token]
        quota = key_info.get("quota", {})
        total = quota.get("total_tokens", 0)
        used = self._quota_store.get_used(
            token, fallback=quota.get("used_tokens", 0)
        )

        if total > 0 and used >= total:
            raise QuotaExceededError(
                f"quota exceeded for key "
                f"'{key_info.get('name', token[:12])}' "
                f"({used:,}/{total:,} tokens)"
            )

        return {
            "total_tokens": total,
            "used_tokens": used,
            "remaining": max(total - used, 0) if total > 0 else -1,
        }

    def deduct_quota(self, token: str, total_tokens: int) -> dict[str, Any] | None:
        """请求后扣减额度。

        参数
        ----
        token : str
            API 密钥 token。
        total_tokens : int
            本次请求消耗的 token 数。

        返回
        ----
        dict | None
            更新后的 quota 信息；密钥不存在 / 无 quota 配置返回 None。
        """
        if total_tokens <= 0:
            return None

        keys = self._load_keys()

        if token not in keys:
            return None

        key_info = keys[token]
        quota = key_info.get("quota", {})
        if not quota:
            return None

        try:
            used = self._quota_store.deduct(
                token,
                total_tokens,
                fallback=quota.get("used_tokens", 0),
            )
            logger.debug("quota deducted: %s +%d → used=%d", token[:12], total_tokens, used)
        except Exception as exc:
            logger.error("failed to update quota SQLite store: %s", exc)
            return None

        return {
            "total_tokens": quota.get("total_tokens", 0),
            "used_tokens": used,
            "remaining": max(quota.get("total_tokens", 0) - used, 0),
        }

    # ------------------------------------------------------------------
    # 汇总查询
    # ------------------------------------------------------------------

    def get_usage(
        self,
        key_id: str,
        date: str | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        """委托给 CallLogger.summary()。"""
        if self._call_log is None:
            return {
                "request_count": 0,
                "error_count": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "reasoning_tokens": 0,
                "avg_latency_ms": 0.0,
            }
        return self._call_log.summary(key_id=key_id, date=date, **filters)

    def used_tokens(self, token: str, fallback: int = 0) -> int:
        return self._quota_store.get_used(token, fallback=fallback)

    def sync_quotas_from_config(self, overwrite: bool = False) -> None:
        self._quota_store.sync_from_config(overwrite=overwrite)

    def overlay_quota_usage(self, data: dict[str, Any]) -> dict[str, Any]:
        keys = data.get("keys", {}) if isinstance(data, dict) else {}
        for token, info in keys.items():
            quota = info.get("quota") or {}
            if quota:
                quota["used_tokens"] = self.used_tokens(
                    token, fallback=quota.get("used_tokens", 0)
                )
                info["quota"] = quota
        return data

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load_keys(self) -> dict[str, dict[str, Any]]:
        path = self._root / "config" / "api_keys.json"
        try:
            return json.loads(path.read_text("utf-8")).get("keys", {})
        except (OSError, json.JSONDecodeError):
            return {}
