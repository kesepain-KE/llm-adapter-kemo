"""通用工具函数。"""

from datetime import datetime, timedelta, timezone


def today_utc() -> str:
    """返回 UTC 今天的 YYYY-MM-DD。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def days_ago(date_str: str, n: int) -> str:
    """日期往前推 n 天。"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d - timedelta(days=n)).strftime("%Y-%m-%d")
