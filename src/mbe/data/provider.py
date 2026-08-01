"""Provider protocol — every data source plugs in behind this interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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


class UnsupportedProviderOperation(ProviderError):
    """Raised when an adapter truthfully does not implement a capability."""


@runtime_checkable
class InstrumentMasterProvider(Protocol):
    name: str

    def fetch_instruments(self): ...


@runtime_checkable
class QuoteProvider(Protocol):
    name: str

    def get_quotes(self, mappings): ...


@runtime_checkable
class HistoricalPriceProvider(Protocol):
    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory: ...


@runtime_checkable
class FinancialStatementProvider(Protocol):
    def get_financials(self, ticker: str) -> FinancialHistory: ...

    def list_filings(self, instrument_id: str, *, as_of=None): ...

    def fetch_filing(self, source_filing_id: str): ...


class CorporateActionProvider(Protocol):
    def get_corporate_actions(self, instrument_id: str): ...


class IndexMembershipProvider(Protocol):
    def get_index_memberships(self, index_code: str): ...


class CompanyAnnouncementProvider(Protocol):
    def get_announcements(self, instrument_id: str): ...


class NewsProvider(Protocol):
    def get_news(self, instrument_id: str): ...
