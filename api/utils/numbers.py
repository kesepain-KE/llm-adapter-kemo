"""数学生工具。"""

from typing import Sequence


def delta_pct(current: int, previous: int) -> float:
    """计算变化百分比。"""
    if previous > 0:
        return round((current - previous) / previous * 100, 1)
    return 0.0


def percentile(sorted_vals: Sequence[float], pct: float) -> float:
    """计算百分位数。"""
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * pct / 100)
    return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 1)
