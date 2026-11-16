from datetime import date

import pytest

from stockdebate.policy import valuation as v
from stockdebate.policy.factsheet import build_factsheet
from tests.helpers import CR, company, prices, profile

EPS = {"Diluted EPS": [10.0, 10.0, 10.0, 10.0, 10.0]}  # FY2026 ... FY2022


def test_pe_uses_annual_eps_without_quarterlies():
    data = company(income=EPS, prices=prices(date(2022, 1, 3), date(2026, 11, 13), lambda d: 200.0))
    fact = v.pe_ratio(data)
    assert fact.value == pytest.approx(20.0)
    assert "FY2026 diluted EPS" in fact.basis
    assert [h.period for h in fact.history] == ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]


def test_daily_pe_waits_for_results_to_be_public():
    data = company(income=EPS, prices=prices(date(2022, 1, 3), date(2022, 12, 30), lambda d: 100.0))
    first_day = v.daily_pe(data)[0][0]
    assert first_day >= date(2022, 5, 30)  # FY2022 ended 31 Mar; results ~60 days later


def test_pe_percentile_high_when_price_at_peak():
    # Price rises steadily, EPS flat: today's P/E is the highest in the window.
    start = date(2022, 1, 3)
    data = company(income=EPS, prices=prices(start, date(2026, 11, 13),
                                              lambda d: 100 + (d - start).days * 0.1))
    fact = v.pe_percentile(data)
    assert fact.value > 99


def test_pe_percentile_needs_a_year_of_history():
    data = company(income=EPS, prices=prices(date(2026, 6, 1), date(2026, 11, 13), lambda d: 100.0))
    assert v.pe_percentile(data) is None


def test_reverse_dcf_recovers_known_growth():
    base = 100.0
    target = v.dcf_value(base, 0.15)
    assert v.solve_implied_growth(base, target) == pytest.approx(0.15, abs=1e-6)


def test_reverse_dcf_undefined_for_negative_cash_flow():
    assert v.solve_implied_growth(-10.0, 1000.0) is None


def test_implied_growth_fact():
    cashflow = {
        "Operating Cash Flow": [120 * CR, 100 * CR, 80 * CR, 70 * CR, 60 * CR],
        "Capital Expenditure": [-20 * CR, -20 * CR, -20 * CR, -20 * CR, -20 * CR],
    }
    balance = {
        "Total Debt": [50 * CR] * 5,
        "Cash Cash Equivalents And Short Term Investments": [30 * CR] * 5,
    }
    base = (100 + 80 + 60) / 3 * CR  # avg FCF of the last 3 years: FY2024-FY2026
    ev = v.dcf_value(base, 0.12)
    market_cap = ev - 50 * CR + 30 * CR
    data = company(balance=balance, cashflow=cashflow, profile=profile(market_cap=market_cap))
    fact = v.implied_growth_fcf(data)
    assert fact.value == pytest.approx(12.0, abs=0.01)
    assert "discounted at 12%" in fact.basis

    fy = v.fcf_yield(data)
    assert fy.value == pytest.approx(base / market_cap * 100, abs=0.01)


def test_valuation_facts_join_the_fact_sheet():
    data = company(income=EPS, prices=prices(date(2022, 1, 3), date(2026, 11, 13), lambda d: 200.0))
    sheet = build_factsheet(data)
    assert sheet.by_metric("pe_ratio") is not None
    assert sheet.by_metric("pe_percentile") is not None
    assert any(u.dataset == "implied_growth_fcf" for u in sheet.unavailable)


def test_implied_growth_earnings():
    income = {"Net Income Common Stockholders": [12 * CR, 10 * CR, 8 * CR, 7 * CR, 6 * CR]}
    base = (12 + 10 + 8) / 3 * CR
    data = company(income=income, profile=profile(market_cap=v.dcf_value(base, 0.08)))
    fact = v.implied_growth_earnings(data)
    assert fact.value == pytest.approx(8.0, abs=0.01)
    assert "ignores reinvestment" in fact.basis
