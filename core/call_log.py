"""
统一调用日志模块。

一次 API 请求只写一条记录到 ``data_status/call_log/``。
JSON Lines 格式，按 key_id + 日期分文件。

一条记录覆盖所有统计维度：密钥 / 厂商 / 模型 / 能力 / 延迟 / 错误 / 用量。

用法::

    call_log = CallLogger(project_root="/path/to/project")
    call_log.log(
        key_id="sk-kemo-admin",
        key_name="管理密钥",
        provider="deepseek",
        model="deepseek-v4-flash",
        capability="chat",
        request={...},
        response={...},
        usage={...},
        error=None,
        latency_ms=234.5,
    )
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CALL_LOG_DIR = "data_status/call_log"


def _load_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("KEMO_TIMEZONE", "Asia/Shanghai"))
    except Exception:
        return ZoneInfo("Asia/Shanghai")


APP_TIMEZONE = _load_timezone()


class CallLogger:
    """统一调用日志记录器。

    记录每次 API 请求的完整调用信息到一条 JSONL 中，
    供统计、审计、debug 使用。
    """

    def __init__(self, project_root: str | Path = "."):
        self._root = Path(project_root)
        self._base_dir = self._root / CALL_LOG_DIR
        self._on_log: Any = None  # CallLogger → UsageManager 回调

    def bind_quota_deduct(self, callback: Any) -> None:
        """绑定额度扣减回调（供 bootstrap 调用）。

        参数
        ----
        callback : callable(token, total_tokens)
            log 写入后调用，通常指向 UsageManager.deduct_quota()。
        """
        self._on_log = callback

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def log(
        self,
        *,
        key_id: str,
        key_name: str,
        provider: str,
        model: str,
        capability: str = "chat",
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
        latency_ms: float = 0.0,
        completion_latency_ms: float | None = None,
    ) -> dict[str, Any]:
        """记录一次 API 调用。

        返回
        ----
        dict
            写入的 log entry，可继续传递。
        """
        now = datetime.now(APP_TIMEZONE)

        entry: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "request_id": (response or {}).get("id", ""),
            "key_id": key_id,
            "key_name": key_name,
            "provider": provider,
            "model": model,
            "capability": capability,
            "stream": (request or {}).get("stream", False),
            "latency_ms": round(latency_ms, 2),
            "error": error,
            "usage": usage or {},
        }

        if completion_latency_ms is not None:
            entry["completion_latency_ms"] = round(completion_latency_ms, 2)

        # 消息摘要（不记原文）
        entry["messages_summary"] = self._summarize_messages(
            (request or {}).get("messages", [])
        )

        entry["choice_count"] = len((response or {}).get("choices", []))

        self._write(key_id, entry)

        # 触发额度扣减
        if self._on_log is not None and not error:
            total = (usage or {}).get("total_tokens", 0)
            if total > 0:
                try:
                    self._on_log(key_id, total)
                except Exception:
                    logger.debug("quota deduct failed for %s", key_id[:12], exc_info=True)

        return entry

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def read(
        self,
        key_id: str,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取某密钥某天的日志。

        参数
        ----
        date : str | None
            YYYY-MM-DD，None = 今天。
        """
        file_path = self._today_file(key_id, date)
        if not file_path.is_file():
            return []

        entries: list[dict[str, Any]] = []
        try:
            for line in file_path.read_text(encoding="utf-8").strip().split("\n"):
                if line:
                    entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("failed to read %s: %s", file_path, exc)
        return entries

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def summary(
        self,
        *,
        key_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        capability: str | None = None,
        date: str | None = None,
    ) -> dict[str, Any]:
        """按条件汇总某天用量。

        参数均可选，组合过滤。不传则全量。
        """
        entries = self._read_filtered(key_id, provider, model, capability, date)

        result: dict[str, Any] = {
            "request_count": len(entries),
            "error_count": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "reasoning_tokens": 0,
            "avg_latency_ms": 0.0,
        }

        total_latency = 0.0
        latency_count = 0

        for e in entries:
            if e.get("error"):
                result["error_count"] += 1

            u = e.get("usage", {})
            result["total_tokens"] += u.get("total_tokens", 0)
            result["prompt_tokens"] += u.get("prompt_tokens", 0)
            result["completion_tokens"] += u.get("completion_tokens", 0)
            result["prompt_cache_hit_tokens"] += u.get("prompt_cache_hit_tokens", 0)
            result["prompt_cache_miss_tokens"] += u.get("prompt_cache_miss_tokens", 0)
            result["reasoning_tokens"] += u.get("reasoning_tokens", 0)

            lat = e.get("latency_ms", 0)
            if lat > 0:
                total_latency += lat
                latency_count += 1

        if latency_count > 0:
            result["avg_latency_ms"] = round(total_latency / latency_count, 2)

        return result

    # ------------------------------------------------------------------
    # 多日期汇总
    # ------------------------------------------------------------------

    def range_summary(
        self,
        key_id: str,
        date_from: str,
        date_to: str,
        **filters,
    ) -> dict[str, Any]:
        """多日汇总，聚合所有匹配天的用量。"""
        from datetime import timedelta as td

        d = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to, "%Y-%m-%d")

        merged: dict[str, Any] = {
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
        total_latency = 0.0
        total_count = 0

        while d <= end:
            day = d.strftime("%Y-%m-%d")
            s = self.summary(key_id=key_id, date=day, **filters)
            merged["request_count"] += s["request_count"]
            merged["error_count"] += s["error_count"]
            merged["total_tokens"] += s["total_tokens"]
            merged["prompt_tokens"] += s["prompt_tokens"]
            merged["completion_tokens"] += s["completion_tokens"]
            merged["prompt_cache_hit_tokens"] += s["prompt_cache_hit_tokens"]
            merged["prompt_cache_miss_tokens"] += s["prompt_cache_miss_tokens"]
            merged["reasoning_tokens"] += s["reasoning_tokens"]
            total_latency += s["avg_latency_ms"] * s["request_count"]
            total_count += s["request_count"]
            d += td(days=1)

        if total_count > 0:
            merged["avg_latency_ms"] = round(total_latency / total_count, 2)

        return merged

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _read_filtered(
        self,
        key_id: str | None,
        provider: str | None,
        model: str | None,
        capability: str | None,
        date: str | None,
    ) -> list[dict[str, Any]]:
        """按条件读取并过滤日志。"""
        if key_id:
            entries = self.read(key_id, date=date)
        else:
            # 全量扫描所有 key
            entries = []
            if self._base_dir.is_dir():
                for key_dir in self._base_dir.iterdir():
                    if key_dir.is_dir():
                        entries.extend(self.read(key_dir.name, date=date))

        # 过滤
        if provider:
            entries = [e for e in entries if e.get("provider") == provider]
        if model:
            entries = [e for e in entries if e.get("model") == model]
        if capability:
            entries = [e for e in entries if e.get("capability") == capability]

        return entries

    def _write(self, key_id: str, entry: dict[str, Any]) -> None:
        """追加一条 JSON 行到当天文件。"""
        file_path = self._today_file(key_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(entry, ensure_ascii=False)
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.error("failed to write call_log: %s", exc)

    def _today_file(self, key_id: str, date: str | None = None) -> Path:
        if date is None:
            date = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d")
        return self._base_dir / key_id / f"{date}.jsonl"

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_messages(messages: list[dict[str, Any]]) -> list[str]:
        """生成消息摘要：role(charCount)。"""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                char_count = len(content)
            elif isinstance(content, list):
                char_count = sum(
                    len(b.get("text", ""))
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                char_count = 0
            parts.append(f"{role}({char_count}c)")
        return parts
