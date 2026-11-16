"""Opening round: agent runner with a fake model, and the code validator."""

import json

from langchain_core.messages import AIMessage

from stockdebate.debate.agent import extract_json, run_opening
from stockdebate.debate.casefile import build_casefile, render_casefile
from stockdebate.debate.schemas import Claim
from stockdebate.debate.validator import check_claim, numbers_in
from tests.helpers import CR, company, profile
from tests.test_policy import GOOD_BALANCE, GOOD_CASHFLOW, GOOD_INCOME


class FakeLLM:
    """Returns queued replies; records what it was sent."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls = []
        self.bound = {}

    def bind(self, **kwargs):
        self.bound = kwargs
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.replies.pop(0))


def case():
    data = company(GOOD_INCOME, GOOD_BALANCE, GOOD_CASHFLOW,
                   profile=profile(name="Test Ltd", sector="Industrials", market_cap=500 * CR))
    return build_casefile(data)


GOOD_OPENING = json.dumps({
    "thesis": "Steady compounding at a fair price.",
    "case_strength": "moderate",
    "claims": [
        {"type": "fact", "text": "Revenue grew at 10.01% a year over FY2022-FY2026.",
         "citations": ["F3"], "importance": "high"},
        {"type": "forecast", "text": "Revenue should grow 9-12% a year.", "citations": ["F3"],
         "importance": "medium", "forecast_low": 9, "forecast_high": 12, "forecast_unit": "% per year"},
    ],
})


# ---------- agent runner ----------

def test_opening_parses_and_assigns_ids():
    llm = FakeLLM(GOOD_OPENING)
    turn = run_opening("bull", case(), llm, "fake")
    assert turn.error is None and turn.attempts == 1
    assert [c.id for c in turn.claims] == ["B1-1", "B1-2"]
    assert llm.bound["response_format"]["type"] == "json_schema"
    assert "BULL" in llm.calls[0][0].content


def test_opening_retries_once_with_error():
    llm = FakeLLM('{"thesis": "x"}', GOOD_OPENING)
    turn = run_opening("bear", case(), llm, "fake")
    assert turn.attempts == 2 and turn.error is None
    assert [c.id for c in turn.claims] == ["R1-1", "R1-2"]
    assert "not valid" in llm.calls[1][-1].content  # the retry explains the error


def test_opening_gives_up_after_two_failures():
    turn = run_opening("bull", case(), FakeLLM("nonsense", "still nonsense"), "fake")
    assert turn.error and turn.claims == [] and turn.attempts == 2


def test_extract_json_strips_reasoning_and_fences():
    raw = "<think>let me think {not json}</think>\n```json\n{\"a\": 1}\n```"
    assert json.loads(extract_json(raw)) == {"a": 1}


def test_casefile_rendering_shows_history_and_flags():
    text = render_casefile(case())
    assert "F3 Revenue growth (CAGR)" in text
    assert "history: FY2022" in text
    assert "UNKNOWN: Promoter pledging" in text
    assert "NOT AVAILABLE" in text and "- roce" in text  # no Total Assets in this test company


# ---------- validator ----------

def claim(text, citations, type_="fact", **kw):
    return Claim(id="B1-1", author="bull", round=1, type=type_, text=text,
                 citations=citations, importance="high", **kw)


def test_numbers_ignore_years_and_ids():
    found = [raw for raw, _ in numbers_in("In FY2026 (2026) F12 rose to 1,057.5 crore, up 12% (B1-2)")]
    assert found == ["1,057.5", "12"]


def test_supported_when_number_matches_rounding():
    sheet = case().sheet
    revenue = sheet.by_metric("revenue")  # 146.41 crore in FY2026
    assert check_claim(claim(f"Revenue reached 146.4 crore", [revenue.id]), sheet).status == "supported"
    assert check_claim(claim(f"Revenue was 100 crore in FY2022", [revenue.id]), sheet).status == "supported"


def test_misquoted_number():
    sheet = case().sheet
    revenue = sheet.by_metric("revenue")
    chk = check_claim(claim("Revenue reached 180 crore", [revenue.id]), sheet)
    assert chk.status == "misquoted" and "180" in chk.detail


def test_unknown_citation_and_missing_citation():
    sheet = case().sheet
    assert check_claim(claim("Margins are great", ["F99"]), sheet).status == "unsupported"
    assert check_claim(claim("Revenue grew 10%", []), sheet).status == "unsupported"
    interp = claim("The business looks durable", [], type_="interpretation")
    assert check_claim(interp, sheet).status == "supported"  # no numbers, no citation needed


def test_forecast_range_numbers_allowed():
    sheet = case().sheet
    f = claim("Expect 9-12% growth", ["F3"], type_="forecast", forecast_low=9, forecast_high=12,
              forecast_unit="%")
    assert check_claim(f, sheet).status == "supported"
