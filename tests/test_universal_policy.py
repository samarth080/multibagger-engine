import pytest

from mbe.universal.domain import CompanyType
from mbe.universal.policy import (
    FACTOR_WEIGHTS, MIN_COVERAGE_FULL, MIN_COVERAGE_PARTIAL,
    UNIVERSAL_SCORE_POLICY_VERSION, factors_for_company_type,
    score_universal_metric,
)


def test_policy_version_is_stamped():
    assert UNIVERSAL_SCORE_POLICY_VERSION == "universal-score-v1"


def test_factor_weights_sum_to_one():
    assert sum(FACTOR_WEIGHTS.values()) == pytest.approx(1.0)


def test_factor_weights_cover_the_required_ten_factors():
    expected = {
        "Growth", "Profitability", "Capital efficiency", "Financial strength",
        "Cash-flow quality", "Valuation", "Momentum", "Technical trend",
        "Volatility and risk", "Data quality",
    }
    assert set(FACTOR_WEIGHTS) == expected


def test_general_corporate_includes_capital_efficiency_metric():
    factors = factors_for_company_type(CompanyType.GENERAL_CORPORATE)
    metrics = [m for m, _, _ in factors["Capital efficiency"]]
    assert "roce_3y" in metrics


def test_bank_excludes_industrial_leverage_and_capital_efficiency_metrics():
    factors = factors_for_company_type(CompanyType.BANK)
    assert factors["Capital efficiency"] == []
    strength_metrics = [m for m, _, _ in factors["Financial strength"]]
    assert "debt_to_equity" not in strength_metrics
    assert "net_debt_to_ebitda" not in strength_metrics
    assert "interest_coverage" not in strength_metrics
    # Growth/Profitability/Valuation/Momentum/Technical trend stay intact
    assert [m for m, _, _ in factors["Growth"]] == [m for m, _, _ in factors_for_company_type(CompanyType.GENERAL_CORPORATE)["Growth"]]


@pytest.mark.parametrize("company_type", [
    CompanyType.NBFC, CompanyType.INSURANCE, CompanyType.ASSET_MANAGEMENT,
    CompanyType.OTHER_FINANCIAL,
])
def test_every_financial_type_excludes_the_same_industrial_metrics(company_type):
    factors = factors_for_company_type(company_type)
    assert factors["Capital efficiency"] == []
    strength_metrics = [m for m, _, _ in factors["Financial strength"]]
    assert strength_metrics == ["current_ratio"]


def test_score_universal_metric_dispatches_shared_and_new_metrics():
    points, _ = score_universal_metric("revenue_cagr_3y", 0.30)
    assert points == 95  # reuses mbe.scoring.benchmarks table verbatim
    points, _ = score_universal_metric("net_margin", 0.20)
    assert points == 90  # uses the new universal-only table
    assert score_universal_metric("trend_state", "strong_up") == (95, "trend template: strong_up")
    assert score_universal_metric("trend_state", "unknown") is None
