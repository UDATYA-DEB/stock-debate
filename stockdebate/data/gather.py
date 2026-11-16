"""Gather a company's data from an ordered list of providers.

For each dataset, providers are tried in order and the first one that returns
data wins. Anything no provider can supply is recorded as `Unavailable`, and
suspicious data (e.g. a missing quarter) is recorded as a quality issue, so the
fact sheet and the agents can see exactly what is and isn't known.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from typing import TypeVar

from stockdebate.data.models import (
    CompanyData,
    DataQualityIssue,
    Frequency,
    StatementKind,
    Unavailable,
)
from stockdebate.data.providers.base import DataProvider

log = logging.getLogger(__name__)
T = TypeVar("T")

STATEMENTS: list[tuple[StatementKind, Frequency]] = [
    ("income", "annual"),
    ("balance", "annual"),
    ("cashflow", "annual"),
    ("income", "quarterly"),
    ("balance", "quarterly"),
    ("cashflow", "quarterly"),
]


def _first_available(
    dataset: str,
    providers: Sequence[DataProvider],
    fetch: Callable[[DataProvider], T | None],
) -> T | Unavailable:
    reasons = []
    for provider in providers:
        try:
            result = fetch(provider)
        except Exception as exc:  # a failing provider shouldn't stop the others
            log.warning("%s failed for %s: %s", provider.name, dataset, exc)
            reasons.append(f"{provider.name}: error ({exc})")
            continue
        if result is not None:
            return result
        reasons.append(f"{provider.name}: no data")
    return Unavailable(
        dataset=dataset,
        reason="; ".join(reasons) or "no providers configured",
        tried=[p.name for p in providers],
    )


def _months_between(newer: date, older: date) -> int:
    return (newer.year - older.year) * 12 + newer.month - older.month


def find_period_gaps(periods: list[date], expected_months: int) -> list[str]:
    """Report gaps between consecutive periods (newest first) larger than expected."""
    gaps = []
    for newer, older in zip(periods, periods[1:]):
        months = _months_between(newer, older)
        if months > expected_months:
            gaps.append(f"{months}-month gap between {older} and {newer}")
    return gaps


def gather(symbol: str, providers: Sequence[DataProvider]) -> CompanyData:
    data = CompanyData(symbol=symbol, gathered_at=datetime.now(timezone.utc))

    profile = _first_available("company profile", providers, lambda p: p.profile(symbol))
    if isinstance(profile, Unavailable):
        data.unavailable.append(profile)
    else:
        data.profile = profile

    for kind, frequency in STATEMENTS:
        name = f"{frequency} {kind} statement"
        result = _first_available(
            name, providers, lambda p, k=kind, f=frequency: p.statement(symbol, k, f)
        )
        if isinstance(result, Unavailable):
            data.unavailable.append(result)
            continue
        data.statements.append(result)
        # Quarterly balance sheets in India are half-yearly by regulation; don't flag those.
        expected = 12 if frequency == "annual" else (6 if kind == "balance" else 3)
        for gap in find_period_gaps(result.periods, expected):
            data.quality_issues.append(DataQualityIssue(dataset=name, issue=gap))

    prices = _first_available("price history", providers, lambda p: p.prices(symbol))
    if isinstance(prices, Unavailable):
        data.unavailable.append(prices)
    else:
        data.prices = prices

    holding = _first_available("shareholding", providers, lambda p: p.shareholding(symbol))
    if isinstance(holding, Unavailable):
        data.unavailable.append(holding)
    else:
        data.shareholding = holding
        # A provider may supply shareholding but not pledging; that must be visible.
        if holding.pledged_pct_of_promoter is None:
            data.unavailable.append(
                Unavailable(
                    dataset="promoter pledging",
                    reason=f"{holding.provenance.provider} does not report pledging",
                    tried=[holding.provenance.provider],
                )
            )

    return data
