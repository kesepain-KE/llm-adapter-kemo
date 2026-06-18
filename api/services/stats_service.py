"""统计 + 趋势 + Provider 分解。"""

from __future__ import annotations

from typing import Any

from api.deps import PROJECT_ROOT, get_ctx
from api.utils import today_utc, days_ago, delta_pct, percentile, read_jsonl


def build_trend(days: int) -> list[dict[str, Any]]:
    """构建最近 N 天的请求趋势。"""
    ctx = get_ctx()
    today = today_utc()
    trend: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        d = days_ago(today, i)
        s = ctx.call_log.summary(date=d)
        trend.append({
            "date": d,
            "requests": s["request_count"],
            "cache_hit": s["prompt_cache_hit_tokens"],
        })
    return trend


def recent_calls(n: int) -> list[dict[str, Any]]:
    """最新 N 条调用记录。"""
    today = today_utc()
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    all_entries: list[dict[str, Any]] = []
    if call_log_dir.is_dir():
        for key_dir in call_log_dir.iterdir():
            if key_dir.is_dir():
                all_entries.extend(read_jsonl(key_dir / f"{today}.jsonl"))
    all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return [
        {
            "request_id": e.get("request_id", ""),
            "model": e.get("model", ""),
            "latency_ms": e.get("latency_ms", 0),
            "total_tokens": e.get("usage", {}).get("total_tokens", 0),
            "error": e.get("error"),
        }
        for e in all_entries[:n]
    ]


