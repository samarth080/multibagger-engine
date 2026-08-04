"""Universal Research Score orchestration: ticker -> provider data ->
existing metric engines -> Universal Research Score. Deliberately mirrors
mbe.pipeline.analyze_ticker's shape (same provider calls, same
graceful-benchmark-failure handling) since that function already proved
this exact orchestration works for an arbitrary ticker — this module
reuses it rather than re-deriving it, just swapping
mbe.scoring.engine.build_scorecard for mbe.universal.engine.build_universal_score."""

from __future__ import annotations

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.risk import assess_risk
from mbe.analysis.technicals import compute_technicals
from mbe.analysis.valuation import compute_valuation
from mbe.data.provider import DataProvider, ProviderError
from mbe.universal.domain import UniversalScoreCard
from mbe.universal.engine import build_universal_score


def analyze_universal(
    ticker: str, provider: DataProvider, *, instrument_id: str | None = None,
) -> UniversalScoreCard:
    info = provider.get_info(ticker)
    fin = provider.get_financials(ticker)
    prices = provider.get_prices(ticker)

    benchmark = None
    try:
        benchmark = provider.get_prices(provider.benchmark_ticker(ticker))
    except ProviderError:
        pass

    fund = compute_fundamentals(fin, info)
    tech = compute_technicals(prices, benchmark)
    price = prices.last_close() or info.price or 0.0
    val = compute_valuation(fin, info, fund, price)
    risk = assess_risk(fin, fund, tech, val, info)

    return build_universal_score(ticker, info, fund, tech, val, risk, instrument_id=instrument_id)
