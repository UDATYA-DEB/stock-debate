"""LangChain clients for the debaters (any OpenAI-compatible endpoint)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from stockdebate.llm.health import _openai_base

# Pinned generation settings (DECISIONS 6.12): same on both runtimes.
DEBATER_TEMPERATURE = 0.4
DEBATER_SEED = 7
DEBATER_MAX_TOKENS = 2048
DEBATER_TIMEOUT_S = 300


def make_debater(url: str, model: str, token: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=_openai_base(url),
        api_key=token or "not-needed",  # sent as "Authorization: Bearer <token>"
        model=model,
        temperature=DEBATER_TEMPERATURE,
        seed=DEBATER_SEED,
        max_tokens=DEBATER_MAX_TOKENS,
        timeout=DEBATER_TIMEOUT_S,
        max_retries=2,
    )
