"""Orchestration: ticker -> data -> engines -> scorecard.

Screening degrades gracefully: one bad ticker is recorded as a failure and
the batch continues (an evidence engine must never lose a whole run to one
delisted symbol).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.risk import assess_risk
from mbe.analysis.technicals import compute_technicals
from mbe.analysis.valuation import compute_valuation
from mbe.data.provider import DataProvider, ProviderError
from mbe.models.analysis import (
    FundamentalMetrics,
    RiskAssessment,
    TechnicalState,
    ValuationResult,
)
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.scoring import ScoreCard
from mbe.scoring.engine import build_scorecard


class AnalysisBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    info: CompanyInfo
    fin: FinancialHistory
    fund: FundamentalMetrics
    tech: TechnicalState
    val: ValuationResult
    risk: RiskAssessment
    card: ScoreCard
    as_of: date


class ScreenResult(BaseModel):
    ranked: list[AnalysisBundle]
    failures: dict[str, str]


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

    return AnalysisBundle(
        info=info, fin=fin, fund=fund, tech=tech, val=val, risk=risk,
        card=card, as_of=date.today(),
    )


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
    bundles.sort(key=lambda b: b.card.multibagger_score, reverse=True)
    return ScreenResult(ranked=bundles, failures=failures)
