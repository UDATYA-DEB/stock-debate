"""Layer 3: valuation and expectations.

- P/E now, and compared with the stock's own history (percentile)
- Free cash flow yield
- Implied growth: the growth rate today's price assumes (reverse DCF)

The reverse DCF turns "is it cheap?" into a number agents can argue about:
"the price assumes 18% growth for 10 years; the company has managed 12%".
Every assumption is written into the fact's `basis`, so agents can challenge it.

Not yet included: valuation relative to sector peers (no peer data source yet).
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from statistics import median

from stockdebate.data.models import CompanyData
from stockdebate.policy import thresholds as t
from stockdebate.policy.factsheet import Fact, HistoryPoint
from stockdebate.policy.dates import consecutive_quarters
from stockdebate.policy.metrics import series, source_of
from stockdebate.policy.trend import fy_label, summarize

LAG = timedelta(days=t.RESULTS_LAG_DAYS)


# ---------- price and EPS helpers ----------

def _closes(data: CompanyData) -> list[tuple[date, float]]:
    return [(p.day, p.close) for p in data.prices.points] if data.prices else []


def _price_on_or_after(closes: list[tuple[date, float]], day: date) -> tuple[date, float] | None:
    days = [d for d, _ in closes]
    i = bisect_right(days, day - timedelta(days=1))
    return closes[i] if i < len(closes) else None


def _annual_eps(data: CompanyData) -> list[tuple[date, float]]:
    return sorted(series(data, "income", "Diluted EPS").items())


def _ttm_eps(data: CompanyData) -> float | None:
    """Sum of the last 4 quarters' diluted EPS, only if they are consecutive."""
    stmt = data.statement("income", "quarterly")
    if stmt is None:
        return None
    latest4 = stmt.periods[:4]
    if len(latest4) < 4 or not consecutive_quarters(latest4):
        return None
    values = [stmt.value("Diluted EPS", p) for p in latest4]
    if any(v is None for v in values):
        return None
    return sum(values)  # type: ignore[arg-type]


def _current_pe(data: CompanyData) -> tuple[float, str, date] | None:
    """(P/E, basis, price date) using TTM EPS when available, else latest annual EPS."""
    closes = _closes(data)
    if not closes:
        return None
    price_day, price = closes[-1]
    ttm = _ttm_eps(data)
    if ttm is not None:
        eps, basis = ttm, "price / diluted EPS of the last 4 quarters"
    else:
        annual = _annual_eps(data)
        if not annual:
            return None
        end, eps = annual[-1]
        basis = f"price / {fy_label(end)} diluted EPS (4 consecutive quarters not available)"
    if eps <= 0:
        return None
    return price / eps, basis, price_day


def daily_pe(data: CompanyData) -> list[tuple[date, float]]:
    """P/E for every trading day, using the annual EPS that was public on that day."""
    closes = _closes(data)
    eps = _annual_eps(data)
    if not closes or not eps:
        return []
    public_from = [end + LAG for end, _ in eps]
    out = []
    for day, close in closes:
        i = bisect_right(public_from, day) - 1
        if i < 0:
            continue  # no annual result public yet in our window
        value = eps[i][1]
        if value > 0:
            out.append((day, close / value))
    return out


# ---------- facts ----------

def pe_ratio(data: CompanyData) -> Fact | None:
    current = _current_pe(data)
    if current is None:
        return None
    pe, basis, price_day = current
    closes = _closes(data)
    history = []
    for end, eps in _annual_eps(data):
        snap = _price_on_or_after(closes, end + LAG)
        if snap and eps > 0:
            history.append((end, snap[1] / eps))
    return Fact(
        metric="pe_ratio",
        label="Price to earnings (P/E)",
        value=round(pe, 2),
        unit="x",
        period=f"as of {price_day}",
        basis=basis + f"; history: P/E about {t.RESULTS_LAG_DAYS} days after each year's end",
        history=[HistoryPoint(period=fy_label(d), end_date=d, value=round(v, 2)) for d, v in history],
        trend=summarize(history) if len(history) >= 2 else None,
        inputs=["Close", "Diluted EPS"],
        source=data.prices.provenance.provider if data.prices else "unknown",
        years_used=len(history),
    )


def pe_percentile(data: CompanyData) -> Fact | None:
    """Where today's P/E sits in its own history: 90 means higher than on 90% of days."""
    daily = daily_pe(data)
    if len(daily) < t.MIN_PE_HISTORY_DAYS:
        return None
    values = [v for _, v in daily]
    current = values[-1]
    pct = 100 * sum(1 for v in values if v < current) / len(values)
    start, end = daily[0][0], daily[-1][0]
    return Fact(
        metric="pe_percentile",
        label="P/E vs own history (percentile)",
        value=round(pct, 1),
        unit="percentile",
        period=f"{start} to {end}",
        basis=(f"share of trading days with a lower P/E, using annual EPS public on each day; "
               f"current {current:.1f}x, min {min(values):.1f}x, "
               f"median {median(values):.1f}x, max {max(values):.1f}x"),
        inputs=["Close", "Diluted EPS"],
        source=data.prices.provenance.provider if data.prices else "unknown",
        years_used=round((end - start).days / 365.25),
    )


def _avg_fcf(data: CompanyData) -> tuple[float, list[tuple[date, float]]] | None:
    ocf = series(data, "cashflow", "Operating Cash Flow")
    capex = series(data, "cashflow", "Capital Expenditure")
    fcf = sorted((p, ocf[p] - abs(capex[p])) for p in ocf if p in capex)
    recent = fcf[-t.FCF_AVERAGE_YEARS:]
    if len(recent) < t.FCF_AVERAGE_YEARS:
        return None
    return sum(v for _, v in recent) / len(recent), recent


