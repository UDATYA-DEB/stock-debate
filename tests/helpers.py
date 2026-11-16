"""Build synthetic CompanyData for tests, without any network calls."""

from datetime import date, datetime, timedelta, timezone

from stockdebate.data.models import (
    CompanyData,
    CompanyProfile,
    PriceHistory,
    PricePoint,
    Provenance,
    Statement,
)

PROV = Provenance(provider="test", fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc))

# Five financial years, newest first: FY2026 ... FY2022
YEARS = [date(y, 3, 31) for y in (2026, 2025, 2024, 2023, 2022)]


def statement(kind: str, rows: dict[str, list[float | None]], years=YEARS) -> Statement:
    """rows: line item -> values aligned with `years` (newest first)."""
    return Statement(
        kind=kind,
        frequency="annual",
        periods=list(years),
        rows={item: {d.isoformat(): v for d, v in zip(years, values)} for item, values in rows.items()},
        provenance=PROV,
    )


def company(income=None, balance=None, cashflow=None, profile=None, prices=None) -> CompanyData:
    data = CompanyData(symbol="TEST", gathered_at=PROV.fetched_at, profile=profile, prices=prices)
    for kind, rows in (("income", income), ("balance", balance), ("cashflow", cashflow)):
        if rows:
            data.statements.append(statement(kind, rows))
    return data


def prices(start: date, end: date, price_fn) -> PriceHistory:
    """Weekday closes from start to end; price_fn(day) -> close."""
    points, day = [], start
    while day <= end:
        if day.weekday() < 5:
            points.append(PricePoint(day=day, close=price_fn(day)))
        day += timedelta(days=1)
    return PriceHistory(points=points, provenance=PROV)


def profile(**kwargs) -> CompanyProfile:
    return CompanyProfile(provenance=PROV, **kwargs)


CR = 1e7  # one crore
