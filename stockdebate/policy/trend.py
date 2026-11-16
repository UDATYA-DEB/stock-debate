"""Period labels and trend summaries.

Trend summaries are what make cherry-picking checkable: if an agent cites the best
year out of five, `latest_rank` / `rank_of` show it, and `direction` shows whether
the overall trend agrees with the claim.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

Direction = Literal["rising", "falling", "flat", "mixed", "insufficient"]


def fy_label(d: date) -> str:
    """Indian financial year label: the year ending 31 March 2026 is FY2026."""
    return f"FY{d.year if d.month <= 3 else d.year + 1}"


def quarter_label(d: date) -> str:
    """Indian fiscal quarter label: the quarter ending 30 Sep 2026 is Q2 FY2027."""
    fy = d.year if d.month <= 3 else d.year + 1
    quarter = ((d.month - 4) % 12) // 3 + 1
    return f"Q{quarter} FY{fy}"


def cagr_pct(start: float, end: float, years: float) -> float | None:
    """Compound annual growth rate in %. Undefined for non-positive values."""
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100


def rank_of(values: list[float], index: int) -> int:
    """Rank of values[index] among all values; 1 = highest."""
    return 1 + sum(1 for i, v in enumerate(values) if i != index and v > values[index])


class TrendSummary(BaseModel):
    n_periods: int
    ups: int
    downs: int
    direction: Direction
    latest_rank: int  # 1 = latest value is the highest in the window
    cagr_pct: float | None


def summarize(points: list[tuple[date, float]]) -> TrendSummary:
    """Summarize a series of (period_end, value), oldest first."""
    values = [v for _, v in points]
    n = len(values)
    diffs = [b - a for a, b in zip(values, values[1:])]
    ups = sum(1 for d in diffs if d > 0)
    downs = sum(1 for d in diffs if d < 0)

    scale = max((abs(v) for v in values), default=0.0)
    if n < 3:
        direction: Direction = "insufficient"
    elif scale == 0 or all(abs(d) <= 0.02 * scale for d in diffs):
        direction = "flat"
    elif ups >= 0.75 * (n - 1) and values[-1] > values[0]:
        direction = "rising"
    elif downs >= 0.75 * (n - 1) and values[-1] < values[0]:
        direction = "falling"
    else:
        direction = "mixed"

    cagr = None
    if n >= 2:
        years = (points[-1][0] - points[0][0]).days / 365.25
        cagr = cagr_pct(values[0], values[-1], years)

    return TrendSummary(
        n_periods=n,
        ups=ups,
        downs=downs,
        direction=direction,
        latest_rank=rank_of(values, n - 1) if n else 0,
        cagr_pct=None if cagr is None else round(cagr, 2),
    )
