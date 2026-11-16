from datetime import date

import pytest

from stockdebate.policy.eligibility import check_eligibility
from stockdebate.policy.factsheet import build_factsheet
from stockdebate.policy.redflags import check_red_flags
from stockdebate.policy.trend import fy_label, quarter_label, rank_of, summarize
from tests.helpers import CR, company, profile


# ---------- trend ----------

def test_indian_fiscal_labels():
    assert fy_label(date(2026, 3, 31)) == "FY2026"
    assert fy_label(date(2026, 9, 30)) == "FY2027"
    assert quarter_label(date(2026, 6, 30)) == "Q1 FY2027"
    assert quarter_label(date(2026, 9, 30)) == "Q2 FY2027"
    assert quarter_label(date(2026, 12, 31)) == "Q3 FY2027"
    assert quarter_label(date(2027, 3, 31)) == "Q4 FY2027"


def test_trend_detects_cherry_pickable_series():
    # Mostly falling, with one good final year: the latest value is NOT the best.
    points = [(date(2022 + i, 3, 31), v) for i, v in enumerate([100, 90, 80, 70, 85])]
    t = summarize(points)
    assert t.direction == "falling" or t.direction == "mixed"
    assert t.ups == 1 and t.downs == 3
    assert t.latest_rank == 3  # 100 and 90 are higher


def test_trend_rising_and_cagr():
    points = [(date(2022 + i, 3, 31), v) for i, v in enumerate([100, 110, 121, 133.1, 146.41])]
    t = summarize(points)
    assert t.direction == "rising"
    assert t.latest_rank == 1
    assert t.cagr_pct == pytest.approx(10.0, abs=0.1)


def test_rank_of():
    assert rank_of([5, 9, 7], 1) == 1
    assert rank_of([5, 9, 7], 0) == 3


# ---------- fact sheet ----------

GOOD_INCOME = {
    "Total Revenue": [146.41 * CR, 133.1 * CR, 121 * CR, 110 * CR, 100 * CR],
    "Net Income Common Stockholders": [15 * CR, 14 * CR, 12 * CR, 11 * CR, 10 * CR],
    "Operating Income": [22 * CR, 20 * CR, 18 * CR, 16 * CR, 15 * CR],
    "EBIT": [24 * CR, 22 * CR, 20 * CR, 18 * CR, 16 * CR],
    "Interest Expense": [2 * CR, 2 * CR, 2 * CR, 2 * CR, 2 * CR],
    "Cost Of Revenue": [90 * CR, 80 * CR, 75 * CR, 70 * CR, 65 * CR],
}
GOOD_BALANCE = {
    "Total Debt": [20 * CR, 22 * CR, 24 * CR, 26 * CR, 28 * CR],
    "Stockholders Equity": [100 * CR, 90 * CR, 80 * CR, 70 * CR, 60 * CR],
    "Ordinary Shares Number": [1.0e8, 1.0e8, 1.0e8, 1.0e8, 1.0e8],
    "Accounts Receivable": [20 * CR, 18 * CR, 17 * CR, 15 * CR, 14 * CR],
    "Inventory": [25 * CR, 22 * CR, 21 * CR, 19 * CR, 18 * CR],
}
GOOD_CASHFLOW = {
    "Operating Cash Flow": [16 * CR, 15 * CR, 12 * CR, 10 * CR, 9 * CR],
    "Capital Expenditure": [-5 * CR, -5 * CR, -4 * CR, -4 * CR, -3 * CR],
}


def test_factsheet_assigns_ids_and_computes_metrics():
    sheet = build_factsheet(company(GOOD_INCOME, GOOD_BALANCE, GOOD_CASHFLOW))
    assert [f.id for f in sheet.facts] == [f"F{i}" for i in range(1, len(sheet.facts) + 1)]

    rev_cagr = sheet.by_metric("revenue_cagr")
    assert rev_cagr.value == pytest.approx(10.0, abs=0.1)
    assert rev_cagr.period == "FY2022-FY2026"
    assert len(rev_cagr.history) == 5

    de = sheet.by_metric("debt_to_equity")
    assert de.value == pytest.approx(0.2)
    assert de.history[0].period == "FY2022"  # history is oldest first

    fcf = sheet.by_metric("free_cash_flow")
    assert fcf.value == pytest.approx(11.0)  # 16 - 5 crore


def test_missing_line_items_are_reported_unavailable():
    sheet = build_factsheet(company(income={"Total Revenue": GOOD_INCOME["Total Revenue"]}))
    missing = {u.dataset for u in sheet.unavailable}
    assert "debt_to_equity" in missing
    assert "free_cash_flow" in missing


# ---------- red flags ----------

def test_red_flags_clear_for_healthy_company():
    data = company(GOOD_INCOME, GOOD_BALANCE, GOOD_CASHFLOW)
    flags = {f.code: f for f in check_red_flags(data, build_factsheet(data))}
    assert flags["negative_ocf"].status == "clear"
    assert flags["debt"].status == "clear"
    assert flags["dilution"].status == "clear"
    assert flags["working_capital"].status == "clear"
    # Not available in Phase 1: must be unknown, never clear
    assert flags["pledging"].status == "unknown"
    assert flags["auditor"].status == "unknown"


def test_red_flags_trigger():
    balance = dict(GOOD_BALANCE)
    balance["Total Debt"] = [150 * CR] * 5  # D/E 1.5
    balance["Ordinary Shares Number"] = [1.3e8, 1.2e8, 1.1e8, 1.0e8, 1.0e8]  # +30%
    balance["Accounts Receivable"] = [60 * CR, 40 * CR, 25 * CR, 18 * CR, 14 * CR]
    income = dict(GOOD_INCOME)
    income["Interest Expense"] = [12 * CR] * 5  # coverage 2x in FY2026
    cashflow = dict(GOOD_CASHFLOW)
    cashflow["Operating Cash Flow"] = [-3 * CR, 4 * CR, -2 * CR, 10 * CR, 9 * CR]

    data = company(income, balance, cashflow)
    flags = {f.code: f for f in check_red_flags(data, build_factsheet(data))}
    assert flags["debt"].status == "triggered"
    assert flags["dilution"].status == "triggered"
    assert flags["working_capital"].status == "triggered"
    assert flags["negative_ocf"].status == "triggered"
    assert flags["debt"].facts  # flags cite the facts they used


# ---------- eligibility ----------

def test_eligibility():
    data = company(GOOD_INCOME, profile=profile(sector="Industrials", market_cap=10_000 * CR,
                                                 avg_daily_volume_3m=1e6))
    result = check_eligibility(data)
    checks = {c.name: c.status for c in result.checks}
    assert checks["non-financial"] == "pass"
    assert checks["history"] == "pass"
    assert checks["liquidity"] == "unknown"  # no price history in this test
    assert result.eligible is False  # unknown is never a pass


def test_financials_excluded():
    data = company(GOOD_INCOME, profile=profile(sector="Financial Services"))
    checks = {c.name: c.status for c in check_eligibility(data).checks}
    assert checks["non-financial"] == "fail"
