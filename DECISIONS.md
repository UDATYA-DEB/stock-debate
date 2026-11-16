# Stock Debate Project — Decisions Log

A multi-agent system where a bull agent and a bear agent debate whether an Indian
stock is a long-term buy, a validator fact-checks their claims, and a judge gives a
verdict. Built as an applied-AI portfolio project. **Not financial advice.**

Status legend: ✅ decided · 🟡 proposed, awaiting confirmation · ❓ open · ⏸️ postponed

---

## 1. Problem definition

| # | Decision | Status |
|---|----------|--------|
| 1.1 | Investment horizon: long term, each call is a 12-month outlook | ✅ |
| 1.2 | Benchmark: market index (Nifty 50 for v1); custom benchmarks later | ✅ |
| 1.3 | Output: BUY / HOLD / SELL + confidence score + concise judge rationale | ✅ |
| 1.4 | Success measured on both outcome (vs benchmark) and reasoning quality, tracked separately | ✅ |
| 1.5 | Market: India only for v1 | ✅ |

## 2. Cadence and memory

| # | Decision | Status |
|---|----------|--------|
| 2.1 | Decision frequency: monthly | ✅ |
| 2.2 | Evaluation window: each call judged over the following 12 months, not 1 month | ✅ |
| 2.3 | Each month builds on the previous thesis ("what changed?") instead of starting over | ✅ |
| 2.4 | Stability rule: verdict changes only when something material changed, and the judge must state what | ✅ |
| 2.5 | Evaluation mode: both backtesting (development) and live tracking (long-running record) | ✅ |
| 2.6 | Phase 1 builds the application and checks debate quality (meaningful vs generic); backtesting deferred to a later phase | ✅ |

**Known pitfalls to handle:** overlapping 12-month windows are not independent samples;
backtests must be point-in-time; LLMs may remember what happened to famous stocks.

## 3. Policy framework (layers)

| # | Decision | Status |
|---|----------|--------|
| 3.1 | Layered policy instead of a flat weighted checklist | ✅ |
| 3.2 | Banks and NBFCs excluded from v1 (they need different metrics) | ✅ |
| 3.3 | Red flags are vetoes that block a BUY, not lost points | ✅ |
| 3.4 | Thresholds relative to sector peers and own history where possible, not only absolute | ✅ |
| 3.5 | History window: look back up to 5 years and use all data available within it (5 years is a maximum, not a requirement). The fact sheet states how many years were used | ✅ |
| 3.6 | Minimum history: 3 years, since several policies use 3-year averages and growth rates; stocks with less are ineligible for now | ✅ |
| 3.7 | Starting thresholds in `stockdebate/policy/thresholds.py`: market cap ≥ ₹5,000 cr, daily traded value ≥ ₹10 cr, pledging ≤ 5%, D/E ≤ 1 (else coverage ≥ 3x), dilution ≤ 10%, receivable/inventory days rise ≤ 30%, negative OCF in < 2 of last 3 years | 🟡 |
| 3.8 | Valuation facts: P/E (TTM EPS when 4 consecutive quarters exist), P/E percentile vs own history, FCF yield, and reverse-DCF implied growth on two bases (free cash flow vs EV = strict; earnings vs market cap = lenient). Assumptions: 12% discount rate, 5% terminal growth, 10 years, 3-year average base | 🟡 |
| 3.9 | Valuation vs sector peers deferred (no peer data source yet) | ⏸️ |

- **Layer 0 – Eligibility:** non-financial, minimum market cap and liquidity; history window up to 5 years (see 3.5).
- **Layer 1 – Red flags (veto):** high or rising promoter pledging; auditor resignation or qualified
  opinion; negative operating cash flow in most recent years; high debt with weak interest coverage;
  large recent dilution; receivables/inventory growing much faster than revenue.
- **Layer 2 – Quality (weighted score):** ROCE vs peers and its stability; revenue and profit growth
  and consistency; earnings quality (cash conversion); evidence-backed competitive advantage;
  capital allocation track record.
- **Layer 3 – Valuation and expectations:** valuation vs own history and peers (cycle-adjusted);
  growth implied by the current price (reverse DCF) vs plausible growth.
- **Layer 4 – What changed (monthly):** recent quarterly trend and guidance; broken thesis assumptions.

