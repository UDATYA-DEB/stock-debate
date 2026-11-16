"""Data provider backed by the yfinance library (Yahoo Finance).

Known limits for Indian stocks (tested on RELIANCE.NS, 2026-11-16):
- Annual statements: about 5 years
- Quarterly income: about 5 quarters, sometimes with gaps
- Quarterly balance sheet: half-yearly only (matches Indian reporting)
- Quarterly cash flow: not available
- Shareholding: current insider/institution % only; no pledging, no history
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import yfinance as yf

from stockdebate.data.models import (
    CompanyProfile,
    Frequency,
    PriceHistory,
    PricePoint,
    Provenance,
    Shareholding,
    Statement,
    StatementKind,
)

_STATEMENT_ATTR = {
    ("income", "annual"): "income_stmt",
    ("income", "quarterly"): "quarterly_income_stmt",
    ("balance", "annual"): "balance_sheet",
    ("balance", "quarterly"): "quarterly_balance_sheet",
    ("cashflow", "annual"): "cashflow",
    ("cashflow", "quarterly"): "quarterly_cashflow",
}


def _to_yahoo_symbol(symbol: str) -> str:
    """NSE symbols need a .NS suffix on Yahoo (e.g. RELIANCE -> RELIANCE.NS)."""
    return symbol if "." in symbol else f"{symbol}.NS"


def _clean(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


class YFinanceProvider:
    name = "yfinance"

    def _provenance(self, symbol: str) -> Provenance:
        return Provenance(
            provider=self.name,
            fetched_at=datetime.now(timezone.utc),
            source_url=f"https://finance.yahoo.com/quote/{_to_yahoo_symbol(symbol)}",
        )

    def profile(self, symbol: str) -> CompanyProfile | None:
        info = yf.Ticker(_to_yahoo_symbol(symbol)).info or {}
        if not info.get("sector") and not info.get("marketCap"):
            return None
        return CompanyProfile(
            name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            market_cap=_clean(info.get("marketCap")),
            avg_daily_volume_3m=_clean(info.get("averageDailyVolume3Month")),
            currency=info.get("currency"),
            provenance=self._provenance(symbol),
        )

    def statement(self, symbol: str, kind: StatementKind, frequency: Frequency) -> Statement | None:
        df = getattr(yf.Ticker(_to_yahoo_symbol(symbol)), _STATEMENT_ATTR[(kind, frequency)])
        if df is None or df.empty:
            return None
        periods = sorted((c.date() for c in df.columns), reverse=True)
        rows = {
            str(item): {col.date().isoformat(): _clean(df.loc[item, col]) for col in df.columns}
            for item in df.index
        }
        return Statement(
            kind=kind,
            frequency=frequency,
            periods=periods,
            rows=rows,
            provenance=self._provenance(symbol),
        )

    def prices(self, symbol: str) -> PriceHistory | None:
        hist = yf.Ticker(_to_yahoo_symbol(symbol)).history(period="max", auto_adjust=True)
        if hist.empty:
            return None
        points = [
            PricePoint(day=ts.date(), close=float(close))
            for ts, close in hist["Close"].items()
            if _clean(close) is not None
        ]
        return PriceHistory(points=points, provenance=self._provenance(symbol))

    def shareholding(self, symbol: str) -> Shareholding | None:
        holders = yf.Ticker(_to_yahoo_symbol(symbol)).major_holders
        if holders is None or holders.empty:
            return None
        values = holders["Value"].to_dict()
        insiders = _clean(values.get("insidersPercentHeld"))
        institutions = _clean(values.get("institutionsPercentHeld"))
        return Shareholding(
            # Yahoo doesn't say which quarter this snapshot is from.
            as_of=None,
            # Yahoo's "insiders" is the closest proxy for promoter holding.
            promoter_pct=None if insiders is None else insiders * 100,
            institutions_pct=None if institutions is None else institutions * 100,
            pledged_pct_of_promoter=None,  # not provided by Yahoo
            provenance=self._provenance(symbol),
        )
