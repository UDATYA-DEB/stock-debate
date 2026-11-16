"""Default prompt texts.

The live prompts are managed in Langfuse (edit them there). These defaults are:
- pushed to Langfuse once, when a prompt doesn't exist there yet
- used as a fallback when Langfuse isn't configured or can't be reached

Templates use Langfuse's {{variable}} syntax. Role-specific text lives in the
prompt's `config` so it is editable in Langfuse too.
"""

OPENING_PROMPT = "debate-opening"

_RULES = """\
RULES
1. Use only the case file below. Do not use outside knowledge, news, or memory of this company.
2. Every number you write must come from the fact sheet, written exactly as shown, with its unit,
   and the claim must cite that fact's ID. A number you can't cite must not appear.
3. Claim types:
   - fact: a figure or status from the case file, with its citation.
   - interpretation: what the facts mean (cite the facts it builds on).
   - forecast: what you expect next; give a range in forecast_low / forecast_high / forecast_unit,
     and cite the facts that justify it.
4. Don't cherry-pick. Each fact shows its history and trend. If you cite the best year while the
   trend is falling, your opponent will expose it.
5. Deal honestly with red flags and missing data that matter to your case.
6. Make 3 to 6 claims, most important first, and mark their importance.
7. If your case is weak, say so with case_strength "weak". Inventing facts is the worst
   possible failure: it is always detected and heavily penalised.
8. Reply with JSON only, matching the required schema."""

OPENING_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are {{stance}}, in a structured debate about whether {{company}} ({{symbol}}) "
            "is a BUY for a long-term investor. Horizon: the next 12 months, compared with the "
            "Nifty 50 index.\n\n" + _RULES
        ),
    },
    {
        "role": "user",
        "content": "This is the OPENING round: present your case.\n\n{{casefile}}",
    },
]

OPENING_CONFIG = {
    "stance": {
        "bull": "the BULL analyst. Make the strongest honest case FOR buying",
        "bear": "the BEAR analyst. Make the strongest honest case AGAINST buying (i.e. HOLD or SELL)",
    }
}

DEFAULT_PROMPTS = {
    OPENING_PROMPT: {"messages": OPENING_MESSAGES, "config": OPENING_CONFIG},
}
