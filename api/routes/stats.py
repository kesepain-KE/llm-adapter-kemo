"""GET /api/stats — 仪表盘统计。"""

from fastapi import Query, HTTPException

from api.deps import get_ctx
from api.utils import today_utc
from api.services import daily_stats


async def api_stats(period: str = Query("today")):
    if period not in ("today", "7d", "30d"):
        raise HTTPException(400, detail=f"unknown period: {period}")
    ctx = get_ctx()
    today = today_utc()
    return daily_stats(period, today, ctx)
