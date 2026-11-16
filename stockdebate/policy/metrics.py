"""Metric calculations for the fact sheet.

Each metric function takes CompanyData and returns a Fact, or None when the
source data doesn't allow it. All metrics use annual data, up to MAX_YEARS.

Line item names are Yahoo Finance's (e.g. "Total Revenue", "EBIT").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from stockdebate.data.models import CompanyData, StatementKind
from stockdebate.policy.factsheet import Fact, HistoryPoint
from stockdebate.policy.thresholds import CRORE, MAX_YEARS
from stockdebate.policy.trend import fy_label, summarize

Series = dict[date, float]  # period end -> value


# ---------- helpers ----------

def series(data: CompanyData, kind: StatementKind, line_item: str) -> Series:
    """Annual values of one line item, limited to the latest MAX_YEARS periods."""
    stmt = data.statement(kind, "annual")
    if stmt is None:
        return {}
    out: Series = {}
    for period in stmt.periods[:MAX_YEARS]:  # periods are newest first
        value = stmt.value(line_item, period)
        if value is not None:
            out[period] = value
    return out


def ratio(numerator: Series, denominator: Series, scale: float = 1.0,
          positive_denominator: bool = True) -> Series:
    """numerator / denominator * scale, for periods present in both."""
    out: Series = {}
    for period, num in numerator.items():
        den = denominator.get(period)
        if den is None or den == 0 or (positive_denominator and den < 0):
            continue
        out[period] = num / den * scale
    return out


def scaled(s: Series, factor: float) -> Series:
    return {p: v / factor for p, v in s.items()}


def source_of(data: CompanyData, kind: StatementKind) -> str:
    stmt = data.statement(kind, "annual")
    return stmt.provenance.provider if stmt else "unknown"


def make_fact(metric: str, label: str, unit: str, s: Series, *, inputs: list[str],
              source: str, basis: str | None = None, value: float | None = None,
              period: str | None = None) -> Fact | None:
    """Build a Fact from a series. By default the value is the latest period's."""
    if not s:
        return None
    points = sorted(s.items())  # oldest first
    latest_date, latest_value = points[-1]
    return Fact(
        metric=metric,
        label=label,
        unit=unit,
        value=round(latest_value if value is None else value, 2),
        period=period or fy_label(latest_date),
        basis=basis,
        history=[HistoryPoint(period=fy_label(d), end_date=d, value=round(v, 2)) for d, v in points],
        trend=summarize(points) if len(points) >= 2 else None,
        inputs=inputs,
        source=source,
        years_used=len(points),
    )


def growth_fact(metric: str, label: str, s: Series, *, inputs: list[str], source: str) -> Fact | None:
    """A CAGR fact over the whole window; the history is the underlying series."""
    if len(s) < 2:
        return None
    points = sorted(s.items())
    trend = summarize(points)
    if trend.cagr_pct is None:  # undefined when start or end value is not positive
        return None
    fact = make_fact(metric, label, "%", s, inputs=inputs, source=source,
                     basis="compound annual growth rate over the window",
                     value=trend.cagr_pct,
                     period=f"{fy_label(points[0][0])}-{fy_label(points[-1][0])}")
    return fact


# ---------- size and growth ----------

def revenue(data: CompanyData) -> Fact | None:
    s = scaled(series(data, "income", "Total Revenue"), CRORE)
    return make_fact("revenue", "Revenue", "INR crore", s,
                     inputs=["Total Revenue"], source=source_of(data, "income"))


def net_profit(data: CompanyData) -> Fact | None:
    s = scaled(series(data, "income", "Net Income Common Stockholders"), CRORE)
    return make_fact("net_profit", "Net profit (to shareholders)", "INR crore", s,
                     inputs=["Net Income Common Stockholders"], source=source_of(data, "income"))


def revenue_cagr(data: CompanyData) -> Fact | None:
    s = scaled(series(data, "income", "Total Revenue"), CRORE)
    return growth_fact("revenue_cagr", "Revenue growth (CAGR)", s,
                       inputs=["Total Revenue"], source=source_of(data, "income"))


def profit_cagr(data: CompanyData) -> Fact | None:
    s = scaled(series(data, "income", "Net Income Common Stockholders"), CRORE)
    return growth_fact("profit_cagr", "Net profit growth (CAGR)", s,
                       inputs=["Net Income Common Stockholders"], source=source_of(data, "income"))


# ---------- quality ----------

def operating_margin(data: CompanyData) -> Fact | None:
    s = ratio(series(data, "income", "Operating Income"),
              series(data, "income", "Total Revenue"), scale=100)
    return make_fact("operating_margin", "Operating margin", "%", s,
                     basis="Operating Income / Total Revenue",
                     inputs=["Operating Income", "Total Revenue"], source=source_of(data, "income"))


