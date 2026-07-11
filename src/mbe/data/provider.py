"""Provider protocol — every data source plugs in behind this interface."""

from __future__ import annotations

from typing import Protocol

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory


class ProviderError(Exception):
    """Raised when a data source cannot deliver usable data for a ticker."""


class DataProvider(Protocol):
    def get_info(self, ticker: str) -> CompanyInfo: ...

    def get_financials(self, ticker: str) -> FinancialHistory: ...

    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory: ...

    def benchmark_ticker(self, ticker: str) -> str:
        """Index used for relative-strength comparisons."""
        ...
