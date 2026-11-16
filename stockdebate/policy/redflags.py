"""Layer 1: red flags. Any triggered flag blocks a BUY (DECISIONS 3.3, 9.1).

Each flag is triggered, clear, or unknown. Unknown means the data isn't
available; it is never treated as clear, and lowers the judge's confidence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from stockdebate.data.models import CompanyData
from stockdebate.policy import thresholds as t
from stockdebate.policy.factsheet import FactSheet

Status = Literal["triggered", "clear", "unknown"]


class RedFlag(BaseModel):
    code: str
    description: str
    status: Status
    detail: str
    facts: list[str] = Field(default_factory=list)  # fact IDs this flag relied on


def check_red_flags(data: CompanyData, sheet: FactSheet) -> list[RedFlag]:
    return [
        _pledging(data),
        _auditor(),
        _negative_ocf(sheet),
        _debt(sheet),
        _dilution(sheet),
        _working_capital(sheet),
    ]


def _pledging(data: CompanyData) -> RedFlag:
    desc = "Promoter pledging is high"
    pledged = data.shareholding.pledged_pct_of_promoter if data.shareholding else None
    if pledged is None:
        return RedFlag(code="pledging", description=desc, status="unknown",
                       detail="pledging data not available from current providers")
    status: Status = "triggered" if pledged > t.PLEDGE_MAX_PCT_OF_PROMOTER else "clear"
    return RedFlag(code="pledging", description=desc, status=status,
                   detail=f"{pledged:.1f}% of promoter holding pledged "
                          f"(limit {t.PLEDGE_MAX_PCT_OF_PROMOTER}%)")


def _auditor() -> RedFlag:
    return RedFlag(code="auditor", description="Auditor resigned or gave a qualified opinion",
                   status="unknown",
                   detail="needs annual reports / exchange filings (gap-filling is deferred)")


def _negative_ocf(sheet: FactSheet) -> RedFlag:
    desc = "Operating cash flow negative in most recent years"
    fact = sheet.by_metric("operating_cash_flow")
    if fact is None or len(fact.history) < 3:
        return RedFlag(code="negative_ocf", description=desc, status="unknown",
                       detail="fewer than 3 years of operating cash flow")
    last3 = fact.history[-3:]
    negatives = sum(1 for h in last3 if h.value < 0)
    status: Status = "triggered" if negatives >= t.NEGATIVE_OCF_YEARS_OF_LAST_3 else "clear"
    return RedFlag(code="negative_ocf", description=desc, status=status,
                   detail=f"negative in {negatives} of the last 3 years", facts=[fact.id])


def _debt(sheet: FactSheet) -> RedFlag:
    desc = "High debt with weak interest coverage"
    de = sheet.by_metric("debt_to_equity")
    if de is None:
        return RedFlag(code="debt", description=desc, status="unknown",
                       detail="debt to equity not available")
    if de.value <= t.MAX_DEBT_TO_EQUITY:
        return RedFlag(code="debt", description=desc, status="clear",
                       detail=f"debt to equity {de.value}x (limit {t.MAX_DEBT_TO_EQUITY}x)",
                       facts=[de.id])
    cov = sheet.by_metric("interest_coverage")
    if cov is None:
        return RedFlag(code="debt", description=desc, status="unknown",
                       detail=f"debt to equity {de.value}x but interest coverage not available",
                       facts=[de.id])
    status: Status = "triggered" if cov.value < t.MIN_INTEREST_COVERAGE else "clear"
    return RedFlag(code="debt", description=desc, status=status,
                   detail=f"debt to equity {de.value}x, interest coverage {cov.value}x "
                          f"(minimum {t.MIN_INTEREST_COVERAGE}x)",
                   facts=[de.id, cov.id])


def _dilution(sheet: FactSheet) -> RedFlag:
    desc = "Large share dilution"
    fact = sheet.by_metric("dilution")
    if fact is None:
        return RedFlag(code="dilution", description=desc, status="unknown",
                       detail="share count history not available")
    status: Status = "triggered" if fact.value > t.MAX_DILUTION_PCT else "clear"
    return RedFlag(code="dilution", description=desc, status=status,
                   detail=f"share count changed {fact.value:+.1f}% over {fact.period} "
                          f"(limit {t.MAX_DILUTION_PCT}%)",
                   facts=[fact.id])


def _working_capital(sheet: FactSheet) -> RedFlag:
    desc = "Receivables or inventory growing much faster than sales"
    found, rising, details = [], [], []
    for metric in ("receivable_days", "inventory_days"):
        fact = sheet.by_metric(metric)
        if fact is None or len(fact.history) < 2 or fact.history[0].value <= 0:
            continue
        found.append(fact.id)
        first, last = fact.history[0], fact.history[-1]
        change = (last.value / first.value - 1) * 100
        details.append(f"{fact.label.lower()} {first.value:.0f} → {last.value:.0f} "
                       f"({first.period}-{last.period}, {change:+.0f}%)")
        if change > t.MAX_WORKING_CAPITAL_DAYS_INCREASE_PCT:
            rising.append(fact.id)
    if not found:
        return RedFlag(code="working_capital", description=desc, status="unknown",
                       detail="receivable and inventory days not available")
    return RedFlag(code="working_capital", description=desc,
                   status="triggered" if rising else "clear",
                   detail="; ".join(details)
                          + f" (limit +{t.MAX_WORKING_CAPITAL_DAYS_INCREASE_PCT:.0f}%)",
                   facts=found)
