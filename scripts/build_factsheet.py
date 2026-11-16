"""Gather data for a stock, then show eligibility, the fact sheet and red flags.

Usage: python scripts/build_factsheet.py RELIANCE [OUTPUT.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from stockdebate.data.gather import gather
from stockdebate.data.providers.yfinance_provider import YFinanceProvider
from stockdebate.policy.eligibility import check_eligibility
from stockdebate.policy.factsheet import build_factsheet
from stockdebate.policy.redflags import check_red_flags

MARK = {"pass": "✓", "fail": "✗", "unknown": "?", "clear": "✓", "triggered": "✗"}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    symbol = sys.argv[1].upper()
    data = gather(symbol, providers=[YFinanceProvider()])
    eligibility = check_eligibility(data)
    sheet = build_factsheet(data)
    flags = check_red_flags(data, sheet)

    name = data.profile.name if data.profile and data.profile.name else symbol
    print(f"\n{name} ({symbol})\n")

    print(f"Eligibility: {'ELIGIBLE' if eligibility.eligible else 'NOT ELIGIBLE'}")
    for c in eligibility.checks:
        print(f"  {MARK[c.status]} {c.name}: {c.detail}")

    print("\nFact sheet:")
    for f in sheet.facts:
        trend = f"  trend: {f.trend.direction}, latest rank {f.trend.latest_rank}/{f.trend.n_periods}" if f.trend else ""
        print(f"  {f.id:>4}  {f.label:<40} {f.value:>12,.2f} {f.unit:<15} {f.period}{trend}")
    for u in sheet.unavailable:
        print(f"     -  {u.dataset:<40} unavailable: {u.reason}")

    print("\nRed flags:")
    for r in flags:
        refs = f"  [{', '.join(r.facts)}]" if r.facts else ""
        print(f"  {MARK[r.status]} {r.status:<9} {r.description}: {r.detail}{refs}")

    if len(sys.argv) > 2:
        out = {
            "eligibility": eligibility.model_dump(),
            "factsheet": sheet.model_dump(mode="json"),
            "red_flags": [r.model_dump() for r in flags],
        }
        Path(sys.argv[2]).write_text(json.dumps(out, indent=2, default=str))
        print(f"\nSaved to {sys.argv[2]}")


if __name__ == "__main__":
    main()
