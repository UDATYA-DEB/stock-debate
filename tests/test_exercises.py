"""Tests for ROCE and cash conversion in stockdebate/policy/metrics.py.

Run with:
    .venv/bin/pytest tests/test_exercises.py -v
"""

import pytest

from stockdebate.policy import metrics
from tests.helpers import CR, company


def _call(fn, data):
    try:
        return fn(data)
    except NotImplementedError:
        pytest.skip(f"{fn.__name__} not implemented yet")


# ---------- ROCE ----------

def test_roce_basic():
    data = company(
        income={"EBIT": [30 * CR, 20 * CR, 10 * CR, None, None]},
        balance={
            "Total Assets": [200 * CR, 150 * CR, 120 * CR, 100 * CR, 90 * CR],
            "Current Liabilities": [50 * CR, 50 * CR, 20 * CR, 20 * CR, 20 * CR],
        },
    )
    fact = _call(metrics.roce, data)
    assert fact.metric == "roce" and fact.unit == "%"
    assert fact.value == pytest.approx(20.0)  # FY2026: 30 / (200 - 50)
    # Only years with EBIT and capital employed: FY2024..FY2026
    assert [h.period for h in fact.history] == ["FY2024", "FY2025", "FY2026"]
    assert [h.value for h in fact.history] == pytest.approx([10.0, 20.0, 20.0])
    assert set(fact.inputs) == {"EBIT", "Total Assets", "Current Liabilities"}


def test_roce_skips_non_positive_capital_employed():
    data = company(
        income={"EBIT": [30 * CR, 20 * CR, 10 * CR, 10 * CR, 10 * CR]},
        balance={
            "Total Assets": [200 * CR, 100 * CR, 100 * CR, 100 * CR, 100 * CR],
            "Current Liabilities": [50 * CR, 100 * CR, 150 * CR, 50 * CR, 50 * CR],
        },
    )
    fact = _call(metrics.roce, data)
    assert "FY2025" not in [h.period for h in fact.history]  # capital employed = 0
    assert "FY2024" not in [h.period for h in fact.history]  # capital employed < 0


def test_roce_returns_none_without_data():
    assert _call(metrics.roce, company(income={"EBIT": [1 * CR] * 5})) is None


# ---------- cash conversion ----------

def test_cash_conversion_basic():
    data = company(
        income={"Net Income Common Stockholders": [10 * CR, 10 * CR, 8 * CR, 5 * CR, 4 * CR]},
        cashflow={"Operating Cash Flow": [12 * CR, 6 * CR, 8 * CR, 5 * CR, 2 * CR]},
    )
    fact = _call(metrics.cash_conversion, data)
    assert fact.metric == "cash_conversion" and fact.unit == "%"
    assert fact.value == pytest.approx(120.0)  # FY2026: 12 / 10
    assert [h.value for h in fact.history] == pytest.approx([50.0, 100.0, 100.0, 60.0, 120.0])


def test_cash_conversion_skips_loss_years():
    data = company(
        income={"Net Income Common Stockholders": [10 * CR, -5 * CR, 0, 5 * CR, 4 * CR]},
        cashflow={"Operating Cash Flow": [12 * CR, 3 * CR, 2 * CR, 5 * CR, 2 * CR]},
    )
    fact = _call(metrics.cash_conversion, data)
    assert [h.period for h in fact.history] == ["FY2022", "FY2023", "FY2026"]
