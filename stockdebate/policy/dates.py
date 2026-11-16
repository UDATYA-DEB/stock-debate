"""Small date helpers shared by policy modules."""

from __future__ import annotations

from datetime import date


def months_between(newer: date, older: date) -> int:
    return (newer.year - older.year) * 12 + newer.month - older.month


def consecutive_quarters(periods_newest_first: list[date]) -> bool:
    """True if each period is exactly one quarter after the next."""
    return all(months_between(a, b) == 3 for a, b in zip(periods_newest_first, periods_newest_first[1:]))
