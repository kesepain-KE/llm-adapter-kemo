"""GET /api/logs — 调用日志查询。"""

from fastapi import Query

from api.services import read_logs
from api.utils import today_utc


async def api_logs(
    status: str = Query("all"),
    q: str = Query(""),
    date: str = Query(""),
    limit: int = Query(50),
):
    today = today_utc()
    d = date if date else today
    return read_logs(d, status=status, q=q, limit=limit)