def fcf_yield(data: CompanyData) -> Fact | None:
    avg = _avg_fcf(data)
    cap = data.profile.market_cap if data.profile else None
    if avg is None or not cap:
        return None
    base, recent = avg
    return Fact(
        metric="fcf_yield",
        label="Free cash flow yield",
        value=round(base / cap * 100, 2),
        unit="%",
        period=f"{fy_label(recent[0][0])}-{fy_label(recent[-1][0])} average vs current market cap",
        basis=f"average free cash flow of {len(recent)} years / market cap",
        history=[HistoryPoint(period=fy_label(d), end_date=d, value=round(v / t.CRORE, 2))
                 for d, v in recent],
        inputs=["Operating Cash Flow", "Capital Expenditure", "Market Cap"],
        source=source_of(data, "cashflow"),
        years_used=len(recent),
    )


def dcf_value(base: float, growth: float, *, rate: float = t.DCF_DISCOUNT_RATE,
              terminal: float = t.DCF_TERMINAL_GROWTH, years: int = t.DCF_YEARS) -> float:
    """Present value of cash flows growing at `growth` for `years`, then at `terminal`."""
    value, cash = 0.0, base
    for year in range(1, years + 1):
        cash *= 1 + growth
        value += cash / (1 + rate) ** year
    terminal_value = cash * (1 + terminal) / (rate - terminal)
    return value + terminal_value / (1 + rate) ** years


def solve_implied_growth(base: float, target: float, low: float = -0.5, high: float = 1.0) -> float | None:
    """Growth rate at which dcf_value(base, g) equals target (bisection)."""
    if base <= 0 or not (dcf_value(base, low) <= target <= dcf_value(base, high)):
        return None
    for _ in range(100):
        mid = (low + high) / 2
        if dcf_value(base, mid) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def implied_growth_fcf(data: CompanyData) -> Fact | None:
    """Reverse DCF on free cash flow against enterprise value.

    Strict view: heavy investment (capex, inventory) lowers free cash flow and
    so raises the growth the price seems to need. See implied_growth_earnings
    for the lenient view.

    Indian cash flow statements usually report interest paid under financing,
    so operating cash flow minus capex approximates cash flow to the whole firm;
    that's why it's compared with enterprise value, not market cap.
    """
    avg = _avg_fcf(data)
    cap = data.profile.market_cap if data.profile else None
    debt = series(data, "balance", "Total Debt")
    cash = series(data, "balance", "Cash Cash Equivalents And Short Term Investments")
    if avg is None or not cap or not debt or not cash:
        return None
    base, recent = avg
    latest_bs = max(debt)
    if latest_bs not in cash:
        return None
    ev = cap + debt[latest_bs] - cash[latest_bs]
    growth = solve_implied_growth(base, ev)
    if growth is None:
        return None
    return Fact(
        metric="implied_growth_fcf",
        label="Implied growth, free cash flow basis (reverse DCF)",
        value=round(growth * 100, 2),
        unit="% per year",
        period=f"next {t.DCF_YEARS} years, priced as of {data.gathered_at.date()}",
        basis=(f"free cash flow (avg {fy_label(recent[0][0])}-{fy_label(recent[-1][0])}: "
               f"INR {base / t.CRORE:,.0f} crore) growing at this rate for {t.DCF_YEARS} years, "
               f"then {t.DCF_TERMINAL_GROWTH:.0%}, discounted at {t.DCF_DISCOUNT_RATE:.0%}, "
               f"equals enterprise value INR {ev / t.CRORE:,.0f} crore "
               f"(market cap + debt - cash, {fy_label(latest_bs)} balance sheet)"),
        inputs=["Operating Cash Flow", "Capital Expenditure", "Market Cap", "Total Debt",
                "Cash Cash Equivalents And Short Term Investments"],
        source=source_of(data, "cashflow"),
        years_used=len(recent),
    )


def implied_growth_earnings(data: CompanyData) -> Fact | None:
    """Reverse DCF on net profit against market cap.

    Lenient view: treats all profit as if it were cash available to shareholders,
    ignoring the investment needed to grow. Read it together with the FCF version;
    the truth for a reinvesting company is usually between the two.
    """
    profit = sorted(series(data, "income", "Net Income Common Stockholders").items())
    recent = profit[-t.FCF_AVERAGE_YEARS:]
    cap = data.profile.market_cap if data.profile else None
    if len(recent) < t.FCF_AVERAGE_YEARS or not cap:
        return None
    base = sum(v for _, v in recent) / len(recent)
    growth = solve_implied_growth(base, cap)
    if growth is None:
        return None
    return Fact(
        metric="implied_growth_earnings",
        label="Implied growth, earnings basis (reverse DCF)",
        value=round(growth * 100, 2),
        unit="% per year",
        period=f"next {t.DCF_YEARS} years, priced as of {data.gathered_at.date()}",
        basis=(f"net profit (avg {fy_label(recent[0][0])}-{fy_label(recent[-1][0])}: "
               f"INR {base / t.CRORE:,.0f} crore) growing at this rate for {t.DCF_YEARS} years, "
               f"then {t.DCF_TERMINAL_GROWTH:.0%}, discounted at {t.DCF_DISCOUNT_RATE:.0%}, "
               f"equals market cap INR {cap / t.CRORE:,.0f} crore; ignores reinvestment needs"),
        history=[HistoryPoint(period=fy_label(d), end_date=d, value=round(v / t.CRORE, 2))
                 for d, v in recent],
        inputs=["Net Income Common Stockholders", "Market Cap"],
        source=source_of(data, "income"),
        years_used=len(recent),
    )


VALUATION_METRICS = [pe_ratio, pe_percentile, fcf_yield, implied_growth_fcf, implied_growth_earnings]
