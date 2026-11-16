# Architecture — Phase 1

Phase 1 goal: run complete debates on Indian stocks and judge whether they are
meaningful or generic. Backtesting, gap-filling and a UI come later.

Numbers in brackets (e.g. [4.7a]) refer to `DECISIONS.md`. Items marked **(P)** are
new proposals in this document that still need confirmation.

---

## 1. Overview

```
                        ┌──────────────────────────────────────────┐
  symbol, month ──────► │ A. PREPARATION  (once per stock / month) │
                        │                                          │
                        │  Data layer ─► Eligibility ─► Fact sheet │
                        │                  │ (stop if     │        │
                        │                  │  ineligible) ▼        │
                        │              Red-flag check   Research   │
                        │                               collector  │
                        │  Previous thesis ─► "What changed" diff  │
                        └───────────────────┬──────────────────────┘
                                            │  CASE FILE
                                            ▼
                        ┌──────────────────────────────────────────┐
                        │ B. DEBATE LOOP  (rounds 1..5, max)       │
                        │                                          │
                        │   ┌─► Prompt builder (graph → views)     │
                        │   │        │                 │           │
                        │   │   Bull agent        Bear agent       │
                        │   │   (local Ollama)    (Kaggle endpoint)│
                        │   │        └──────┬──────────┘           │
                        │   │        Schema check (retry once)     │
                        │   │               ▼                      │
                        │   │        Code validator                │
                        │   │               ▼                      │
                        │   │        Argument graph update         │
                        │   │        + checkpoint                  │
                        │   │               ▼                      │
                        │   │        Convergence check ──converged─┼──┐
                        │   │               │ not converged        │  │
                        │   │      after round 3: recess trigger?  │  │
                        │   │        │yes            │no           │  │
                        │   │     RECESS             │             │  │
                        │   │  (targeted search,     │             │  │
                        │   │   new evidence)        │             │  │
                        │   └────────┴───────────────┘             │  │
                        │        (stop after round 5)──────────────┼──┤
                        └──────────────────────────────────────────┘  │
                                                                      ▼
                        ┌──────────────────────────────────────────┐
                        │ C. CLOSING & JUDGEMENT                   │
                        │  Closing statements (no new facts)       │
                        │  Gemini validator (blind, residual)      │
                        │  Judge (Gemini) ─► post-judge rule check │
                        └───────────────────┬──────────────────────┘
                                            ▼
                        ┌──────────────────────────────────────────┐
                        │ D. PERSIST                               │
                        │  run record · metrics · next thesis      │
                        └──────────────────────────────────────────┘
```

**Code vs LLM**

