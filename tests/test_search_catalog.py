"""mbe.search.catalog: merging the search universe with research/ranking status.

The regression this guards: search results must not be limited to the
Nifty Smallcap 250 research universe. Every NSE-listed company in the pinned
search master must appear in the merged index, tagged honestly as modeled or
not — never with a fabricated score.
"""

from mbe.search.catalog import build_search_index
from mbe.search.domain import SearchResultType

SEARCH_UNIVERSE_ROWS = [
    {
        "source_record_id": "INE002A01018", "company_name": "Reliance Industries Limited",
        "symbol": "RELIANCE", "exchange": "NSE", "exchange_segment": None, "series": "EQ",
        "isin": "INE002A01018", "bse_code": None, "industry": None, "sector": None,
        "listing_status": "active", "listing_date": "1995-11-29", "delisting_date": None,
        "is_sme": False, "security_type": "equity",
        "provider_symbols": {"yahoo": "RELIANCE.NS"}, "aliases": [],
    },
    {
        "source_record_id": "INE044A01036", "company_name": "Sun Pharmaceutical Industries Limited",
        "symbol": "SUNPHARMA", "exchange": "NSE", "exchange_segment": None, "series": "EQ",
        "isin": "INE044A01036", "bse_code": None, "industry": None, "sector": None,
        "listing_status": "active", "listing_date": None, "delisting_date": None,
        "is_sme": False, "security_type": "equity",
        "provider_symbols": {"yahoo": "SUNPHARMA.NS"}, "aliases": [],
    },
]

# A "research universe" instrument record shaped like data["instruments"] in
# the pipeline output (mbe.publish._canonical_instruments), for the same
# Sun Pharma ISIN so it resolves to the identical canonical instrument_id.
from mbe.models.instrument import stable_instrument_id as _stable_instrument_id

SUNPHARMA_ID = _stable_instrument_id(exchange_code="NSE", symbol="SUNPHARMA", isin="INE044A01036")

RESEARCH_INSTRUMENTS = [
    {
        "instrument_id": SUNPHARMA_ID, "company_id": "company-placeholder",
        "display_name": "Sun Pharmaceutical Industries Ltd.", "legal_name": "Sun Pharmaceutical Industries Ltd.",
        "exchange": "NSE", "symbol": "SUNPHARMA", "isin": "INE044A01036",
        "sector": "Healthcare", "industry": "Pharmaceuticals", "market_cap_category": "large",
        "is_sme": False, "listing_status": "active",
        "aliases": [{"type": "abbreviation", "value": "SPIL"}],
    },
]

SCREENER_ROWS = [
    {
        "instrument_id": SUNPHARMA_ID,
        "values": {
            "rank": 3, "multibagger_score": 81.4, "confidence": 0.72, "risk_score": 22.0,
        },
    },
]


def test_every_search_universe_row_produces_a_record():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    assert len(index) == 2
    symbols = {record.symbol for record in index}
    assert symbols == {"RELIANCE", "SUNPHARMA"}


def test_unmodeled_company_is_type_known_with_no_fabricated_score():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    reliance = next(r for r in index if r.symbol == "RELIANCE")

    assert reliance.result_type == SearchResultType.KNOWN
    assert reliance.research_available is False
    assert reliance.rank is None
    assert reliance.multibagger_score is None
    assert reliance.confidence is None
    assert reliance.risk_score is None
    assert reliance.display_name == "Reliance Industries Limited"
    assert reliance.report_url == f"/company/{reliance.instrument_id}.html"


def test_modeled_company_is_type_modeled_with_rank_and_score_from_the_current_build():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    expected_id = SUNPHARMA_ID
    sunpharma = next(r for r in index if r.instrument_id == expected_id)

    assert sunpharma.result_type == SearchResultType.MODELED
    assert sunpharma.research_available is True
    assert sunpharma.rank == 3
    assert sunpharma.multibagger_score == 81.4
    assert sunpharma.confidence == 0.72
    assert sunpharma.risk_score == 22.0
    # Research-universe identity is richer (sector/industry/aliases) — prefer it.
    assert sunpharma.sector == "Healthcare"
    assert sunpharma.industry == "Pharmaceuticals"
    assert sunpharma.aliases == [{"type": "abbreviation", "value": "SPIL"}]
    assert sunpharma.report_url == f"/company/{expected_id}.html"


def test_canonical_instrument_id_matches_deterministic_derivation():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    reliance = next(r for r in index if r.symbol == "RELIANCE")
    from mbe.models.instrument import stable_instrument_id
    assert reliance.instrument_id == stable_instrument_id(
        exchange_code="NSE", symbol="RELIANCE", isin="INE002A01018"
    )


def test_wholly_empty_inputs_raise_instead_of_silently_returning_nothing():
    import pytest
    from mbe.data.provider import ProviderError
    with pytest.raises(ProviderError):
        build_search_index([], [], [])


def test_research_instrument_missing_from_search_universe_is_still_included():
    """A research-universe company must never disappear from search even if
    (hypothetically) it is momentarily absent from the wider pinned source —
    research/ranking data is authoritative for identity when present."""
    index = build_search_index([SEARCH_UNIVERSE_ROWS[0]], RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    assert len(index) == 2
    symbols = {record.symbol for record in index}
    assert "SUNPHARMA" in symbols
