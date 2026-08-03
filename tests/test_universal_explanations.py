from mbe.models.scoring import Evidence
from mbe.universal.domain import CompanyType, ReportState, UniversalFactorScore, UniversalScoreCard
from mbe.universal.explanations import build_strengths_and_risks


def _card_with_factor(name: str, score: float, confidence: float = 0.9) -> UniversalScoreCard:
    factor = UniversalFactorScore(
        name=name, score=score, confidence=confidence, eligible_weight=confidence,
        evidence=[Evidence(metric="x", value=score, benchmark="b", points=score, weight=1.0, rationale="r")],
    )
    other = UniversalFactorScore(name="Data quality", score=80.0, confidence=1.0, eligible_weight=1.0)
    return UniversalScoreCard(
        ticker="T.NS", company_type=CompanyType.GENERAL_CORPORATE, overall_score=score,
        confidence="High", confidence_score=0.8, data_coverage_pct=80.0,
        report_state=ReportState.FULL, factors=[factor, other], policy_version="universal-score-v1",
    )


def test_high_scoring_factor_becomes_a_strength():
    card = _card_with_factor("Growth", 85.0)
    strengths, risks = build_strengths_and_risks(card)
    assert any("Growth" in s for s in strengths)


def test_low_scoring_factor_becomes_a_risk():
    card = _card_with_factor("Financial strength", 20.0)
    strengths, risks = build_strengths_and_risks(card)
    assert any("Financial strength" in r for r in risks)


def test_low_confidence_factor_is_never_used_as_evidence():
    card = _card_with_factor("Growth", 90.0, confidence=0.1)
    strengths, risks = build_strengths_and_risks(card)
    assert not any("Growth" in s for s in strengths)


def test_mid_scoring_factor_is_neither_strength_nor_risk():
    card = _card_with_factor("Momentum", 55.0)
    strengths, risks = build_strengths_and_risks(card)
    assert not any("Momentum" in s for s in strengths)
    assert not any("Momentum" in r for r in risks)