| Code (deterministic) | LLM |
|---|---|
| Data gathering, eligibility, fact sheet, red flags | Bull agent (Qwen, local) |
| Representativeness and trend summaries | Bear agent (Gemma, Kaggle) |
| Citation and quote checks, challenge checks | Gemini validator (only what code can't check) |
| Argument graph, prompt building | Judge (Gemini) |
| Convergence and recess triggers | Agents' recess query proposals |
| Search execution, post-judge rule checks | |

---

## 2. Phase A — Preparation

Runs once per stock per month and produces a **case file**: everything the debate
is allowed to use.

1. **Data layer** *(built)* — `gather(symbol, providers)` returns `CompanyData`
   with statements, prices, shareholding, unavailable datasets and quality issues [8.6, 8.7].
2. **Eligibility (Layer 0)** — non-financial, liquidity, ≥3 years of history [3.2, 3.6].
   Ineligible stocks stop here with a recorded reason; no debate.
3. **Fact sheet** — code computes every metric the policies need, using up to
   5 years [3.5]. Each item gets an ID (`F1`, `F2`, …) and includes value, unit,
   period, source, and its **full history + trend summary** (used for cherry-picking
   checks [5.12, 5.13]). Includes valuation vs history/peers and the growth implied
   by the current price [Layer 3].
4. **Red-flag check (Layer 1)** — each flag is `triggered`, `clear`, or `unknown`
   (data unavailable). Unknown is never treated as clear [8.7].
5. **Research collector** — search and news queries generated from a fixed template
   per stock (e.g. "<company> management commentary", "<company> results"). Results are
   stored as evidence items `E1`, `E2`, … with URL, publication date, reliability tag,
   and text chunks [4.7, 4.7f, 8.5].
6. **Memory** — load last month's thesis (surviving claims + verdict) and compute
   **what changed** between last month's fact sheet and this one (Layer 4) [2.3, 7.7].

**Red flags and missing data (P):**
- A triggered red flag does **not** cancel the debate. The debate still runs, because
  "is there an innocent explanation?" is one of the things agents argue about [4.3].
  But the judge **cannot return BUY** while a red flag is triggered [3.3].
- `unknown` flags (e.g. pledging unavailable) don't block anything, but are listed for
  the judge and **lower confidence**.

---

## 3. Phase B — Debate loop

### 3.1 Round structure

| Round | Purpose | |
|---|---|---|
| 1 | Opening | |
| 2 | Rebuttal | convergence checks start here (min 2 rounds) [4.12] |
| 3 | Cross-examination (questions to the opponent) | recess check after this round |
| *recess* | targeted research, only if triggered [4.7a] | |
| 4 | Answers (with any new evidence) | |
| 5 | (last possible round) | |
| closing | separate final statement, no new facts [4.9, 4.13] | |

**Simultaneous rounds (P):** in each round, both agents respond to the state at the
end of the previous round, at the same time. This removes first-mover advantage,
and since the bull runs locally and the bear on Kaggle, both can run **in parallel**,
which halves debate time. Attacks on a claim made in round N happen in round N+1.

### 3.2 One round, step by step

1. **Prompt builder** — builds each agent's view from the argument graph within a fixed
   token budget [7.4]: role and rules; the narrative summary [7.5]; attacks on the
   agent's claims not yet answered; the opponent's strongest standing claims; questions
   asked of the agent; evidence slices for the claims involved, including full
   histories of metrics the opponent cited [5.13]; validator feedback from last round.
2. **Agent call** — through LangChain [6.11] with structured output (schema below).
3. **Schema check** — malformed output is retried once with the error message;
   if it fails again, that agent's turn is recorded as empty.
4. **Code validator** [5.3] — for every fact claim and every challenge:
   - fact-sheet ID exists and the number matches → else *misquoted / unsupported*
   - document quote appears in the cited evidence → else *unsupported*
   - claim date within the allowed window → else *out-of-window*
   - representativeness check for metric claims (rank in history, trend) [5.12]
   - challenges must cite data and are checked the same way [5.14]
5. **Graph update** — add claim nodes and `supports / attacks / asks / answers / cites`
   edges; set statuses (standing, refuted, conceded, unanswered) [7.2, 7.3].
6. **Checkpoint** — save the graph and round outputs, so a debate can resume [6.13].
7. **Convergence check** (from round 2) [4.11] — converged if *no new claims this round*,
   or *all high-importance claims are resolved*, or *neither side changed position*.
8. **Recess check** (after round 3 only) [4.7b] — trigger if not converged and some
   high-importance claims are still disputed or questions are unanswered for lack of
   evidence.

### 3.3 Agent output schema (sketch)

```json
{
  "claims": [
    {
      "id": "B2-1",
      "type": "fact | interpretation | forecast",
      "text": "Q2 FY27 revenue grew 14% year on year",
      "metric": "revenue", "period": "Q2 FY27", "basis": "vs Q2 FY26",
      "citations": ["F12"],
      "quote": null,
      "forecast_range": null,
      "responds_to": "R1-3",
      "relation": "attacks | supports | answers | null",
      "importance": "high | medium | low"
    }
  ],
  "challenges": [
    {"target": "R1-2", "kind": "cherry_picked | misquoted | unsupported",
     "argument": "...", "citations": ["F12"]}
  ],
  "questions": [{"to_claim": "R1-4", "text": "..."}],
  "concessions": ["R1-1"],
  "case_strength": "strong | moderate | weak"
}
```

Claim IDs are assigned by code, not the model (the model's IDs are rewritten).
`case_strength` lets an agent say its case is weak [4.6].

### 3.4 Recess

1. Each agent proposes up to N search queries, each tied to a disputed claim or open
   question [4.7c]. Same N for both sides [4.7d].
2. Code runs the searches and stores results as new evidence items, with URL,
   date and reliability tag [4.7e, 4.7f].
3. New evidence goes into the shared pool for both agents and the validator.

---

## 4. Phase C — Closing and judgement

1. **Closing statements** — each side states concessions and final position. Code
   rejects any fact claim not already in the graph [4.13].
2. **Gemini validator** [5.1, 6.3] — blind (no side labels) [5.4]; only for claims code
   couldn't settle (paraphrases, multi-fact claims), plus qualitative cherry-picking review.
3. **Judge input package** [5.5, 5.15]:
   - policy results: eligibility, red flags (triggered / clear / unknown), code-computed
     quality and valuation metrics
   - the argument graph: surviving claims, refuted claims, concessions, open disputes
   - per-side failure summary: fabrications (maximum penalty), misquotes,
     cherry-picks (lesser penalty) [5.16]
   - previous verdict and what changed [2.4]
4. **Judge output:**
   ```json
   {
     "verdict": "BUY | HOLD | SELL",
     "confidence": 0.0,
     "policy_assessment": [{"policy": "...", "met": true, "claims": ["B2-1"]}],
     "rationale": "...",
     "key_claims": ["B2-1", "R3-2"],
     "changed_from_previous": false,
     "material_change": null
   }
   ```
5. **Post-judge rule check (code)** — BUY is impossible with a triggered red flag;
   if the verdict changed from last month, `material_change` must be filled [2.4];
   the rationale may only rely on surviving claims. On violation, the judge is asked
   once more with the violation explained; if it still fails, the run is marked invalid.

**Confidence (P):** the judge proposes a confidence from the weighted policy rubric;
code then applies fixed deductions for each side's fabrication and cherry-picking
rates and for `unknown` red flags. Exact weights to be decided together.

---

## 5. Phase D — Persist

Each run saves to `runs/<symbol>/<month>/`:
- case file, full argument graph, raw agent outputs, validator results, judge output
- **metrics**: rounds used, convergence reason, recess yes/no, fabrication /
  misquote / cherry-pick counts **per round and per agent** [4.14], token usage, latency
- next month's thesis: surviving claims + verdict [7.7]

An index in SQLite lists all runs for later comparison.

---

## 6. Cross-cutting

- **LLM clients** — one module creating the three LangChain clients from config:
  bull (Ollama, local), bear (OpenAI-compatible Kaggle URL), judge/validator (Gemini).
  Model versions, quantization, temperature and seed pinned in config [6.12].
- **Remote health** — health check of the Kaggle endpoint before each debate;
  timeouts and retries per call; resume from the last checkpoint after a failure [6.13].
  **(P)** If the endpoint stays down, the run is paused and marked incomplete. It is
  **not** silently switched to another model, because that would change the experiment.
- **Observability (Langfuse)** — every run is a trace; each agent turn is a span with one
  generation per LLM attempt, linked to the prompt version that produced it; validator results
  are scores. Prompts are managed in Langfuse, with code defaults as fallback (DECISIONS §10).
- **Cache** — every LLM and search call cached by its inputs, so re-runs are free.
- **Secrets** — API keys and the tunnel token in `.env`, never in code or logs.
- **Orchestration (P)** — a plain Python orchestrator (explicit loop with the checks
  above) for Phase 1, using LangChain only for model clients and structured output.
  LangGraph is an option later if the flow grows; starting plain keeps every step
  visible while learning.

---

## 7. Module layout

```
stockdebate/
  data/          ✅ models, providers (yfinance), gather
  policy/        eligibility, fact sheet metrics, red flags, trend/representativeness
  research/      search + news clients, evidence store, chunking/retrieval
  debate/        schemas, prompt builder, argument graph, code validator,
                 convergence + recess triggers, recess, orchestrator
  judge/         Gemini validator, judge, post-judge rules, confidence
  memory/        thesis load/save, "what changed" diff
  llm/           client factory, cache, health checks, config
  storage/       run records, SQLite index
scripts/         CLI entry points (inspect_data.py ✅, run_debate.py)
tests/
```

---

## 8. Build order

| # | Milestone | Proves |
|---|---|---|
| 1 | Data layer ✅ | we know what data exists |
| 2 | Eligibility, fact sheet, red flags, valuation (code only) ✅ | metrics are correct and testable |
| 3 | Claim schema + **one agent's opening** (local) — built, awaiting real model test | a 7-8B model can produce structured, cited claims |
| 4 | Code validator + argument graph | fabrications are caught; graph builds from output |
| 5 | Two agents, full loop (local + Kaggle), checkpoints, convergence | a debate runs end to end |
| 6 | Gemini validator + judge + post-judge rules | a verdict comes out |
| 7 | **Phase 1 check:** run ~10 stocks, read the debates | meaningful or generic? |
| 8 | Research collector + recess | evidence beyond the fact sheet helps |
| 9 | Memory (monthly thesis) + simple report view | month-to-month operation |

Milestone 3 is the earliest real test of the idea: if small models can't produce
cited, structured claims, we learn it before building the rest.
