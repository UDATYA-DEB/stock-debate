"""Generate one agent's opening argument and check its claims.

Usage:
  python scripts/run_opening.py TITAN --role bull
  python scripts/run_opening.py TITAN --role bear --url https://... --model gemma3:4b --token ...

URL, model and token default to the values saved from the UI (.env):
BULL_URL / BULL_MODEL, or BEAR_URL / BEAR_MODEL / BEAR_TOKEN.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from stockdebate.data.gather import gather
from stockdebate.data.providers.yfinance_provider import YFinanceProvider
from stockdebate.debate.agent import opening_round
from stockdebate.debate.casefile import build_casefile
from stockdebate.llm.clients import make_debater
from stockdebate.llm.config import DEFAULT_LANGFUSE_HOST, load_saved
from stockdebate.obs.tracing import Observability

RUNS = Path(__file__).resolve().parents[1] / "runs"
MARK = {"supported": "✓", "misquoted": "✗", "unsupported": "✗"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--role", choices=["bull", "bear"], default="bull")
    p.add_argument("--url")
    p.add_argument("--model")
    p.add_argument("--token")
    args = p.parse_args()

    saved = load_saved()
    url = args.url or saved.get(f"{args.role}_url")
    model = args.model or saved.get(f"{args.role}_model")
    token = args.token or (saved.get("bear_token") if args.role == "bear" else None)
    if not url or not model:
        sys.exit(f"No {args.role} endpoint/model: pass --url and --model, or save them in the UI.")

    symbol = args.symbol.upper()
    print(f"Gathering data for {symbol}...")
    case = build_casefile(gather(symbol, providers=[YFinanceProvider()]))
    if not case.eligibility.eligible:
        print("Note: this stock is NOT eligible; running anyway for testing.")

    obs = Observability.from_keys(saved.get("langfuse_public_key"), saved.get("langfuse_secret_key"),
                                  saved.get("langfuse_host", DEFAULT_LANGFUSE_HOST))
    print(f"Asking the {args.role} agent ({model}); Langfuse tracing {'on' if obs.enabled else 'off'}...")
    run_id = f"{symbol}-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        with obs.trace(f"opening {symbol}", session_id=run_id, tags=[symbol, args.role, "opening"],
                       metadata={"model": model}):
            turn, check_list = opening_round(args.role, case, make_debater(url, model, token), model, obs)
    finally:
        obs.flush()
    print(f"\nPrompt {turn.prompt_source}, ~{turn.prompt_tokens_est} tokens, "
          f"{turn.attempts} attempt(s), {turn.latency_s}s")
    if turn.error:
        print(f"FAILED: {turn.error}\nLast raw output:\n{turn.raw_outputs[-1][:2000]}")
    else:
        print(f"\nThesis: {turn.thesis}\nCase strength: {turn.case_strength}\n")
        checks = {c.claim_id: c for c in check_list}
        for c in turn.claims:
            chk = checks[c.id]
            rng = (f" [forecast {c.forecast_low}-{c.forecast_high} {c.forecast_unit}]"
                   if c.type == "forecast" else "")
            print(f"{MARK[chk.status]} {c.id} ({c.type}, {c.importance}) {c.text}{rng}")
            print(f"     cites {c.citations or '-'} -> {chk.status}: {chk.detail}")
        counts = {s: sum(1 for x in checks.values() if x.status == s) for s in MARK}
        print(f"\nSummary: {counts}")

    out_dir = RUNS / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"opening-{args.role}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(turn.model_dump_json(indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