**Verdict mapping:**
- BUY: eligible, no red flags, quality above threshold, valuation attractive
- SELL: red flag appears, or thesis broken, or valuation extreme
- HOLD: everything else

Thresholds (e.g. ROCE ~15%, pledging <5%) came from blog and broker sources that disagree
with each other. They are starting points to calibrate, not rules.

## 4. Division of labour

| # | Decision | Status |
|---|----------|--------|
| 4.1 | Numeric metrics are computed by code into a fact sheet with citable IDs; LLMs don't calculate | ✅ |
| 4.2 | Agents may not state any number not in the fact sheet or quoted from a document | ✅ |
| 4.3 | Agents debate interpretation: explanation, durability, expectations, red-flag context, what changed | ✅ |
| 4.4 | Claims are tagged as Fact, Interpretation, or Forecast (forecasts given as ranges) | ✅ |
| 4.5 | Debate format: opening → rebuttal (must address specific opposing claims) → closing with concessions | ✅ |
| 4.6 | Agents argue their side by default but may state their case is weak | ✅ |
| 4.7 | Research happens in two controlled phases: (1) preparation before the debate, (2) an optional recess after round 3. No free-form searching during rounds | ✅ |
| 4.7a | Recess: if the debate has no clear conclusion after round 3, both agents may search and gather new evidence, then debate rounds 4-5 using all data; judge then decides with reasoning | ✅ |
| 4.7b | Recess trigger measured from the argument graph (e.g. key claims still disputed, open questions unanswered), not left to the debaters | ✅ |
| 4.7c | Each agent proposes a limited number of search queries aimed at specific disputed claims or open questions; code runs the searches | ✅ |
| 4.7d | Equal research budget for both sides; all new evidence goes into a shared pool that both agents and the validator see | ✅ |
| 4.7e | Recess evidence is stored, dated, given IDs, and validated exactly like preparation evidence | ✅ |
| 4.7f | Sources tagged by reliability (official filing > established news > blog/forum) | ✅ |
| 4.7g | If no recess is needed and the debate has converged, it ends early (closing, then judge) | ✅ |
| 4.8 | Debate length: up to 5 rounds (a maximum, not a requirement); debates end as soon as they converge, because forcing extra rounds encourages filler and fabrication | ✅ |
| 4.9 | Each round has a distinct purpose: opening → rebuttal → cross-examination → answers. The closing is a separate final statement after whichever round the debate ends on | ✅ |
| 4.10 | Agents receive a structured summary of earlier rounds, not the full transcript | ✅ |
| 4.11 | Convergence is checked by code from the argument graph after every round (e.g. no new claims, key claims resolved, positions unchanged) | ✅ |
| 4.12 | Minimum of 2 rounds, so each side responds to the other at least once | ✅ |
| 4.13 | Every debate ends with a short closing statement (concessions and final position) in which no new facts are allowed | ✅ |
| 4.14 | Track fabrication rate per round, to test whether later rounds fabricate more | ✅ |

## 5. Validation and judging

| # | Decision | Status |
|---|----------|--------|
| 5.1 | Independent validator fact-checks every Fact claim from both sides | ✅ |
| 5.2 | Verdict labels: supported, misquoted, unsupported, contradicted, out-of-window (cherry-picked = stretch) | ✅ |
| 5.3 | Validation is mostly code (fact-ID lookup, quote matching); LLM only for paraphrases | ✅ |
| 5.4 | Blind validation: validator does not know which side made a claim | ✅ |
| 5.5 | Judge receives surviving facts plus a summary of failed claims per side (rate and type) | ✅ |
| 5.6 | Failures weaken the side that made them and lower confidence; they do not strengthen the other side | ✅ |
| 5.7 | Validator accuracy measured by planting fabricated claims | ✅ |
| 5.8 | Validation timing: code checks between every round (failures shown to both agents), LLM checks once at the end | ✅ |
| 5.9 | Cherry-picking detection is in v1 (hard requirement) | ✅ |
| 5.10 | Two independent checks per fact: neutral validator (blind, is it accurate?) and opposing debater (in context, is it misleading?) | ✅ |
| 5.11 | Every fact claim states metric, period, and comparison basis, so representativeness can be checked | ✅ |
| 5.12 | Code computes a neutral representativeness check (e.g. where the quoted period sits in the full history, trend direction) for the validator | ✅ |
| 5.13 | When a claim cites a metric, the opponent's next round automatically receives that metric's full history and trend summary | ✅ |
| 5.14 | An opponent's "misleading" challenge must cite data and is itself validated; unsupported challenges count against the challenger | ✅ |
| 5.15 | Judge sees, per fact: validator verdict, representativeness result, opponent challenge, and whether the challenge held up | ✅ |
| 5.16 | Penalty severity: fabrication is the maximum penalty; cherry-picking is highlighted to the judge and penalized, but less severely | ✅ |

