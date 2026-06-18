"""
Token 用量统计模块。

从 provider 的 token_count 模块获取归一化 usage。
不再负责持久化——持久化已由 ``core.call_log.CallLogger`` 统一接管。

用法::

    usage_mgr = UsageManager(project_root="/path/to/project", registry=reg)
    usage = usage_mgr.count("deepseek", response)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class UsageManager:
    """Token 用量管理器。

    - count()     从 API 响应提取归一化 usage
    - get_usage() 从 call_log 读取汇总（委托给 CallLogger）
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        registry: Any = None,
    ):
        self._root = Path(project_root)
        self._registry = registry
        self._call_log: Any = None  # 延迟绑定

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
        """从响应中提取并归一化 usage。

        优先走 provider 的 token_count 模块，
        未注册时直接使用响应中的 usage 字段。

        参数
        ----
        provider : str
            provider 名称。
        response : dict
            API 响应。
        request : dict | None
            原始请求（usage 缺失时用于离线预估）。

        返回
        ----
        dict
            统一 usage。
        """
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

        # 回退
        if raw_usage:
            return {
                "prompt_tokens": raw_usage.get("prompt_tokens", 0),
                "completion_tokens": raw_usage.get("completion_tokens", 0),
                "total_tokens": raw_usage.get("total_tokens", 0),
                "prompt_cache_hit_tokens": raw_usage.get(
                    "prompt_cache_hit_tokens", 0
                ),
                "prompt_cache_miss_tokens": raw_usage.get(
                    "prompt_cache_miss_tokens", 0
                ),
                "reasoning_tokens": 0,
            }
        return {}

    # ------------------------------------------------------------------
    # 汇总查询
    # ------------------------------------------------------------------

    def get_usage(
        self,
        key_id: str,
        date: str | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        """获取某密钥某天的用量汇总。

        委托给 CallLogger.summary()。
        """
        if self._call_log is None:
            logger.warning("call_log not bound; returning empty summary")
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
