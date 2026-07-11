"""Combines pillars into the Investment Score, Multibagger Score and
Confidence. Weights are explicit constants; hard gates keep the engine from
recommending hype with broken economics (brief: no pump-and-dumps).
"""

from __future__ import annotations

from mbe.models.analysis import (
    FundamentalMetrics,
    RiskAssessment,
    TechnicalState,
    ValuationResult,
)
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.scoring import Evidence, PillarScore, ScoreCard
from mbe.scoring.benchmarks import score_reinvestment, score_size_runway
from mbe.scoring.pillars import (
    growth_pillar,
    momentum_pillar,
    quality_pillar,
    strength_pillar,
    valuation_pillar,
)

INVESTMENT_WEIGHTS = {
    "Quality": 0.28,
    "Financial Strength": 0.18,
    "Growth": 0.18,
    "Valuation": 0.22,
    "Momentum": 0.14,
}
# haircut: at risk_score 100 the investment score loses 25%
RISK_HAIRCUT = 0.25

MULTIBAGGER_WEIGHTS = {
    "Growth": 0.26,
    "Quality": 0.24,
    "Size Runway": 0.16,
    "Valuation": 0.14,
    "Momentum": 0.10,
    "Reinvestment": 0.10,
}
HARD_GATE_CAP = 35.0


def _size_pillar(info: CompanyInfo) -> PillarScore:
    if info.market_cap is None:
        return PillarScore(name="Size Runway", score=0.0, confidence=0.0, evidence=[])
    is_india = info.ticker.endswith((".NS", ".BO"))
    points, benchmark = score_size_runway(info.market_cap, is_india)
    return PillarScore(
        name="Size Runway",
        score=points,
        confidence=1.0,
        evidence=[
            Evidence(
                metric="market_cap",
                value=info.market_cap,
                benchmark=benchmark,
                points=points,
                weight=1.0,
                rationale="Multibaggers are far more common below institutional radar size",
            )
        ],
    )


def _reinvestment_pillar(fund: FundamentalMetrics) -> PillarScore:
    if fund.reinvestment_rate is None:
        return PillarScore(name="Reinvestment", score=0.0, confidence=0.0, evidence=[])
    points, benchmark = score_reinvestment(fund.reinvestment_rate)
    return PillarScore(
        name="Reinvestment",
        score=points,
        confidence=1.0,
        evidence=[
            Evidence(
                metric="reinvestment_rate",
                value=round(fund.reinvestment_rate, 4),
                benchmark=benchmark,
                points=points,
                weight=1.0,
                rationale="Compounding needs somewhere productive to redeploy cash",
            )
        ],
    )


def _hard_gates(fund: FundamentalMetrics, fin: FinancialHistory) -> list[str]:
    failures = []
    if fund.accruals_ratio is not None and fund.accruals_ratio > 0.10:
        failures.append(
            f"Accruals ratio {fund.accruals_ratio:.2f} > 0.10 — earnings quality gate"
        )
    if fund.interest_coverage is not None and fund.interest_coverage < 1.5:
        failures.append(
            f"Interest coverage {fund.interest_coverage:.1f}x < 1.5x — solvency gate"
        )
    if fund.share_count_cagr_3y is not None and fund.share_count_cagr_3y > 0.08:
        failures.append(
            f"Dilution {fund.share_count_cagr_3y:.1%}/yr > 8% — shareholder erosion gate"
        )
    fcf3 = [v for _, v in fin.series("fcf")[-3:]]
    ni3 = [v for _, v in fin.series("net_income")[-3:]]
    if fcf3 and ni3 and sum(fcf3) < 0 and sum(ni3) < 0:
        failures.append("Both 3y cumulative FCF and net income negative — viability gate")
    return failures


def _verdict(investment: float, multibagger: float, confidence: float) -> str:
    if investment >= 75:
        base = "Strong candidate — deep-dive diligence warranted"
    elif investment >= 60:
        base = "Promising — verify the flagged data gaps before acting"
    elif investment >= 45:
        base = "Watchlist — needs a catalyst or better price"
    else:
        base = "Avoid — insufficient evidence of edge"
    if multibagger >= 75 and investment >= 60:
        base += "; elevated multibagger characteristics"
    if confidence < 0.4:
        base = "Low confidence (data gaps): " + base
    return base


def build_scorecard(
    info: CompanyInfo,
    fund: FundamentalMetrics,
    tech: TechnicalState,
    val: ValuationResult,
    risk: RiskAssessment,
    fin: FinancialHistory,
    price_days: int,
) -> ScoreCard:
    pillars = {
        "Quality": quality_pillar(fund),
        "Growth": growth_pillar(fund),
        "Financial Strength": strength_pillar(fund),
        "Valuation": valuation_pillar(val, fund),
        "Momentum": momentum_pillar(tech),
        "Size Runway": _size_pillar(info),
        "Reinvestment": _reinvestment_pillar(fund),
    }

    def combine(weights: dict[str, float]) -> float:
        total_weight = sum(
            w for name, w in weights.items() if pillars[name].confidence > 0
        )
        if total_weight == 0:
            return 0.0
        return sum(
            w * pillars[name].score
            for name, w in weights.items()
            if pillars[name].confidence > 0
        ) / total_weight

    investment_raw = combine(INVESTMENT_WEIGHTS)
    investment = investment_raw * (1 - RISK_HAIRCUT * risk.risk_score / 100)

    multibagger = combine(MULTIBAGGER_WEIGHTS)
    gate_failures = _hard_gates(fund, fin)
    if gate_failures:
        multibagger = min(multibagger, HARD_GATE_CAP)

    years = len(fin.years())
    confidence = (
        0.5 * (fund.completeness + tech.completeness + val.completeness) / 3
        + 0.3 * min(years / 5, 1.0)
        + 0.2 * min(price_days / 756, 1.0)  # 3 trading years
    )

    return ScoreCard(
        ticker=info.ticker,
        investment_score=round(investment, 1),
        multibagger_score=round(multibagger, 1),
        confidence=round(confidence, 3),
        pillars=list(pillars.values()),
        hard_gate_failures=gate_failures,
        verdict=_verdict(investment, multibagger, confidence),
    )
