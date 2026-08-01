"""Search ranking policy version 2 (Phase 10B).

Extends the Phase 10A tiering with BSE-code/ISIN-first-class matching,
exchange-aware query parsing (NSE:/BSE: hints), a full-phrase-match tier,
and documented prominence tie-breakers (active > inactive, primary listing,
research availability strictly as a LATE tie-break that never beats an
exact identity match).
"""

from mbe.search.domain import ExchangeListing, SearchIndexRecord, SearchResultType
from mbe.search.ranking import (
    SEARCH_RANKING_POLICY_VERSION,
    parse_exchange_hint,
    rank_search_candidates,
)


def _record(
    instrument_id, display_name, symbol, *, isin=None, bse_code=None,
    listing_status="active", is_primary=True, exchange="NSE",
    result_type=SearchResultType.KNOWN, research_available=False,
    rank=None, score=None, listings=None,
):
    return SearchIndexRecord(
        instrument_id=instrument_id, display_name=display_name, legal_name=display_name,
        symbol=symbol, exchange=exchange, primary_exchange=exchange, isin=isin,
        bse_code=bse_code, listing_status=listing_status,
        listings=listings or [ExchangeListing(
            exchange=exchange, symbol=symbol, bse_code=bse_code, isin=isin,
            listing_status=listing_status, is_primary=is_primary,
        )],
        result_type=result_type, research_available=research_available,
        rank=rank, multibagger_score=score,
        report_url=f"/company/{instrument_id}.html",
    )


RELIANCE = _record("id-reliance", "Reliance Industries Limited", "RELIANCE", isin="INE002A01018", bse_code="500325")
TCS = _record("id-tcs", "Tata Consultancy Services Limited", "TCS", isin="INE467B01029", bse_code="532540")
BSE_ONLY = _record("id-bseonly", "BSE Only Company Ltd.", "BSEONLY", isin="INE999X01011", bse_code="500999", exchange="BSE")


def test_ranking_policy_is_versioned():
    assert SEARCH_RANKING_POLICY_VERSION


def test_exact_bse_code_matches_and_outranks_fuzzy():
    results = rank_search_candidates("500325", [RELIANCE, TCS, BSE_ONLY])
    assert results[0].record.instrument_id == "id-reliance"
    assert results[0].matched_by == "exact_bse_code"
    assert results[0].score == 98


def test_exact_isin_matches():
    results = rank_search_candidates("INE467B01029", [RELIANCE, TCS])
    assert results[0].record.instrument_id == "id-tcs"
    assert results[0].matched_by == "exact_isin"


def test_full_phrase_match_tier_finds_a_contiguous_multiword_phrase():
    # "Consultancy Services" is a contiguous phrase inside TCS's name but is
    # neither a prefix nor the whole name.
    results = rank_search_candidates("Consultancy Services", [RELIANCE, TCS])
    assert results[0].record.instrument_id == "id-tcs"
    assert results[0].matched_by == "full_phrase_match"


def test_fuzzy_never_outranks_an_exact_match_even_when_both_present():
    decoy = _record("id-decoy", "Relaince Indsutries Ltd.", "RELDECOY")  # fuzzy-close misspelling
    results = rank_search_candidates("Reliance Industries Limited", [decoy, RELIANCE])
    assert results[0].record.instrument_id == "id-reliance"
    assert results[0].matched_by == "exact_company_name"


def test_parse_exchange_hint_supports_prefix_and_suffix_syntax():
    assert parse_exchange_hint("NSE:TCS") == ("TCS", "NSE")
    assert parse_exchange_hint("BSE:500325") == ("500325", "BSE")
    assert parse_exchange_hint("TCS NSE") == ("TCS", "NSE")
    assert parse_exchange_hint("Reliance BSE") == ("Reliance", "BSE")
    assert parse_exchange_hint("TCS") == ("TCS", None)


def test_parse_exchange_hint_ignores_untrusted_colon_syntax():
    # Only the allowlisted NSE/BSE prefixes are treated as an exchange hint;
    # arbitrary "word:word" input is passed through as a literal query.
    assert parse_exchange_hint("javascript:alert(1)") == ("javascript:alert(1)", None)
    assert parse_exchange_hint("FOO:TCS") == ("FOO:TCS", None)


def test_exchange_hint_prefers_listings_on_the_requested_exchange():
    results = rank_search_candidates("TCS", [TCS], exchange="NSE")
    assert results and results[0].record.instrument_id == "id-tcs"


def test_exchange_hint_excludes_a_company_with_no_listing_on_that_exchange():
    # BSE_ONLY has no NSE listing at all; an NSE-scoped query must not
    # silently return it as if it were an NSE result.
    results = rank_search_candidates("BSE Only Company", [BSE_ONLY], exchange="NSE")
    assert results == []
    results_bse = rank_search_candidates("BSE Only Company", [BSE_ONLY], exchange="BSE")
    assert results_bse and results_bse[0].record.instrument_id == "id-bseonly"


def test_active_listing_ranks_above_inactive_listing_at_the_same_match_tier():
    active = _record("id-active", "Similar Prefix Company One Ltd.", "ACTV", listing_status="active")
    inactive = _record("id-inactive", "Similar Prefix Company Two Ltd.", "INAC", listing_status="delisted")
    results = rank_search_candidates("Similar Prefix Company", [inactive, active])
    assert [r.record.instrument_id for r in results[:2]] == ["id-active", "id-inactive"]


def test_research_availability_is_a_late_tiebreak_not_a_score_override():
    # Both are prefix matches at the identical remainder-word count (tied
    # score); research_available may only decide the tie, never promote a
    # worse match tier above a better one.
    modeled = _record(
        "id-modeled", "Tie Break Alpha Ltd.", "TBA",
        result_type=SearchResultType.MODELED, research_available=True, rank=5, score=70.0,
    )
    unmodeled = _record("id-unmodeled", "Tie Break Beta Ltd.", "TBB")
    results = rank_search_candidates("Tie Break", [unmodeled, modeled])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-modeled"


def test_research_availability_never_beats_a_better_exact_match():
    exact_unmodeled = _record("id-exact", "Precise Match Limited", "PMLT")
    modeled_fuzzy = _record(
        "id-fuzzy-modeled", "Precize Match Limitedd", "PMLX",
        result_type=SearchResultType.MODELED, research_available=True, rank=1, score=90.0,
    )
    results = rank_search_candidates("Precise Match Limited", [modeled_fuzzy, exact_unmodeled])
    assert results[0].record.instrument_id == "id-exact"
