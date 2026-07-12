"""Compose a fundamentals-only source (e.g. EDGAR) with a market-data source
(e.g. Yahoo) behind the single DataProvider protocol."""

from __future__ import annotations

from mbe.data.provider import DataProvider
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory


class CompositeProvider:
    def __init__(self, fundamentals, market: DataProvider):
        self.fundamentals = fundamentals
        self.market = market

    def get_info(self, ticker: str) -> CompanyInfo:
        return self.market.get_info(ticker)

    def get_financials(self, ticker: str) -> FinancialHistory:
        return self.fundamentals.get_financials(ticker)

    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory:
        return self.market.get_prices(ticker, years)

    def benchmark_ticker(self, ticker: str) -> str:
        return self.market.benchmark_ticker(ticker)
