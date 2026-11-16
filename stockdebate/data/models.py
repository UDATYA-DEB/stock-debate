"""Data shapes shared by every data provider.

Every dataset carries its provenance (which provider, when fetched), so any number
the agents cite can be traced back to where it came from. When a provider can't
supply a dataset, it says so explicitly with an `Unavailable` record instead of
returning empty data. Missing data must never look like a pass.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

StatementKind = Literal["income", "balance", "cashflow"]
Frequency = Literal["annual", "quarterly"]


class Provenance(BaseModel):
    provider: str
    fetched_at: datetime
    source_url: str | None = None


class Unavailable(BaseModel):
    """A dataset that no provider could supply, and why."""

    dataset: str
    reason: str
    tried: list[str] = Field(default_factory=list)


class Statement(BaseModel):
    """One financial statement (e.g. annual income statement).

    `rows` maps a line item (e.g. "Total Revenue") to its value per period,
    keyed by the period-end date in ISO format.
    """

    kind: StatementKind
    frequency: Frequency
    periods: list[date]  # newest first
    rows: dict[str, dict[str, float | None]]
    provenance: Provenance

    def value(self, line_item: str, period: date) -> float | None:
        return self.rows.get(line_item, {}).get(period.isoformat())


class PricePoint(BaseModel):
    day: date
    close: float


class PriceHistory(BaseModel):
    points: list[PricePoint]  # oldest first
    provenance: Provenance


class Shareholding(BaseModel):
    """Shareholding snapshot. Fields are None when the provider doesn't report them."""

    as_of: date | None
    promoter_pct: float | None = None
    pledged_pct_of_promoter: float | None = None
    institutions_pct: float | None = None
    provenance: Provenance


class CompanyProfile(BaseModel):
    """Basic company information used for eligibility checks."""

    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None  # in the listing currency (INR)
    avg_daily_volume_3m: float | None = None  # shares per day
    currency: str | None = None
    provenance: Provenance


class DataQualityIssue(BaseModel):
    dataset: str
    issue: str


class CompanyData(BaseModel):
    """Everything gathered about one company, plus what's missing and what's suspect."""

    symbol: str
    gathered_at: datetime
    profile: CompanyProfile | None = None
    statements: list[Statement] = Field(default_factory=list)
    prices: PriceHistory | None = None
    shareholding: Shareholding | None = None
    unavailable: list[Unavailable] = Field(default_factory=list)
    quality_issues: list[DataQualityIssue] = Field(default_factory=list)

    def statement(self, kind: StatementKind, frequency: Frequency) -> Statement | None:
        return next(
            (s for s in self.statements if s.kind == kind and s.frequency == frequency),
            None,
        )
