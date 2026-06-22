"""通用工具函数。"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _load_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("KEMO_TIMEZONE", "Asia/Shanghai"))
    except Exception:
        return ZoneInfo("Asia/Shanghai")


APP_TIMEZONE = _load_timezone()


def today_utc() -> str:
    """返回应用时区今天的 YYYY-MM-DD。"""
    return datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d")


def days_ago(date_str: str, n: int) -> str:
    """日期往前推 n 天。"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d - timedelta(days=n)).strftime("%Y-%m-%d")
