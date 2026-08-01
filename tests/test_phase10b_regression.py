"""Phase 10B regression matrix: group-company disambiguation, additional
exact-symbol collisions, BSE code/exchange-hint queries and former-name
search, exercised against the real pinned NSE/BSE search-universe snapshots
(section 19 of the Phase 10B spec).
"""

import json
from pathlib import Path

import pytest

from mbe.models.instrument import stable_instrument_id
from mbe.search.catalog import build_search_index
from mbe.search.ranking import parse_exchange_hint, rank_search_candidates

SEARCH_UNIVERSE = json.loads(Path("universes/nse-search-universe.json").read_text())["records"]
BSE_UNIVERSE = json.loads(Path("universes/bse-search-universe.json").read_text())["records"]


@pytest.fixture(scope="module")
def index():
    return build_search_index(SEARCH_UNIVERSE, [], [], bse_rows=BSE_UNIVERSE)


def _top_symbol(query, index, **kwargs):
    results = rank_search_candidates(query, index, **kwargs)
    assert results, f"expected at least one result for {query!r}"
    return results[0].record.symbol, results


@pytest.mark.parametrize("query,expected_symbol", [
    ("ICICIBANK", "ICICIBANK"),
    ("CAMS", "CAMS"),
    ("IEX", "IEX"),
    ("Bajaj Finserv", "BAJAJFINSV"),
    ("Adani Enterprises", "ADANIENT"),
    ("Tata Power", "TATAPOWER"),
    ("Mahindra Logistics", "MAHLOG"),
])
def test_additional_exact_and_group_queries(index, query, expected_symbol):
    symbol, _ = _top_symbol(query, index)
    assert symbol == expected_symbol


def test_icici_group_query_returns_multiple_relevant_companies_not_hidden(index):
    results = rank_search_candidates("ICICI", index)
    symbols = {r.record.symbol for r in results}
    assert "ICICIBANK" in symbols
    assert len(symbols) > 1  # ICICIGI/ICICIPRULI/ICICIAMC are legitimate group results, not hidden


def test_bajaj_group_query_prefers_no_arbitrary_hiding(index):
    results = rank_search_candidates("Bajaj", index)
    symbols = {r.record.symbol for r in results}
    assert len(symbols) > 1


def test_adani_group_query_returns_multiple_companies(index):
    results = rank_search_candidates("Adani", index)
    symbols = {r.record.symbol for r in results}
    assert "ADANIENT" in symbols and "ADANIPORTS" in symbols


def test_mahindra_and_mahindra_symbol_is_exact_and_unambiguous(index):
    symbol, _ = _top_symbol("M&M", index)
    assert symbol == "M&M"


def test_bse_code_query_resolves_to_the_correct_nse_symbol_not_an_unrelated_one(index):
    # 500325 is Reliance Industries; must not resolve to any other company.
    symbol, results = _top_symbol("500325", index)
    assert symbol == "RELIANCE"
    assert results[0].matched_by == "exact_bse_code"


def test_exchange_prefix_hint_scopes_a_query_to_bse(index):
    query, exchange = parse_exchange_hint("BSE:500180")
    results = rank_search_candidates(query, index, exchange=exchange)
    assert results and results[0].record.symbol == "HDFCBANK"


def test_exchange_suffix_hint_scopes_a_query_to_nse(index):
    query, exchange = parse_exchange_hint("TCS NSE")
    results = rank_search_candidates(query, index, exchange=exchange)
    assert results and results[0].record.symbol == "TCS"


def test_untrusted_colon_syntax_is_not_treated_as_an_exchange_hint(index):
    query, exchange = parse_exchange_hint("javascript:alert(1)")
    assert exchange is None
    assert query == "javascript:alert(1)"


def test_invalid_bse_code_and_isin_return_no_matches(index):
    assert rank_search_candidates("999999", index) == []
    assert rank_search_candidates("XX0000000000", index) == []


def test_delisted_listing_does_not_rank_above_an_active_listing_at_the_same_tier():
    from mbe.search.domain import ExchangeListing, SearchIndexRecord

    active = SearchIndexRecord(
        instrument_id="id-a", display_name="Sample Match Alpha Ltd.", legal_name="Sample Match Alpha Ltd.",
        symbol="SMA", exchange="NSE", primary_exchange="NSE", listing_status="active",
        listings=[ExchangeListing(exchange="NSE", symbol="SMA", is_primary=True, listing_status="active")],
        result_type="known", report_url="/company/id-a.html",
    )
    delisted = SearchIndexRecord(
        instrument_id="id-b", display_name="Sample Match Beta Ltd.", legal_name="Sample Match Beta Ltd.",
        symbol="SMB", exchange="NSE", primary_exchange="NSE", listing_status="delisted",
        listings=[ExchangeListing(exchange="NSE", symbol="SMB", is_primary=True, listing_status="delisted")],
        result_type="known", report_url="/company/id-b.html",
    )
    results = rank_search_candidates("Sample Match", [delisted, active])
    assert results[0].record.instrument_id == "id-a"


def test_former_name_search_resolves_for_a_research_universe_company():
    research = [{
        "instrument_id": stable_instrument_id(exchange_code="NSE", symbol="ETERNAL", isin="INE758T01015"),
        "display_name": "Eternal Limited", "legal_name": "Eternal Limited", "symbol": "ETERNAL",
        "exchange": "NSE", "isin": "INE758T01015", "sector": "Consumer Services",
        "industry": "Retail", "aliases": [{"type": "former_name", "value": "Zomato Limited"}],
    }]
    index_with_former_name = build_search_index(SEARCH_UNIVERSE, research, [])
    results = rank_search_candidates("Zomato Limited", index_with_former_name)
    assert results and results[0].record.symbol == "ETERNAL"
    assert results[0].matched_by == "exact_former_name"
