"""Orchestration: ticker -> data -> engines -> scorecard.

Screening degrades gracefully: one bad ticker is recorded as a failure and
the batch continues (an evidence engine must never lose a whole run to one
delisted symbol).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from mbe.analysis.business import assess_business
from mbe.analysis.forecast import apply_forecasts, build_forecast, forecast_flags
from mbe.analysis.sector import apply_sector_pillar, compute_sector_scores
from mbe.analysis.stewardship import assess_stewardship
from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.risk import assess_risk
from mbe.analysis.technicals import compute_technicals
from mbe.analysis.valuation import compute_valuation
from mbe.data.provider import DataProvider, ProviderError
from mbe.models.analysis import (
    BusinessProfile,
    FundamentalMetrics,
    RiskAssessment,
    TechnicalState,
    ValuationResult,
)
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.forecast import PriceForecast
from mbe.models.scoring import ScoreCard
from mbe.models.sector import SectorScore
from mbe.models.stewardship import StewardshipProfile
from mbe.models.thesis import Critique, InvestmentThesis
from mbe.scoring.engine import build_scorecard
from mbe.thesis.engine import build_thesis, critique_thesis


class AnalysisBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    info: CompanyInfo
    fin: FinancialHistory
    fund: FundamentalMetrics
    tech: TechnicalState
    prices: PriceHistory | None = None
    val: ValuationResult
    risk: RiskAssessment
    card: ScoreCard
    as_of: date
    business: BusinessProfile | None = None
    stewardship: StewardshipProfile | None = None
    thesis: InvestmentThesis | None = None
    critique: Critique | None = None
    forecast: PriceForecast | None = None


class ScreenResult(BaseModel):
    ranked: list[AnalysisBundle]
    failures: dict[str, str]
    sector_scores: list[SectorScore] = []  # best group first; empty pre-P2.4 runs


def analyze_ticker(ticker: str, provider: DataProvider) -> AnalysisBundle:
    info = provider.get_info(ticker)
    fin = provider.get_financials(ticker)
    prices = provider.get_prices(ticker)

    benchmark = None
    try:
        benchmark = provider.get_prices(provider.benchmark_ticker(ticker))
    except ProviderError:
        pass  # relative strength becomes None; confidence drops accordingly

    fund = compute_fundamentals(fin, info)
    tech = compute_technicals(prices, benchmark)
    price = prices.last_close() or info.price or 0.0
    val = compute_valuation(fin, info, fund, price)
    risk = assess_risk(fin, fund, tech, val, info)
    card = build_scorecard(info, fund, tech, val, risk, fin, price_days=len(prices.df))

    business = assess_business(fin, info, fund)
    stewardship = assess_stewardship(fin, info, fund, business)
    thesis = build_thesis(info, fund, business, val, risk)
    critique = critique_thesis(thesis, fund, business, val, risk)

    bundle = AnalysisBundle(
        info=info, fin=fin, fund=fund, tech=tech, val=val, risk=risk, prices=prices,
        card=card, as_of=date.today(),
        business=business, stewardship=stewardship, thesis=thesis, critique=critique,
    )
    # no universe on this path: the peer term is absent and completeness says so
    bundle.forecast = build_forecast(bundle, peer_pes=[], peer_growths=[])
    bundle.risk.flags.extend(forecast_flags(bundle, bundle.forecast))
    return bundle


def screen(tickers: list[str], provider: DataProvider) -> ScreenResult:
    bundles: list[AnalysisBundle] = []
    failures: dict[str, str] = {}
    for ticker in tickers:
        try:
            bundles.append(analyze_ticker(ticker, provider))
        except ProviderError as exc:
            failures[ticker] = str(exc)
        except Exception as exc:  # engine bug on odd data: record, keep batch alive
            failures[ticker] = f"unexpected: {exc!r}"
    sector_scores: list[SectorScore] = []
    if bundles:
        context = compute_sector_scores(bundles)
        apply_sector_pillar(bundles, context)  # score adjust gated by ablation verdict
        apply_forecasts(bundles, context)  # peer-anchored, overrides the solo pass
        sector_scores = sorted(
            context.groups.values(), key=lambda s: s.score, reverse=True
        )
    bundles.sort(key=lambda b: b.card.multibagger_score, reverse=True)
    return ScreenResult(ranked=bundles, failures=failures, sector_scores=sector_scores)
