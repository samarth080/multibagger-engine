import pytest

from mbe.models.analysis import FundamentalMetrics, RiskAssessment, RiskFlag, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo
from mbe.universal.domain import CompanyType, ReportState
from mbe.universal.engine import build_universal_score


def _full_general_inputs():
    info = CompanyInfo(ticker="DIXON.NS", sector="Technology", industry="Electronic Components")
    fund = FundamentalMetrics(
        revenue_cagr_3y=0.28, profit_cagr_3y=0.32, margin_trend=0.02,
        roe_3y=0.22, net_margin=0.06, roce_3y=0.24,
        debt_to_equity=0.4, interest_coverage=12.0, net_debt_to_ebitda=0.8, current_ratio=1.6,
        fcf_margin=0.08, cash_conversion=1.05, accruals_ratio=0.03,
        completeness=0.95,
    )
    tech = TechnicalState(
        relative_strength_63d=0.10, cmf20=0.08, trend_state="up", rsi14=58.0,
        dist_52w_high=-0.08, completeness=0.9,
    )
    val = ValuationResult(margin_of_safety=0.20, peg=1.1, implied_growth=0.18, fcf_yield=0.03, completeness=0.9)
    risk = RiskAssessment(risk_score=20.0, flags=[RiskFlag(code="LOW_LIQUIDITY", severity=1, detail="thin volume")])
    return info, fund, tech, val, risk


def test_full_data_general_corporate_produces_full_report_state_and_score():
    info, fund, tech, val, risk = _full_general_inputs()
    card = build_universal_score("DIXON.NS", info, fund, tech, val, risk)
    assert card.company_type == CompanyType.GENERAL_CORPORATE
    assert card.report_state == ReportState.FULL
    assert card.overall_score is not None
    assert 0 <= card.overall_score <= 100
    assert card.data_coverage_pct > 60
    assert card.confidence in {"Medium", "High"}
    assert card.policy_version == "universal-score-v1"


def test_factor_subscores_reconcile_to_overall_via_stated_weights():
    info, fund, tech, val, risk = _full_general_inputs()
    card = build_universal_score("DIXON.NS", info, fund, tech, val, risk)
    from mbe.universal.policy import FACTOR_WEIGHTS
    scored = [f for f in card.factors if f.confidence > 0]
    total_weight = sum(FACTOR_WEIGHTS[f.name] for f in scored)
    recombined = sum(FACTOR_WEIGHTS[f.name] * f.score for f in scored) / total_weight
    assert card.overall_score == pytest.approx(round(recombined, 1))


def test_missing_fundamentals_never_scores_zero():
    info = CompanyInfo(ticker="XYZ.NS", sector="Technology", industry="Software")
    fund = FundamentalMetrics(completeness=0.0)  # everything None
    tech = TechnicalState(relative_strength_63d=0.05, cmf20=0.02, trend_state="sideways", rsi14=50.0, completeness=0.6)
    val = ValuationResult(completeness=0.0)
    risk = RiskAssessment(risk_score=0.0)
    card = build_universal_score("XYZ.NS", info, fund, tech, val, risk)
    growth = next(f for f in card.factors if f.name == "Growth")
    assert growth.score is None  # never fabricated as 0
    assert growth.confidence == 0.0
    assert card.report_state == ReportState.TECHNICAL_ONLY


def test_no_data_at_all_is_insufficient():
    info = CompanyInfo(ticker="ZZZ.NS")
    fund = FundamentalMetrics(completeness=0.0)
    tech = TechnicalState(completeness=0.0)
    val = ValuationResult(completeness=0.0)
    risk = RiskAssessment(risk_score=0.0)
    card = build_universal_score("ZZZ.NS", info, fund, tech, val, risk)
    assert card.report_state == ReportState.INSUFFICIENT
    assert card.company_type == CompanyType.UNKNOWN_LIMITED_DATA


def test_bank_excludes_capital_efficiency_and_lowers_coverage_and_confidence():
    info = CompanyInfo(ticker="HDFCBANK.NS", sector="Financial Services", industry="Banks—Regional")
    fund = FundamentalMetrics(
        revenue_cagr_3y=0.15, profit_cagr_3y=0.18, margin_trend=0.01,
        roe_3y=0.16, net_margin=0.22, roce_3y=0.02,  # roce_3y present but must be excluded, not scored
        debt_to_equity=8.0, interest_coverage=1.1, net_debt_to_ebitda=5.0, current_ratio=1.1,
        fcf_margin=None, cash_conversion=None, accruals_ratio=None,
        completeness=0.6,
    )
    tech = TechnicalState(relative_strength_63d=0.05, cmf20=0.01, trend_state="up", rsi14=55.0, dist_52w_high=-0.10, completeness=0.9)
    val = ValuationResult(margin_of_safety=0.10, peg=1.5, implied_growth=0.12, fcf_yield=0.02, completeness=0.8)
    risk = RiskAssessment(risk_score=15.0)
    card = build_universal_score("HDFCBANK.NS", info, fund, tech, val, risk)
    assert card.company_type == CompanyType.BANK
    capital_efficiency = next(f for f in card.factors if f.name == "Capital efficiency")
    assert capital_efficiency.score is None
    assert capital_efficiency.confidence == 0.0
    strength = next(f for f in card.factors if f.name == "Financial strength")
    assert "debt_to_equity" not in [e.metric for e in strength.evidence]
    assert any("not meaningful for" in note for note in card.excluded_factor_notes)
    general_info = CompanyInfo(ticker="GENERAL.NS", sector="Technology", industry="Software")
    general_card = build_universal_score("GENERAL.NS", general_info, fund, tech, val, risk)
    assert card.data_coverage_pct < general_card.data_coverage_pct


def test_instrument_id_is_passed_through():
    info, fund, tech, val, risk = _full_general_inputs()
    card = build_universal_score("DIXON.NS", info, fund, tech, val, risk, instrument_id="abc-123")
    assert card.instrument_id == "abc-123"