def provider_breakdown(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 provider 分解统计数据。"""
    by_p: dict[str, dict[str, Any]] = {}
    for e in entries:
        p = e.get("provider", "unknown")
        if p not in by_p:
            by_p[p] = {
                "provider": p,
                "request_count": 0,
                "error_count": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cache_hit_tokens": 0,
                "reasoning_tokens": 0,
                "total_latency_ms": 0.0,
                "latency_count": 0,
                "stream_count": 0,
                "models": {},
            }
        bp = by_p[p]
        bp["request_count"] += 1
        if e.get("error"):
            bp["error_count"] += 1
        u = e.get("usage", {})
        bp["total_tokens"] += u.get("total_tokens", 0)
        bp["prompt_tokens"] += u.get("prompt_tokens", 0)
        bp["completion_tokens"] += u.get("completion_tokens", 0)
        bp["cache_hit_tokens"] += u.get("prompt_cache_hit_tokens", 0)
        bp["reasoning_tokens"] += u.get("reasoning_tokens", 0)
        lat = e.get("latency_ms", 0)
        if lat > 0:
            bp["total_latency_ms"] += lat
            bp["latency_count"] += 1
        if e.get("stream"):
            bp["stream_count"] += 1
        m = e.get("model", "unknown")
        if m not in bp["models"]:
            bp["models"][m] = {"model": m, "total_tokens": 0}
        bp["models"][m]["total_tokens"] += u.get("total_tokens", 0)

    result: list[dict[str, Any]] = []
    for bp in by_p.values():
        total = bp["total_tokens"] or 1
        reqs = bp["request_count"] or 1
        models_list = list(bp["models"].values())
        for m in models_list:
            m["pct"] = round(m["total_tokens"] / total * 100, 1)
        result.append({
            "provider": bp["provider"],
            "request_count": bp["request_count"],
            "total_tokens": bp["total_tokens"],
            "prompt_tokens": bp["prompt_tokens"],
            "completion_tokens": bp["completion_tokens"],
            "cache_hit_pct": round(bp["cache_hit_tokens"] / total * 100, 1),
            "reasoning_tokens": bp["reasoning_tokens"],
            "avg_latency_ms": round(bp["total_latency_ms"] / max(bp["latency_count"], 1), 1),
            "error_rate_pct": round(bp["error_count"] / reqs * 100, 2),
            "stream_pct": round(bp["stream_count"] / reqs * 100, 1),
            "models": models_list,
        })
    return result


def usage_summary(entries: list[dict[str, Any]], period: str) -> dict[str, Any]:
    """从日志条目生成用量统计总览。"""
    total_req = len(entries)
    err_count = sum(1 for e in entries if e.get("error"))
    success_rate = (total_req - err_count) / max(total_req, 1) * 100
    latencies = sorted([e.get("latency_ms", 0) for e in entries if e.get("latency_ms", 0) > 0])
    active_keys = len({e.get("key_id") for e in entries})
    total_tokens = sum(e.get("usage", {}).get("total_tokens", 0) for e in entries)
    cache_hit = sum(e.get("usage", {}).get("prompt_cache_hit_tokens", 0) for e in entries)
    reasoning = sum(e.get("usage", {}).get("reasoning_tokens", 0) for e in entries)

    return {
        "period": period,
        "total_tokens": total_tokens,
        "request_count": total_req,
        "success_rate_pct": round(success_rate, 2),
        "active_keys": active_keys,
        "latency": {
            "p50_ms": percentile(latencies, 50),
            "p95_ms": percentile(latencies, 95),
            "p99_ms": percentile(latencies, 99),
        },
        "cache": {
            "hit_tokens": cache_hit,
            "hit_pct": round(cache_hit / max(total_tokens, 1) * 100, 1),
        },
        "reasoning_tokens": reasoning,
        "by_provider": provider_breakdown(entries),
    }


def daily_stats(period: str, today: str, ctx) -> dict[str, Any]:
    """单日/多日仪表盘统计。"""
    if period == "today":
        s_today = ctx.call_log.summary(date=today)
        s_yesterday = ctx.call_log.summary(date=days_ago(today, 1))
        return {
            "period": "today",
            "request_count": s_today["request_count"],
            "request_delta_pct": delta_pct(s_today["request_count"], s_yesterday["request_count"]),
            "token_total": s_today["total_tokens"],
            "token_delta_pct": delta_pct(s_today["total_tokens"], s_yesterday["total_tokens"]),
            "avg_latency_ms": s_today["avg_latency_ms"],
            "latency_delta_ms": round(s_today["avg_latency_ms"] - s_yesterday["avg_latency_ms"], 1),
            "error_rate_pct": round(
                s_today["error_count"] / max(s_today["request_count"], 1) * 100, 2
            ),
            "error_open_count": s_today["error_count"],
            "trend": build_trend(7),
            "recent_calls": recent_calls(5),
            "by_provider": provider_breakdown(
                _read_day_entries(today)
            ),
        }

    days = 7 if period == "7d" else 30
    total_all = {"request_count": 0, "error_count": 0, "total_tokens": 0}
    for i in range(days):
        s = ctx.call_log.summary(date=days_ago(today, i))
        total_all["request_count"] += s["request_count"]
        total_all["error_count"] += s["error_count"]
        total_all["total_tokens"] += s["total_tokens"]

    return {
        "period": period,
        "request_count": total_all["request_count"],
        "request_delta_pct": 0,
        "token_total": total_all["total_tokens"],
        "token_delta_pct": 0,
        "avg_latency_ms": 0,
        "latency_delta_ms": 0,
        "error_rate_pct": round(
            total_all["error_count"] / max(total_all["request_count"], 1) * 100, 2
        ),
        "error_open_count": total_all["error_count"],
        "trend": build_trend(days),
        "recent_calls": recent_calls(5),
        "by_provider": provider_breakdown([]),
    }


def _read_day_entries(date_str: str) -> list[dict[str, Any]]:
    call_log_dir = PROJECT_ROOT / "data_status" / "call_log"
    all_entries: list[dict[str, Any]] = []
    if call_log_dir.is_dir():
        for key_dir in call_log_dir.iterdir():
            if key_dir.is_dir():
                all_entries.extend(read_jsonl(key_dir / f"{date_str}.jsonl"))
    return all_entries
