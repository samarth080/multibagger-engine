from mbe.universal.domain import (
    CompanyType, ReportState, UniversalFactorScore, UniversalScoreCard,
)


def test_company_type_values_are_stable_strings():
    assert CompanyType.GENERAL_CORPORATE.value == "general_corporate"
    assert CompanyType.BANK.value == "bank"
    assert CompanyType.NBFC.value == "nbfc"
    assert CompanyType.INSURANCE.value == "insurance"
    assert CompanyType.ASSET_MANAGEMENT.value == "asset_management"
    assert CompanyType.OTHER_FINANCIAL.value == "other_financial"
    assert CompanyType.UNKNOWN_LIMITED_DATA.value == "unknown_limited_data"


def test_report_state_values_are_stable_strings():
    assert ReportState.FULL.value == "full_evaluated_report"
    assert ReportState.PARTIAL.value == "partial_evaluated_report"
    assert ReportState.TECHNICAL_ONLY.value == "technical_only_evaluated_report"
    assert ReportState.INSUFFICIENT.value == "insufficient_data_for_scoring"


def test_factor_score_defaults_to_none_score_not_zero():
    factor = UniversalFactorScore(name="Growth", confidence=0.0, eligible_weight=0.0)
    assert factor.score is None  # missing data must never default to 0


def test_scorecard_requires_policy_version():
    card = UniversalScoreCard(
        ticker="RELIANCE.NS", company_type=CompanyType.GENERAL_CORPORATE,
        confidence="Low", confidence_score=0.1, data_coverage_pct=10.0,
        report_state=ReportState.INSUFFICIENT, policy_version="universal-score-v1",
    )
    assert card.overall_score is None
    assert card.factors == []
