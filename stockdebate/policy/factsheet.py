"""The fact sheet: every number the agents are allowed to cite.

Each fact has an ID (F1, F2, ...), its latest value, its full history in the
window, and a trend summary. Agents cite facts by ID; the validator checks claims
against them; the opponent gets the history to check for cherry-picking.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from stockdebate.data.models import CompanyData, Unavailable
from stockdebate.policy.trend import TrendSummary


class HistoryPoint(BaseModel):
    period: str  # e.g. "FY2026"
    end_date: date
    value: float


class Fact(BaseModel):
    id: str = ""  # assigned by build_factsheet
    metric: str  # machine name, e.g. "debt_to_equity"
    label: str  # human name, e.g. "Debt to equity"
    value: float
    unit: str  # "%", "x", "INR crore", "days", "million shares"
    period: str  # e.g. "FY2026" or "FY2022-FY2026"
    basis: str | None = None  # e.g. "Total Debt / Stockholders Equity"
    history: list[HistoryPoint] = Field(default_factory=list)
    trend: TrendSummary | None = None
    inputs: list[str] = Field(default_factory=list)  # source line items
    source: str  # provider name
    years_used: int


class FactSheet(BaseModel):
    symbol: str
    built_at: datetime
    facts: list[Fact] = Field(default_factory=list)
    unavailable: list[Unavailable] = Field(default_factory=list)

    def get(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def by_metric(self, metric: str) -> Fact | None:
        return next((f for f in self.facts if f.metric == metric), None)


def build_factsheet(data: CompanyData) -> FactSheet:
    # Imported here to avoid a circular import (metrics builds Fact objects).
    from stockdebate.policy.metrics import METRICS
    from stockdebate.policy.valuation import VALUATION_METRICS

    sheet = FactSheet(symbol=data.symbol, built_at=datetime.now(timezone.utc))
    for metric_fn in METRICS + VALUATION_METRICS:
        name = metric_fn.__name__
        try:
            fact = metric_fn(data)
        except NotImplementedError:
            sheet.unavailable.append(
                Unavailable(dataset=name, reason="not implemented yet (exercise)")
            )
            continue
        if fact is None:
            sheet.unavailable.append(
                Unavailable(dataset=name, reason="insufficient data in the source statements")
            )
            continue
        fact.id = f"F{len(sheet.facts) + 1}"
        sheet.facts.append(fact)
    return sheet
