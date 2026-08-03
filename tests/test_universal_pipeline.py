import pandas as pd
import pytest

from mbe.data.provider import ProviderError
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.universal.pipeline import analyze_universal


class _StubProvider:
    def __init__(self, *, fail: bool = False):
        self._fail = fail

    def get_info(self, ticker):
        if self._fail:
            raise ProviderError("no data")
        return CompanyInfo(ticker=ticker, sector="Technology", industry="Software", market_cap=5e10)

    def get_financials(self, ticker):
        years = {2023: 100.0, 2024: 130.0, 2025: 170.0}
        return FinancialHistory(data={
            "revenue": years, "net_income": {y: v * 0.1 for y, v in years.items()},
            "cfo": {y: v * 0.12 for y, v in years.items()}, "capex": {y: -v * 0.04 for y, v in years.items()},
            "fcf": {y: v * 0.08 for y, v in years.items()}, "total_equity": {y: v * 0.5 for y, v in years.items()},
            "total_debt": {y: v * 0.1 for y, v in years.items()}, "cash": {y: v * 0.2 for y, v in years.items()},
            "total_assets": {y: v * 0.9 for y, v in years.items()},
            "current_assets": {y: v * 0.4 for y, v in years.items()},
            "current_liabilities": {y: v * 0.2 for y, v in years.items()},
            "interest_expense": {y: v * 0.01 for y, v in years.items()},
            "shares_diluted": {y: 1_000_000.0 for y in years},
        })

    def get_prices(self, ticker, years=3):
        idx = pd.bdate_range("2023-01-01", periods=260)
        closes = [100 + i * 0.1 for i in range(len(idx))]
        df = pd.DataFrame({
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000 for _ in closes],
        }, index=idx)
        return PriceHistory(ticker=ticker, df=df)

    def benchmark_ticker(self, ticker):
        return "^NSEI"


def test_analyze_universal_returns_a_score_for_any_ticker():
    card = analyze_universal("MADEUP.NS", _StubProvider())
    assert card.ticker == "MADEUP.NS"
    assert card.overall_score is not None


def test_analyze_universal_tolerates_missing_benchmark():
    class _NoBenchmark(_StubProvider):
        def benchmark_ticker(self, ticker):
            raise ProviderError("no index data")

    card = analyze_universal("MADEUP.NS", _NoBenchmark())
    assert card.overall_score is not None  # relative strength just becomes unavailable


def test_analyze_universal_propagates_provider_error_for_unknown_ticker():
    with pytest.raises(ProviderError):
        analyze_universal("NOPE.NS", _StubProvider(fail=True))
