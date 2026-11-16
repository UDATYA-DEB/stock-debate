"""Tests for provider fallback and gap detection, using fake providers (no network)."""

from datetime import date, datetime, timezone

from stockdebate.data.gather import find_period_gaps, gather
from stockdebate.data.models import Provenance, Shareholding, Statement


def _prov(name: str) -> Provenance:
    return Provenance(provider=name, fetched_at=datetime.now(timezone.utc))


class EmptyProvider:
    name = "empty"

    def profile(self, symbol):
        return None

    def statement(self, symbol, kind, frequency):
        return None

    def prices(self, symbol):
        return None

    def shareholding(self, symbol):
        return None


class BrokenProvider(EmptyProvider):
    name = "broken"

    def statement(self, symbol, kind, frequency):
        raise RuntimeError("service down")


class StatementsProvider(EmptyProvider):
    name = "statements"

    def statement(self, symbol, kind, frequency):
        if frequency == "annual":
            periods = [date(2026, 3, 31), date(2025, 3, 31), date(2024, 3, 31)]
        else:
            # Missing the 2026-06-30 quarter
            periods = [date(2026, 9, 30), date(2026, 3, 31), date(2025, 12, 31)]
        return Statement(kind=kind, frequency=frequency, periods=periods, rows={}, provenance=_prov(self.name))

    def shareholding(self, symbol):
        return Shareholding(as_of=None, promoter_pct=50.0, provenance=_prov(self.name))


def test_falls_back_past_empty_and_broken_providers():
    data = gather("TEST", [BrokenProvider(), EmptyProvider(), StatementsProvider()])
    annual_income = data.statement("income", "annual")
    assert annual_income is not None
    assert annual_income.provenance.provider == "statements"


def test_records_unavailable_with_reasons():
    data = gather("TEST", [BrokenProvider(), EmptyProvider()])
    prices = next(u for u in data.unavailable if u.dataset == "price history")
    assert prices.tried == ["broken", "empty"]
    income = next(u for u in data.unavailable if u.dataset == "annual income statement")
    assert "service down" in income.reason


def test_missing_pledging_is_reported_not_silently_passed():
    data = gather("TEST", [StatementsProvider()])
    assert any(u.dataset == "promoter pledging" for u in data.unavailable)


def test_quarterly_gap_is_flagged():
    data = gather("TEST", [StatementsProvider()])
    issues = [q for q in data.quality_issues if q.dataset == "quarterly income statement"]
    assert len(issues) == 1
    assert "2026-03-31" in issues[0].issue and "2026-09-30" in issues[0].issue


def test_half_yearly_balance_sheet_is_not_flagged():
    assert find_period_gaps([date(2026, 9, 30), date(2026, 3, 31)], expected_months=6) == []
