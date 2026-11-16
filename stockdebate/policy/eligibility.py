"""Layer 0: is this stock in scope for v1?

Each check passes, fails, or is unknown. Unknown is never treated as a pass,
so a stock is eligible only if every check passes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from stockdebate.data.models import CompanyData
from stockdebate.policy import thresholds as t

Status = Literal["pass", "fail", "unknown"]


class Check(BaseModel):
    name: str
    status: Status
    detail: str


class EligibilityResult(BaseModel):
    eligible: bool
    checks: list[Check]


def check_eligibility(data: CompanyData) -> EligibilityResult:
    checks = [_non_financial(data), _history(data), _market_cap(data), _liquidity(data)]
    return EligibilityResult(eligible=all(c.status == "pass" for c in checks), checks=checks)


def _non_financial(data: CompanyData) -> Check:
    sector = data.profile.sector if data.profile else None
    if sector is None:
        return Check(name="non-financial", status="unknown", detail="sector not available")
    if sector in t.FINANCIAL_SECTORS:
        return Check(name="non-financial", status="fail", detail=f"sector is {sector} (excluded in v1)")
    return Check(name="non-financial", status="pass", detail=f"sector is {sector}")


def _history(data: CompanyData) -> Check:
    stmt = data.statement("income", "annual")
    years = len(stmt.periods[: t.MAX_YEARS]) if stmt else 0
    status: Status = "pass" if years >= t.MIN_YEARS else "fail"
    return Check(name="history", status=status,
                 detail=f"{years} years of annual income data (minimum {t.MIN_YEARS})")


def _market_cap(data: CompanyData) -> Check:
    cap = data.profile.market_cap if data.profile else None
    if cap is None:
        return Check(name="market cap", status="unknown", detail="market cap not available")
    crore = cap / t.CRORE
    status: Status = "pass" if crore >= t.MIN_MARKET_CAP_CRORE else "fail"
    return Check(name="market cap", status=status,
                 detail=f"INR {crore:,.0f} crore (minimum {t.MIN_MARKET_CAP_CRORE:,})")


def _liquidity(data: CompanyData) -> Check:
    volume = data.profile.avg_daily_volume_3m if data.profile else None
    last_close = data.prices.points[-1].close if data.prices and data.prices.points else None
    if volume is None or last_close is None:
        return Check(name="liquidity", status="unknown", detail="volume or price not available")
    traded_crore = volume * last_close / t.CRORE
    status: Status = "pass" if traded_crore >= t.MIN_AVG_DAILY_TRADED_VALUE_CRORE else "fail"
    return Check(name="liquidity", status=status,
                 detail=f"about INR {traded_crore:,.0f} crore traded per day "
                        f"(minimum {t.MIN_AVG_DAILY_TRADED_VALUE_CRORE})")
