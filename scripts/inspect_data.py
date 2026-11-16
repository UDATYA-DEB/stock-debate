"""Show what data we can gather for a stock, and what's missing.

Usage: python scripts/inspect_data.py RELIANCE [OUTPUT.json]
"""

from __future__ import annotations

import sys
from pathlib import Path

from stockdebate.data.gather import gather
from stockdebate.data.providers.yfinance_provider import YFinanceProvider


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    symbol = sys.argv[1].upper()
    data = gather(symbol, providers=[YFinanceProvider()])

    print(f"\n{symbol} (gathered {data.gathered_at:%Y-%m-%d %H:%M} UTC)\n")
    print("Available:")
    for s in data.statements:
        span = f"{s.periods[-1]} to {s.periods[0]}"
        print(f"  {s.frequency:9} {s.kind:8}  {len(s.periods)} periods ({span}), "
              f"{len(s.rows)} line items  [{s.provenance.provider}]")
    if data.prices:
        p = data.prices.points
        print(f"  prices              {len(p)} days ({p[0].day} to {p[-1].day})  "
              f"[{data.prices.provenance.provider}]")
    if data.shareholding:
        h = data.shareholding
        print(f"  shareholding        promoter~{h.promoter_pct:.1f}%  "
              f"institutions {h.institutions_pct:.1f}%  [{h.provenance.provider}]")

    print("\nUnavailable:")
    for u in data.unavailable or []:
        print(f"  {u.dataset}: {u.reason}")
    if not data.unavailable:
        print("  (none)")

    print("\nData quality issues:")
    for q in data.quality_issues:
        print(f"  {q.dataset}: {q.issue}")
    if not data.quality_issues:
        print("  (none)")

    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(data.model_dump_json(indent=2))
        print(f"\nSaved to {sys.argv[2]}")


if __name__ == "__main__":
    main()
