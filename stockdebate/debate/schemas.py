"""What the debate agents must return, and how claims are stored.

Two layers:
- `*Out` models are the JSON schema the LLM fills in. Kept small and flat,
  because 7-8B models follow simple schemas far more reliably.
- `Claim` / `AgentTurn` are the stored versions, with IDs and metadata that
  code adds. The model never chooses claim IDs.

Claim IDs: B<round>-<n> for the bull, R<round>-<n> for the bear (e.g. B1-2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["bull", "bear"]
ClaimType = Literal["fact", "interpretation", "forecast"]
Importance = Literal["high", "medium", "low"]
CaseStrength = Literal["strong", "moderate", "weak"]

ROLE_PREFIX = {"bull": "B", "bear": "R"}


class ClaimOut(BaseModel):
    type: ClaimType = Field(description="fact = a figure from the fact sheet; interpretation = what "
                                        "facts mean; forecast = an expectation about the future")
    text: str = Field(description="One or two sentences. Write every number exactly as it appears "
                                  "in the fact sheet, with its unit.")
    citations: list[str] = Field(default_factory=list,
                                 description="Fact IDs this claim relies on, e.g. [\"F3\", \"F7\"]")
    importance: Importance
    forecast_low: float | None = Field(default=None, description="forecast claims only: low end of the range")
    forecast_high: float | None = Field(default=None, description="forecast claims only: high end of the range")
    forecast_unit: str | None = Field(default=None, description="forecast claims only, e.g. \"% per year\"")


class OpeningOut(BaseModel):
    thesis: str = Field(description="Your overall position in one sentence.")
    claims: list[ClaimOut] = Field(description="3 to 6 claims, most important first.")
    case_strength: CaseStrength = Field(description="Honest assessment of your own case.")


class Claim(ClaimOut):
    id: str
    author: Role
    round: int


class AgentTurn(BaseModel):
    role: Role
    round: int
    model: str
    thesis: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    case_strength: CaseStrength | None = None
    error: str | None = None  # set when the model never produced valid output
    attempts: int = 0
    latency_s: float = 0.0
    prompt_tokens_est: int = 0
    prompt_source: str | None = None  # "langfuse vN" or "built-in"
    raw_outputs: list[str] = Field(default_factory=list)
