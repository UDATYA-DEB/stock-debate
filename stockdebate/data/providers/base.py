"""The interface every data provider implements.

To add a new source (e.g. Tapetide), write a class with these methods. Each
method returns the data, or None if this provider doesn't have it. Raising an
exception is also fine: the gatherer treats it as "not available from this
provider" and records the error message.
"""

from __future__ import annotations

from typing import Protocol

from stockdebate.data.models import (
    CompanyProfile,
    Frequency,
    PriceHistory,
    Shareholding,
    Statement,
    StatementKind,
)


class DataProvider(Protocol):
    name: str

    def profile(self, symbol: str) -> CompanyProfile | None: ...

    def statement(self, symbol: str, kind: StatementKind, frequency: Frequency) -> Statement | None: ...

    def prices(self, symbol: str) -> PriceHistory | None: ...

    def shareholding(self, symbol: str) -> Shareholding | None: ...
