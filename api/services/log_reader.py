"""JSONL 日志读取 + 过滤 + 汇总。"""

from __future__ import annotations

from typing import Any

from api.deps import PROJECT_ROOT
from api.utils import read_jsonl


def read_logs(
    date: str,
    *,
    status: str = "all",
    q: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """读取指定日期的日志，返回 {entries, summary}。"""
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    all_entries: list[dict[str, Any]] = []

    if call_log_dir.is_dir():
        for key_dir in call_log_dir.iterdir():
            if key_dir.is_dir():
                all_entries.extend(read_jsonl(key_dir / f"{date}.jsonl"))

    # 时间倒序
    all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    # 过滤
    if status == "ok":
        all_entries = [e for e in all_entries if not e.get("error")]
    elif status == "error":
        all_entries = [e for e in all_entries if e.get("error")]

    if q:
        ql = q.lower()
        all_entries = [
            e for e in all_entries
            if ql in (e.get("key_id", "") or "").lower()
            or ql in (e.get("model", "") or "").lower()
            or ql in (e.get("provider", "") or "").lower()
        ]

    page = all_entries[:limit]
    total_req = len(all_entries)
    err_count = sum(1 for e in all_entries if e.get("error"))

    summary = {
        "request_count": total_req,
        "error_count": err_count,
        "total_tokens": sum(e.get("usage", {}).get("total_tokens", 0) for e in all_entries),
        "prompt_tokens": sum(e.get("usage", {}).get("prompt_tokens", 0) for e in all_entries),
        "completion_tokens": sum(e.get("usage", {}).get("completion_tokens", 0) for e in all_entries),
        "avg_latency_ms": round(
            sum(e.get("latency_ms", 0) for e in all_entries) / max(total_req, 1), 2
        ),
    }
    return {"entries": page, "summary": summary}


def collect_entries_for_days(days: int) -> list[dict[str, Any]]:
    """聚合最近 N 天的所有日志条目。"""
    from api.utils import today_utc, days_ago
    today = today_utc()
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    all_entries: list[dict[str, Any]] = []
    for i in range(days):
        d = days_ago(today, i)
        if call_log_dir.is_dir():
            for key_dir in call_log_dir.iterdir():
                if key_dir.is_dir():
                    all_entries.extend(read_jsonl(key_dir / f"{d}.jsonl"))
    return all_entries
