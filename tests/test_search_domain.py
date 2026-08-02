"""SearchIndexRecord/SearchCandidate schema (Phase 10C Milestone 2 additions:
index_memberships and search-ranking-policy-v3 evidence fields)."""

from mbe.search.domain import SearchCandidate, SearchIndexRecord, SearchResultType


def _minimal_record(**overrides):
    base = dict(
        instrument_id="id-1", display_name="Example Ltd.", symbol="EXAMPLE",
        result_type=SearchResultType.KNOWN, report_url="/company/id-1.html",
    )
    base.update(overrides)
    return SearchIndexRecord(**base)


def test_search_index_record_has_empty_index_memberships_by_default():
    record = _minimal_record()
    assert record.index_memberships == []


def test_search_candidate_carries_v3_evidence_fields():
    record = _minimal_record()
    candidate = SearchCandidate(
        record=record, score=95.0, matched_by="exact_company_name", matched_value="Example Ltd.",
        match_tier="exact_company_name", matched_field="company_name",
        match_reason="Exact company name", match_confidence=0.95,
        ranking_policy_version="2026-08-02.10c.2",
        active_listing=True, primary_listing=True,
        research_available=False, ranking_available=False,
    )
    assert candidate.index_memberships == []
    assert candidate.classification_conflict is False
    assert candidate.ambiguity_warning is None
    assert candidate.requested_exchange_matched is None
