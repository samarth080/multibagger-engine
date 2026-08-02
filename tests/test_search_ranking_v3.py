"""Search ranking policy version 3 (Phase 10C Milestone 2): late tie-break
dimensions layered on the unchanged version-2 primary match tiers, plus the
evidence fields every candidate now carries."""

from mbe.search.domain import ExchangeListing, SearchIndexRecord, SearchResultType
from mbe.search.ranking import (
    SEARCH_RANKING_POLICY_VERSION,
    classification_quality_rank,
    index_membership_rank,
    matched_field_for,
    match_reason,
    rank_search_candidates,
)


def _record(
    instrument_id, display_name, symbol, *, isin=None, bse_code=None,
    listing_status="active", is_primary=True, exchange="NSE",
    result_type=SearchResultType.KNOWN, research_available=False,
    rank=None, score=None, is_sme=None, index_memberships=None,
    industry=None, classification_review_status=None, classification_conflict=False,
):
    return SearchIndexRecord(
        instrument_id=instrument_id, display_name=display_name, legal_name=display_name,
        symbol=symbol, exchange=exchange, primary_exchange=exchange, isin=isin,
        bse_code=bse_code, listing_status=listing_status, is_sme=is_sme,
        listings=[ExchangeListing(
            exchange=exchange, symbol=symbol, bse_code=bse_code, isin=isin,
            listing_status=listing_status, is_primary=is_primary,
        )],
        index_memberships=index_memberships or [], industry=industry,
        classification_review_status=classification_review_status,
        classification_conflict=classification_conflict,
        result_type=result_type, research_available=research_available,
        rank=rank, multibagger_score=score,
        report_url=f"/company/{instrument_id}.html",
    )


def test_policy_version_is_bumped_for_milestone_2():
    assert SEARCH_RANKING_POLICY_VERSION == "2026-08-02.10c.2"


def test_index_membership_tiebreak_prefers_broad_index_member_at_equal_score():
    member = _record(
        "id-member", "Tie Break Gamma Ltd.", "TBG", index_memberships=["Nifty 50"],
    )
    non_member = _record("id-nonmember", "Tie Break Delta Ltd.", "TBD")
    results = rank_search_candidates("Tie Break", [non_member, member])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-member"


def test_index_membership_is_a_noop_for_todays_data_no_company_has_one():
    a = _record("id-a", "Tie Break Epsilon Ltd.", "TBE")
    b = _record("id-b", "Tie Break Zeta Ltd.", "TBZ")
    results = rank_search_candidates("Tie Break", [b, a])
    # Neither carries a verified index membership — order falls through to
    # the next dimension (alphabetical), proving this tie-break dimension
    # cannot fabricate a difference where none of today's data supports one.
    assert [r.record.instrument_id for r in results] == ["id-a", "id-b"]


def test_ranking_availability_is_a_late_tiebreak_distinct_from_research_availability():
    ranked = _record(
        "id-ranked", "Tie Break Eta Ltd.", "TBH",
        research_available=True, rank=3, score=80.0,
    )
    researched_only = _record(
        "id-researched-only", "Tie Break Theta Ltd.", "TBI", research_available=True,
    )
    results = rank_search_candidates("Tie Break", [researched_only, ranked])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-ranked"


def test_classification_quality_tiebreak_prefers_clean_industry_tagged_record():
    clean = _record(
        "id-clean", "Tie Break Iota Ltd.", "TBJ",
        industry="Software", classification_review_status="accepted",
    )
    conflicted = _record(
        "id-conflicted", "Tie Break Kappa Ltd.", "TBK",
        industry="Software", classification_review_status="conflict", classification_conflict=True,
    )
    results = rank_search_candidates("Tie Break", [conflicted, clean])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-clean"


