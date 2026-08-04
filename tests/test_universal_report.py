from datetime import datetime, timezone

from mbe.models.analysis import FundamentalMetrics, RiskAssessment, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo
from mbe.universal.engine import build_universal_score
from mbe.universal.report import FORBIDDEN_REPORT_KEYS, build_universal_report


def _card():
    info = CompanyInfo(ticker="DIXON.NS", sector="Technology", industry="Electronic Components")
    fund = FundamentalMetrics(revenue_cagr_3y=0.28, profit_cagr_3y=0.32, roe_3y=0.22, net_margin=0.06,
                               roce_3y=0.24, debt_to_equity=0.4, interest_coverage=12.0,
                               net_debt_to_ebitda=0.8, current_ratio=1.6, fcf_margin=0.08,
                               cash_conversion=1.05, accruals_ratio=0.03, completeness=0.95)
    tech = TechnicalState(relative_strength_63d=0.10, cmf20=0.08, trend_state="up", rsi14=58.0,
                           dist_52w_high=-0.08, completeness=0.9)
    val = ValuationResult(margin_of_safety=0.20, peg=1.1, implied_growth=0.18, fcf_yield=0.03, completeness=0.9)
    risk = RiskAssessment(risk_score=20.0)
    return build_universal_score("DIXON.NS", info, fund, tech, val, risk, instrument_id="dixon-id")


def test_report_contains_every_required_section():
    card = _card()
    report = build_universal_report(card, generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
    required_sections = {
        "executive_summary", "company_identity", "universal_score", "factor_breakdown",
        "business_and_financial_quality", "growth", "profitability", "capital_efficiency",
        "balance_sheet_strength", "cash_flow_quality", "valuation", "technical_trend",
        "momentum", "volatility_and_risk", "strengths", "risks", "data_quality_notes",
        "methodology", "source_lineage",
    }
    assert required_sections <= set(report)


def test_report_never_contains_a_forecast_or_recommendation_section():
    card = _card()
    report = build_universal_report(card, generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
    for key in FORBIDDEN_REPORT_KEYS:
        assert key not in report


def test_methodology_section_carries_policy_version():
    card = _card()
    report = build_universal_report(card, generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert report["methodology"]["policy_version"] == "universal-score-v1"


def test_source_lineage_carries_generated_timestamp():
    card = _card()
    when = datetime(2026, 8, 4, 18, 30, tzinfo=timezone.utc)
    report = build_universal_report(card, generated_at=when)
    assert report["source_lineage"]["generated_at"] == when.isoformat()