## 6. Models

| # | Decision | Status |
|---|----------|--------|
| 6.1 | Debaters: 7-8B open models; judge: a stronger model | ✅ |
| 6.2 | Bull and bear use different model families to reduce shared blind spots | ✅ |
| 6.3 | LLM validator uses a judge-tier model (Gemini), not a 7-8B model | ✅ |
| 6.4 | Small debaters get focused, pre-selected evidence and structured (JSON) output | ✅ |
| 6.5 | Hardware: RTX 4060 Laptop, 8 GB VRAM; 24 GB system RAM (WSL currently sees 11 GB); 20 cores. Debaters run locally one at a time (quantized ~8B) | ✅ |
| 6.6 | Starting debater models: open-source Qwen (8-9B) vs Gemma (small) via Ollama; tested early | ✅ |
| 6.7 | Judge and LLM validator via free API for development (14B+ won't fit in 8 GB VRAM) | ✅ |
| 6.8 | Option for full backtest: run a ~14B judge locally with partial CPU offload (slow, but no rate limits). Postponed until backtesting phase | ⏸️ |
| 6.9 | Raise WSL memory limit to ~16 GB via .wslconfig. Not needed yet; revisit if memory becomes a limit | ⏸️ |
| 6.10 | Judge: Google Gemini (free tier) | ✅ |
| 6.11 | Runtime split: one debater local (Ollama), one on a Kaggle notebook exposed as an endpoint, Gemini judge; integrated with LangChain by swapping endpoints | ✅ |
| 6.13 | Guardrails for the remote debater: health check before each debate, timeouts and retries, checkpoint the argument graph after every round so a debate can resume, authenticated tunnel | ✅ |
| 6.12 | Pin exact model versions, quantization, temperature, and seed on every runtime for reproducibility | ✅ |

## 7. Context management

| # | Decision | Status |
|---|----------|--------|
| 7.1 | Don't stack the full transcript; keep debate state outside the model | ✅ |
| 7.2 | Debate state stored as an argument graph: claims, evidence, support/attack/question edges, verdicts | ✅ |
| 7.3 | Graph built by code from the agents' structured JSON output (agents say which claim they respond to); no LLM extraction | ✅ |
| 7.4 | Each agent's prompt is assembled from the graph per round, within a fixed token budget | ✅ |
| 7.5 | A short narrative summary per round supplements the graph | ✅ |
| 7.6 | Judge receives the full graph; graph-based strength scoring (QBAF-style) is a possible input to confidence | ✅ |
| 7.7 | Surviving claims carry forward as next month's thesis memory | ✅ |
| 7.8 | Storage: NetworkX in memory, persisted to SQLite/JSON per debate (no graph database) | ✅ |

## Open questions

- Tapetide: user to sign up, then test as a second provider
- Backtest judge capacity (deferred with backtesting)

## 8. Data sources

| # | Decision | Status |
|---|----------|--------|
| 8.1 | yfinance (Python) for prices and basic financials | ✅ |
| 8.2 | Free MCP/hosted services for India-specific data (quarterly history, shareholding, pledging, filings) | ✅ |
| 8.3 | Free web search tool for qualitative research (statements, commentary, context) | ✅ |
| 8.4 | Free news sources (e.g. GDELT, publisher RSS) for recent events | ✅ |
| 8.5 | Every fetched item stored with source URL and publication date, so it is citable and point-in-time | ✅ |
| 8.6 | Option C: build Phase 1 on yfinance with a swappable provider interface; add Tapetide as a second provider if it works | ✅ |
| 8.7 | Missing datasets are reported as "unavailable" and gaps in periods as data quality issues; never silently passed | ✅ |
| 8.8 | Pledging and shareholding history to be extracted from annual reports / exchange filings in the preparation phase, as citable documents | ✅ |
| 8.9 | Gap-filling step (search → find official document → extract with evidence → overlap and sanity checks → lower-reliability tag) is deferred until after Phase 1 shows debates are meaningful | ⏸️ |
| 8.10 | Phase 1 runs on yfinance data only; gaps stay marked "unavailable" | ✅ |

**yfinance test on RELIANCE.NS (2026-11-16):**
- Annual income, balance sheet, cash flow: 5 years (FY2022-FY2026)
- Quarterly income: 5 quarters, with one quarter missing (Sep 2025)
- Quarterly balance sheet: half-yearly only (matches Indian reporting)
- Quarterly cash flow: empty
- Price history: back to 1996
- Holders: current insider/institution %; no pledging, no history

So yfinance alone can't supply the 8-12 quarter histories needed for cherry-picking checks,
or pledging data. Candidate MCP servers that claim to cover these (unverified):
FinStack MCP (MIT, self-hosted), Tapetide (hosted, free tier ~50 calls/day), india-market-mcp
(no pledging). Search candidates: Tavily (free ~1,000 credits/month), self-hosted SearXNG.
News: GDELT (free, no key), NewsAPI free tier (24-hour delay, development only).

**FinStack MCP test (v0.10.0, 2026-11-16):**
- Financials and quarterly results are wrappers around yfinance: no extra history (quarterly results capped at 4 quarters)
- Pledging and shareholding tools crash (bug: reuses an HTTP client) and call an unofficial NSE endpoint
- Direct request to that endpoint: NSE homepage returned 403 (blocked), endpoint returned 404 (no longer exists)
- Conclusion: FinStack adds nothing over yfinance for our needs

## 9. Architecture (see ARCHITECTURE.md)

| # | Decision | Status |
|---|----------|--------|
| 9.1 | A triggered red flag doesn't cancel the debate, but the judge cannot return BUY; unknown flags lower confidence | ✅ |
| 9.2 | Simultaneous rounds: both agents respond to the same state; bull (local) and bear (Kaggle) run in parallel | ✅ |
| 9.3 | No silent model fallback: if the Kaggle endpoint stays down, the run is paused and marked incomplete | ✅ |
| 9.4 | Confidence: judge proposes from the policy rubric; code applies fixed deductions for fabrication, cherry-picking and unknown red flags (weights TBD) | ✅ |
| 9.5 | Plain Python orchestrator for Phase 1; LangChain for model clients and structured output; LangGraph possibly later | ✅ |
| 9.6 | Build order as in ARCHITECTURE.md section 8 (ROCE and cash conversion were planned as user exercises; implemented by Claude at the user's request) | ✅ |
| 9.7 | Streamlit UI: setup screen (Gemini key + 2 endpoints, example placeholders) → "List models" per endpoint with a dropdown → health check of all three (connect, model exists, tiny test prompt) → main screen | ✅ |
| 9.8 | Settings saved to a local, git-ignored .env only when the user ticks "Remember"; the Gemini key is sent in a header, never in URLs | ✅ |

## 10. Observability (Langfuse)

| # | Decision | Status |
|---|----------|--------|
| 10.1 | Langfuse for traces and prompt management (SDK v5); optional: blank keys = tracing off, built-in prompts | ✅ |
| 10.2 | Prompts are fetched from Langfuse (label `production`); role-specific text lives in the prompt `config`. Code defaults are pushed once if missing (never overwrite) and used as fallback when Langfuse is unreachable | ✅ |
| 10.3 | Trace layout: trace per run (session id, tags: symbol/role/round) → agent span per role → generation per LLM attempt, linked to the prompt version, with token usage | ✅ |
| 10.4 | Validator results recorded as scores on the agent span: valid_output, claims_supported_pct, fabrications (with details as comment) | ✅ |
| 10.5 | Langfuse is a 4th health check on the setup screen; missing prompts block Start until pushed | ✅ |
| 10.6 | Cloud vs self-hosted Langfuse: user's choice (host field) | ❓ |
