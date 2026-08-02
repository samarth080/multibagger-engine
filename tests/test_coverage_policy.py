from datetime import datetime, timezone

import pytest

from mbe.coverage.domain import (
    ALL_SECTIONS, COVERAGE_LEVEL_LABELS, COVERAGE_LEVEL_SECTIONS, CoverageAssessment,
    CoverageLevel,
)
from mbe.coverage.policy import RESEARCH_COVERAGE_POLICY_VERSION, assess_coverage


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


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

BASE_RECORD = {
    "instrument_id": "abc-123", "company_id": None, "isin": "INE002A01018",
    "bse_code": None, "legal_name": "Reliance Industries Limited",
    "listing_status": "active", "is_sme": False, "provider_symbol": None,
}


def test_level_0_when_no_quote_provider_mapping():
    result = assess_coverage(
        BASE_RECORD, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 0
    assert result.coverage_label == "Level 0 — Identity Coverage"
    assert result.research_eligible is False
    assert "no_quote_provider_mapping" in result.research_eligibility_reasons
    assert result.research_sections_available == ["identity"]
    assert "quote" in result.research_sections_missing


def test_level_1_when_quote_mapping_but_no_financials_or_model():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 1
    assert result.coverage_label == "Level 1 — Market Coverage"
    assert result.quote_available is True
    assert result.financial_available is False
    assert "no_financial_data" in result.research_eligibility_reasons


def test_level_2_when_financial_data_but_no_model_score():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=True, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 2
    assert result.coverage_label == "Level 2 — Financial Coverage"
    assert result.financial_available is True
    assert result.model_available is False
    assert "not_in_model_universe" in result.research_eligibility_reasons


def test_level_2_requires_quote_mapping_even_with_financial_data():
    """Financial data without a quote mapping doesn't happen today, but the
    policy encodes the real invariant rather than assuming it can't."""
    result = assess_coverage(
        BASE_RECORD, has_financial_data=True, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 0


def test_level_3_requires_both_model_score_and_full_research_payload():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=True, has_model_score=True,
        has_full_research_payload=True, now=NOW,
    )
    assert result.research_coverage_level == 3
    assert result.coverage_label == "Level 3 — Full Research"
    assert result.research_eligible is True
    assert result.research_eligibility_reasons == ["in_smallcap_research_universe"]
    assert result.research_universe == "Nifty Smallcap 250"
    assert "score" in result.research_sections_available
    assert result.research_sections_missing == []


def test_level_3_still_requires_financial_data_and_quote_mapping():
    """A model score and full research payload alone aren't enough — Level 3
    must not claim financial_summary/quote sections are available if the
    underlying capability flags say otherwise."""
    no_financial = assess_coverage(
        {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}, has_financial_data=False,
        has_model_score=True, has_full_research_payload=True, now=NOW,
    )
    assert no_financial.research_coverage_level < 3

    no_quote_mapping = assess_coverage(
        BASE_RECORD, has_financial_data=True,
        has_model_score=True, has_full_research_payload=True, now=NOW,
    )
    assert no_quote_mapping.research_coverage_level < 3


def test_model_score_without_full_payload_does_not_promote_to_level_3():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=True, has_model_score=True,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 2


def test_invalid_identity_is_rejected():
    with pytest.raises(ValueError, match="instrument_id"):
        assess_coverage(
            {**BASE_RECORD, "instrument_id": ""}, has_financial_data=False,
            has_model_score=False, has_full_research_payload=False, now=NOW,
        )


def test_identity_completeness_reflects_isin_and_legal_name():
    complete = assess_coverage(
        BASE_RECORD, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert complete.identity_completeness == "complete"
    partial = assess_coverage(
        {**BASE_RECORD, "isin": None, "legal_name": None}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    assert partial.identity_completeness == "partial"


def test_identity_completeness_edge_cases():
    """Test the and semantics: both isin and legal_name must be present for complete."""
    missing_isin = assess_coverage(
        {**BASE_RECORD, "isin": None}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    assert missing_isin.identity_completeness == "partial"

    missing_legal_name = assess_coverage(
        {**BASE_RECORD, "legal_name": None}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    assert missing_legal_name.identity_completeness == "partial"


def test_inactive_listing_status_is_reflected_in_coverage_status():
    result = assess_coverage(
        {**BASE_RECORD, "listing_status": "delisted"}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_status == "inactive_listing"


def test_policy_version_is_stamped_on_every_assessment():
    result = assess_coverage(
        BASE_RECORD, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.coverage_policy_version == RESEARCH_COVERAGE_POLICY_VERSION == "2026-08-03.11.2a.1"


def test_no_fake_score_fields_below_level_3():
    for level_kwargs in (
        {"has_financial_data": False, "has_model_score": False, "has_full_research_payload": False},
        {"has_financial_data": True, "has_model_score": False, "has_full_research_payload": False},
    ):
        result = assess_coverage({**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}, now=NOW, **level_kwargs)
        assert result.research_coverage_level < 3
        assert "score" not in result.research_sections_available
        assert "rank" not in result.research_sections_available