def roce(data: CompanyData) -> Fact | None:
    """Return on capital employed, in %.

    ROCE = EBIT / Capital Employed * 100, where
    Capital Employed = Total Assets - Current Liabilities.

    Only periods present in all three series are used (the income statement
    may have fewer years than the balance sheet). Periods with zero or negative
    capital employed are skipped: ROCE has no meaning there.
    """
    ebit = series(data, "income", "EBIT")
    assets = series(data, "balance", "Total Assets")
    current_liabilities = series(data, "balance", "Current Liabilities")
    capital_employed = {p: assets[p] - current_liabilities[p]
                        for p in assets if p in current_liabilities}
    s = ratio(ebit, capital_employed, scale=100)  # skips non-positive capital employed
    return make_fact("roce", "Return on capital employed", "%", s,
                     basis="EBIT / (Total Assets - Current Liabilities)",
                     inputs=["EBIT", "Total Assets", "Current Liabilities"],
                     source=source_of(data, "balance"))


def cash_conversion(data: CompanyData) -> Fact | None:
    """Cash conversion, in %: how much of reported profit arrives as cash.

    Cash conversion = Operating Cash Flow / Net Income * 100.
    Loss years (net income zero or negative) are skipped: the ratio has no
    meaning there. Our policy (Layer 2) looks for roughly 70% or more.
    """
    s = ratio(series(data, "cashflow", "Operating Cash Flow"),
              series(data, "income", "Net Income Common Stockholders"), scale=100)
    return make_fact("cash_conversion", "Cash conversion (operating cash flow / net profit)", "%", s,
                     basis="Operating Cash Flow / Net Income Common Stockholders; loss years skipped",
                     inputs=["Operating Cash Flow", "Net Income Common Stockholders"],
                     source=source_of(data, "cashflow"))


def operating_cash_flow(data: CompanyData) -> Fact | None:
    s = scaled(series(data, "cashflow", "Operating Cash Flow"), CRORE)
    return make_fact("operating_cash_flow", "Operating cash flow", "INR crore", s,
                     inputs=["Operating Cash Flow"], source=source_of(data, "cashflow"))


def free_cash_flow(data: CompanyData) -> Fact | None:
    ocf = series(data, "cashflow", "Operating Cash Flow")
    capex = series(data, "cashflow", "Capital Expenditure")  # reported as a negative number
    s = {p: (ocf[p] - abs(capex[p])) / CRORE for p in ocf if p in capex}
    return make_fact("free_cash_flow", "Free cash flow", "INR crore", s,
                     basis="Operating Cash Flow - |Capital Expenditure|",
                     inputs=["Operating Cash Flow", "Capital Expenditure"],
                     source=source_of(data, "cashflow"))


# ---------- balance sheet ----------

def debt_to_equity(data: CompanyData) -> Fact | None:
    s = ratio(series(data, "balance", "Total Debt"), series(data, "balance", "Stockholders Equity"))
    return make_fact("debt_to_equity", "Debt to equity", "x", s,
                     basis="Total Debt / Stockholders Equity",
                     inputs=["Total Debt", "Stockholders Equity"], source=source_of(data, "balance"))


def interest_coverage(data: CompanyData) -> Fact | None:
    interest = {p: abs(v) for p, v in series(data, "income", "Interest Expense").items()}
    s = ratio(series(data, "income", "EBIT"), interest)
    return make_fact("interest_coverage", "Interest coverage", "x", s,
                     basis="EBIT / Interest Expense",
                     inputs=["EBIT", "Interest Expense"], source=source_of(data, "income"))


def share_count(data: CompanyData) -> Fact | None:
    s = scaled(series(data, "balance", "Ordinary Shares Number"), 1e6)
    return make_fact("share_count", "Shares outstanding", "million shares", s,
                     inputs=["Ordinary Shares Number"], source=source_of(data, "balance"))


def dilution(data: CompanyData) -> Fact | None:
    s = series(data, "balance", "Ordinary Shares Number")
    if len(s) < 2:
        return None
    points = sorted(s.items())
    first, last = points[0][1], points[-1][1]
    if first <= 0:
        return None
    return make_fact("dilution", "Share count change over window", "%", scaled(s, 1e6),
                     basis="(latest shares / earliest shares - 1) * 100; history in million shares",
                     value=(last / first - 1) * 100,
                     period=f"{fy_label(points[0][0])}-{fy_label(points[-1][0])}",
                     inputs=["Ordinary Shares Number"], source=source_of(data, "balance"))


def receivable_days(data: CompanyData) -> Fact | None:
    s = ratio(series(data, "balance", "Accounts Receivable"),
              series(data, "income", "Total Revenue"), scale=365)
    return make_fact("receivable_days", "Receivable days", "days", s,
                     basis="Accounts Receivable / Total Revenue * 365",
                     inputs=["Accounts Receivable", "Total Revenue"], source=source_of(data, "balance"))


def inventory_days(data: CompanyData) -> Fact | None:
    s = ratio(series(data, "balance", "Inventory"),
              series(data, "income", "Cost Of Revenue"), scale=365)
    return make_fact("inventory_days", "Inventory days", "days", s,
                     basis="Inventory / Cost Of Revenue * 365",
                     inputs=["Inventory", "Cost Of Revenue"], source=source_of(data, "balance"))


METRICS: list[Callable[[CompanyData], Fact | None]] = [
    revenue,
    net_profit,
    revenue_cagr,
    profit_cagr,
    operating_margin,
    roce,
    cash_conversion,
    operating_cash_flow,
    free_cash_flow,
    debt_to_equity,
    interest_coverage,
    share_count,
    dilution,
    receivable_days,
    inventory_days,
]
