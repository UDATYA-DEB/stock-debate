"""The case file: everything a debate may use, and its compact text rendering.

The rendering is written for small models: one line per fact, the history
inline, and the trend spelled out, so cherry-picking is visible to both sides.
"""

from __future__ import annotations

from pydantic import BaseModel

from stockdebate.data.models import CompanyData, Unavailable
from stockdebate.policy.eligibility import EligibilityResult, check_eligibility
from stockdebate.policy.factsheet import Fact, FactSheet, build_factsheet
from stockdebate.policy.redflags import RedFlag, check_red_flags


class CaseFile(BaseModel):
    symbol: str
    name: str
    sector: str | None
    eligibility: EligibilityResult
    sheet: FactSheet
    red_flags: list[RedFlag]
    unavailable: list[Unavailable]


def build_casefile(data: CompanyData) -> CaseFile:
    sheet = build_factsheet(data)
    return CaseFile(
        symbol=data.symbol,
        name=data.profile.name if data.profile and data.profile.name else data.symbol,
        sector=data.profile.sector if data.profile else None,
        eligibility=check_eligibility(data),
        sheet=sheet,
        red_flags=check_red_flags(data, sheet),
        unavailable=data.unavailable + sheet.unavailable,
    )


def _num(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") if abs(value) < 1e15 else str(value)


def render_fact(f: Fact) -> str:
    line = f"{f.id} {f.label}: {_num(f.value)} {f.unit} ({f.period})"
    if len(f.history) > 1:
        line += " | history: " + ", ".join(f"{h.period} {_num(h.value)}" for h in f.history)
    if f.trend:
        line += (f" | trend {f.trend.direction}; latest is #{f.trend.latest_rank} "
                 f"highest of {f.trend.n_periods}")
    if f.basis:
        line += f" | how: {f.basis}"
    return line


def render_casefile(case: CaseFile) -> str:
    lines = [f"COMPANY: {case.name} ({case.symbol}), sector: {case.sector or 'unknown'}", ""]

    lines.append("FACT SHEET (cite these IDs; amounts in INR crore unless the unit says otherwise):")
    lines += [render_fact(f) for f in case.sheet.facts]

    lines += ["", "RED FLAGS (any triggered flag means the verdict cannot be BUY):"]
    for r in case.red_flags:
        refs = f" [{', '.join(r.facts)}]" if r.facts else ""
        lines.append(f"- {r.status.upper()}: {r.description}. {r.detail}{refs}")

    if case.unavailable:
        lines += ["", "NOT AVAILABLE (do not guess these):"]
        lines += [f"- {u.dataset}" for u in case.unavailable]
    return "\n".join(lines)
