"""Code validator, first version: are the agents' numbers and citations real?

Checks every claim (DECISIONS 4.2, 5.2, 5.3):
- citations must be fact IDs that exist
- every number in the claim text must match a value in the facts it cites
  (the latest value, any history value, or the CAGR), within rounding
- fact claims must cite something

Not yet: document quotes, representativeness, challenges (milestone 4).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from stockdebate.debate.schemas import Claim
from stockdebate.policy.factsheet import FactSheet

Status = Literal["supported", "misquoted", "unsupported"]

# Numbers like 1,057,219.5  38.43  -0.33  12   (but not parts of FY2026, Q2, F12 or B1-2)
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])-?\d[\d,]*(?:\.\d+)?")
_IDS = re.compile(r"\b(?:[BR]\d+-\d+|F\d+|E\d+)\b")  # claim, fact and evidence IDs


class ClaimCheck(BaseModel):
    claim_id: str
    status: Status
    detail: str


def numbers_in(text: str) -> list[tuple[str, float]]:
    out = []
    for match in _NUMBER.finditer(_IDS.sub(" ", text)):
        raw = match.group().rstrip(",")
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if raw.isdigit() and 1990 <= value <= 2100:
            continue  # a year
        out.append((raw, value))
    return out


def _decimals(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def _matches(raw: str, value: float, candidates: list[float]) -> bool:
    """True if `value` equals a candidate when the candidate is rounded like `raw`."""
    places = _decimals(raw)
    for c in candidates:
        for sign in (1, -1):  # "fell 0.33%" may refer to a value of -0.33
            if round(sign * c, places) == value or abs(sign * c - value) <= max(1e-9, abs(c) * 0.005):
                return True
    return False


def check_claim(claim: Claim, sheet: FactSheet) -> ClaimCheck:
    unknown = [c for c in claim.citations if sheet.get(c) is None]
    if unknown:
        return ClaimCheck(claim_id=claim.id, status="unsupported",
                          detail=f"cites {', '.join(unknown)}, which does not exist")

    numbers = numbers_in(claim.text)
    if claim.type == "fact" and not claim.citations:
        return ClaimCheck(claim_id=claim.id, status="unsupported", detail="fact claim without a citation")
    if numbers and not claim.citations:
        return ClaimCheck(claim_id=claim.id, status="unsupported",
                          detail=f"states {numbers[0][0]} without citing a fact")

    candidates: list[float] = []
    for fid in claim.citations:
        fact = sheet.get(fid)
        candidates.append(fact.value)
        candidates += [h.value for h in fact.history]
        if fact.trend and fact.trend.cagr_pct is not None:
            candidates.append(fact.trend.cagr_pct)
    if claim.type == "forecast":  # the forecast's own range may appear in its text
        candidates += [v for v in (claim.forecast_low, claim.forecast_high) if v is not None]

    wrong = [raw for raw, value in numbers if not _matches(raw, value, candidates)]
    if wrong:
        return ClaimCheck(claim_id=claim.id, status="misquoted",
                          detail=f"{', '.join(wrong)} not found in cited facts "
                                 f"{', '.join(claim.citations)}")
    return ClaimCheck(claim_id=claim.id, status="supported",
                      detail="numbers match cited facts" if numbers else "citations exist")


def check_claims(claims: list[Claim], sheet: FactSheet) -> list[ClaimCheck]:
    return [check_claim(c, sheet) for c in claims]
