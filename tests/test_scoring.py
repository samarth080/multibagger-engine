import pytest

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.models.analysis import (
    FundamentalMetrics,
    RiskAssessment,
    TechnicalState,
    ValuationResult,
)
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.scoring.benchmarks import score_metric, score_rsi, score_size_runway
from mbe.scoring.engine import build_scorecard
from mbe.scoring.pillars import quality_pillar

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]


def _compounder_fin() -> FinancialHistory:
    return FinancialHistory(
        data={
            field: dict(zip(YEARS, values))
            for field, values in {
                "revenue": [100, 115, 132, 152, 175, 200],
                "net_income": [10, 12, 15, 18, 22, 26],
                "operating_income": [15, 17, 20, 24, 28, 33],
                "ebitda": [20, 23, 27, 32, 37, 43],
                "gross_profit": [40, 46, 53, 61, 70, 80],
                "interest_expense": [4, 4, 4, 4, 4, 4],
                "total_assets": [300, 340, 385, 435, 490, 550],
                "total_equity": [60, 70, 82, 96, 112, 130],
                "total_debt": [40, 40, 40, 40, 40, 40],
                "cash": [10, 12, 14, 16, 18, 20],
                "current_assets": [50, 55, 60, 65, 70, 75],
                "current_liabilities": [25, 27, 29, 31, 33, 35],
                "cfo": [12, 14, 18, 22, 26, 30],
                "capex": [5, 6, 7, 8, 9, 10],
                "fcf": [7, 8, 11, 14, 17, 20],
                "shares_diluted": [100, 100, 100, 100, 100, 100],
            }.items()
        }
    )


def test_score_metric_thresholds():
    points, benchmark = score_metric("roce_3y", 0.24)
    assert points == 75
    assert "0.20" in benchmark or "20" in benchmark
    points, _ = score_metric("debt_to_equity", 0.05)
    assert points == 95  # lower is better
    points, _ = score_metric("margin_of_safety", -0.5)
    assert points == 5


def test_score_metric_unknown_raises():
    with pytest.raises(KeyError):
        score_metric("not_a_metric", 1.0)


def test_score_rsi_zones():
    assert score_rsi(55)[0] == 75  # healthy
    assert score_rsi(80)[0] == 30  # overbought
    assert score_rsi(25)[0] == 25  # oversold


def test_score_size_runway_india():
    assert score_size_runway(3e10, is_india=True)[0] == 95  # < Rs 5,000 cr
    assert score_size_runway(6e12, is_india=True)[0] == 15  # mega cap


def test_quality_pillar_renormalizes_on_missing_metrics():
    fund = FundamentalMetrics(roce_3y=0.24)  # everything else missing
    pillar = quality_pillar(fund)
    assert pillar.score == pytest.approx(75.0)
    assert pillar.confidence == pytest.approx(0.30)  # only .30 of weight present
    assert len(pillar.evidence) == 1
    assert pillar.evidence[0].metric == "roce_3y"


def _full_bundle():
    fin = _compounder_fin()
    info = CompanyInfo(ticker="COMP.NS", market_cap=3e10, insider_pct=0.6)
    fund = compute_fundamentals(fin, info)
    tech = TechnicalState(
        trend_state="strong_up",
        rsi14=60.0,
        relative_strength_63d=0.08,
        dist_52w_high=-0.05,
        cmf20=0.10,
        completeness=0.9,
    )
    val = ValuationResult(
        margin_of_safety=0.20,
        peg=1.0,
        implied_growth=0.10,
        fcf_yield=0.05,
        completeness=0.9,
    )
    risk = RiskAssessment(flags=[], risk_score=0.0, permanent_loss_bucket="low")
    return fin, info, fund, tech, val, risk


def test_golden_compounder_scorecard():
    fin, info, fund, tech, val, risk = _full_bundle()
    card = build_scorecard(
        info, fund, tech, val, risk, fin, price_days=756
    )
    assert card.investment_score >= 70
    assert card.multibagger_score >= 70
    assert card.hard_gate_failures == []
    assert card.confidence > 0.8
    # every pillar must carry evidence
    for pillar in card.pillars:
        assert pillar.evidence, f"pillar {pillar.name} has no evidence"


def test_hard_gate_caps_multibagger_score():
    fin, info, fund, tech, val, risk = _full_bundle()
    bad_fund = fund.model_copy(update={"accruals_ratio": 0.15})
    card = build_scorecard(info, bad_fund, tech, val, risk, fin, price_days=756)
    assert card.multibagger_score <= 35
    assert any("accruals" in f.lower() for f in card.hard_gate_failures)


def test_risk_haircuts_investment_score():
    fin, info, fund, tech, val, _ = _full_bundle()
    risky = RiskAssessment(flags=[], risk_score=100.0, permanent_loss_bucket="high")
    clean = RiskAssessment(flags=[], risk_score=0.0, permanent_loss_bucket="low")
    card_risky = build_scorecard(info, fund, tech, val, risky, fin, price_days=756)
    card_clean = build_scorecard(info, fund, tech, val, clean, fin, price_days=756)
    assert card_risky.investment_score < card_clean.investment_score