def test_classification_conflict_never_suppresses_a_better_exact_match():
    exact_conflicted = _record(
        "id-exact-conflicted", "Precise Conflict Limited", "PCLT",
        industry="Software", classification_review_status="conflict", classification_conflict=True,
    )
    prefix_clean = _record(
        "id-prefix-clean", "Precise Conflict Extended Group Limited", "PCEG",
        industry="Software", classification_review_status="accepted",
    )
    results = rank_search_candidates("Precise Conflict Limited", [prefix_clean, exact_conflicted])
    assert results[0].record.instrument_id == "id-exact-conflicted"
    assert results[0].matched_by == "exact_company_name"


def test_missing_sector_never_penalizes_because_sector_coverage_is_zero_today():
    # Neither record sets sector at all (matches today's 0/2,947 coverage);
    # classification_quality_rank must not distinguish on sector.
    a = _record("id-a2", "Tie Break Lambda Ltd.", "TBL", industry="Software", classification_review_status="accepted")
    b = _record("id-b2", "Tie Break Mu Ltd.", "TBM", industry="Software", classification_review_status="accepted")
    assert classification_quality_rank(
        industry=a.industry, review_status=a.classification_review_status, conflict=a.classification_conflict,
    ) == classification_quality_rank(
        industry=b.industry, review_status=b.classification_review_status, conflict=b.classification_conflict,
    )


def test_evidence_fields_are_populated_on_every_candidate():
    record = _record(
        "id-evidence", "Evidence Fields Ltd.", "EVID",
        research_available=True, rank=1, score=90.0, index_memberships=["Nifty 50"],
        industry="Software", classification_review_status="accepted",
    )
    results = rank_search_candidates("EVID", [record])
    result = results[0]
    assert result.match_tier == "exact_nse_symbol"
    assert result.matched_field == "symbol"
    assert result.match_reason == "Exact company symbol"
    assert result.match_confidence == 1.0
    assert result.ranking_policy_version == SEARCH_RANKING_POLICY_VERSION
    assert result.active_listing is True
    assert result.primary_listing is True
    assert result.research_available is True
    assert result.ranking_available is True
    assert result.classification_review_status == "accepted"
    assert result.classification_conflict is False
    assert "Nifty 50" in result.prominence_signals
    assert "Full research available" in result.prominence_signals
    assert "Ranked" in result.prominence_signals


def test_ambiguity_warning_set_for_low_confidence_fuzzy_first_result():
    decoy_only = _record("id-fuzzy-only", "Relaince Indsutries Ltd.", "RELDX")
    results = rank_search_candidates("Reliance Industries Limited", [decoy_only])
    assert results[0].score < 82
    assert results[0].ambiguity_warning is not None


def test_ambiguity_warning_set_for_short_query_tie():
    # Two identical-remainder-length prefix matches for a 3-character query
    # guarantee a tied top score.
    a = _record("id-tied-a", "Abc One Ltd.", "ABCONE")
    b = _record("id-tied-b", "Abc Two Ltd.", "ABCTWO")
    results = rank_search_candidates("Abc", [b, a])
    assert results[0].score == results[1].score
    assert results[0].ambiguity_warning is not None


def test_matched_field_for_and_match_reason_cover_every_primary_tier():
    for matched_by, expected_field in [
        ("exact_nse_symbol", "symbol"), ("exact_bse_code", "bse_code"),
        ("exact_isin", "isin"), ("exact_company_name", "company_name"),
        ("company_name_prefix", "company_name"), ("full_phrase_match", "company_name"),
        ("word_match", "company_name"), ("fuzzy_company_name", "company_name"),
    ]:
        assert matched_field_for(matched_by) == expected_field
        assert match_reason(matched_by)
    assert matched_field_for("exact_former_name") == "alias"
    assert match_reason("exact_former_name") == "Matched former company name"
    assert matched_field_for("exact_alias") == "alias"
    assert match_reason("exact_alias") == "Matched alias"


def test_index_membership_rank_orders_by_documented_precedence():
    assert index_membership_rank(["Nifty 50"]) < index_membership_rank(["Nifty 500"])
    assert index_membership_rank([]) > index_membership_rank(["Nifty 500"])
