from mbe.coverage.domain import (
    ALL_SECTIONS, COVERAGE_LEVEL_LABELS, COVERAGE_LEVEL_SECTIONS, CoverageAssessment,
    CoverageLevel,
)


def test_coverage_level_values_are_ordered_0_to_3():
    assert [int(level) for level in CoverageLevel] == [0, 1, 2, 3]


def test_every_level_has_a_public_label():
    for level in CoverageLevel:
        assert COVERAGE_LEVEL_LABELS[level].startswith(f"Level {int(level)} — ")


def test_section_tables_are_nested_and_cover_all_sections():
    identity = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.IDENTITY])
    market = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.MARKET])
    fundamentals = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.FUNDAMENTALS])
    full = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.FULL_RESEARCH])
    assert identity <= market <= fundamentals <= full
    assert full == set(ALL_SECTIONS)
    assert "score" in full and "score" not in fundamentals


def test_coverage_assessment_round_trips_through_json():
    payload = CoverageAssessment(
        instrument_id="abc-123", company_id=None,
        research_coverage_level=1, coverage_label="Level 1 — Market Coverage",
        coverage_level_version="1.0", research_coverage_status="active",
        research_eligible=False, research_eligibility_reasons=["not_in_model_universe"],
        research_sections_available=["identity", "quote"],
        research_sections_missing=["financial_summary", "score"],
        research_universe=None, ranking_available=False, model_available=False,
        financial_available=False, quote_available=True,
        identity_completeness="complete", source_quality_summary="Identity and live market data.",
        evaluated_at="2026-08-03T00:00:00+00:00", coverage_policy_version="2026-08-03.11.2a.1",
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["research_coverage_level"] == 1
    assert CoverageAssessment.model_validate(dumped) == payload
