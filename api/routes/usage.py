"""GET /api/usage — 用量统计。"""

from fastapi import Query, HTTPException

from api.services import collect_entries_for_days, usage_summary


async def api_usage(period: str = Query("today")):
    days_map = {"today": 1, "7d": 7, "30d": 30, "month": 30}
    days = days_map.get(period)
    if days is None:
        raise HTTPException(400, detail=f"unknown period: {period}")
    entries = collect_entries_for_days(days)
    return usage_summary(entries, period)
