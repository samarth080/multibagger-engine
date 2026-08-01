"""Phase 10A regression suite: full Indian market discovery, restored.

Exercises the exact company list from the Phase 10A ticket against the real
pinned search-universe snapshot (universes/nse-search-universe.json — the
same file the weekly build and api/company.py bundle), merged with a small
synthetic research/ranking universe so the research-vs-non-research and
quote-available-vs-unavailable cases are covered without depending on the
production model build.
"""

import json
from pathlib import Path

import pytest

from mbe.models.instrument import stable_instrument_id
from mbe.search.catalog import build_search_index
from mbe.search.domain import SearchResultType
from mbe.search.ranking import rank_search_candidates

SEARCH_UNIVERSE = json.loads(Path("universes/nse-search-universe.json").read_text())["records"]


def _instrument_id(symbol: str, isin: str) -> str:
    return stable_instrument_id(exchange_code="NSE", symbol=symbol, isin=isin)


# A minimal, synthetic research/ranking universe: DIXON is "modeled" so the
# research-company / non-research-company contrast can be tested against the
# same real search universe as everything else, without needing the full
# 250-row production build in this test.
DIXON_ID = _instrument_id("DIXON", "INE935N01020")
RESEARCH_INSTRUMENTS = [{
    "instrument_id": DIXON_ID, "company_id": "dixon-co",
    "display_name": "Dixon Technologies (India) Ltd.", "legal_name": "Dixon Technologies (India) Ltd.",
    "symbol": "DIXON", "exchange": "NSE", "isin": "INE935N01020",
    "sector": "Consumer Durables", "industry": "Consumer Electronics",
    "is_sme": False, "listing_status": "active", "aliases": [],
}]
SCREENER_ROWS = [{
    "instrument_id": DIXON_ID,
    "values": {"rank": 12, "multibagger_score": 74.2, "confidence": 0.68, "risk_score": 31.0},
}]


@pytest.fixture(scope="module")
def index():
    return build_search_index(SEARCH_UNIVERSE, RESEARCH_INSTRUMENTS, SCREENER_ROWS)


def _top_symbol(query, index):
    results = rank_search_candidates(query, index)
    assert results, f"expected at least one result for {query!r}"
    return results[0].record.symbol, results


@pytest.mark.parametrize("query,expected_symbol,expected_name_fragment", [
    ("RELIANCE", "RELIANCE", "Reliance Industries"),
    ("TCS", "TCS", "Tata Consultancy Services"),
    ("INFY", "INFY", "Infosys"),
    ("Infosys", "INFY", "Infosys"),
    ("HDFCBANK", "HDFCBANK", "HDFC Bank"),
    ("HAL", "HAL", "Hindustan Aeronautics"),
    ("BEL", "BEL", "Bharat Electronics"),
    ("Dixon", "DIXON", "Dixon Technologies"),
    ("Polycab", "POLYCAB", "Polycab India"),
])
def test_major_company_search(index, query, expected_symbol, expected_name_fragment):
    symbol, results = _top_symbol(query, index)
    assert symbol == expected_symbol
    assert expected_name_fragment.lower() in results[0].record.display_name.lower()


def test_reliance_industries_is_discoverable_by_group_name(index):
    """Group name alone is inherently ambiguous (Reliance Industries, Power,
    Communications, ...); the requirement is that Reliance Industries is
    discoverable, not that it wins every tie — see docs/HANDOVER.md search
    architecture notes on this known limitation."""
    results = rank_search_candidates("Reliance", index)
    names = [r.record.display_name for r in results]
    assert any("Reliance Industries" in name for name in names)


def test_hdfc_bank_ranks_before_hdfc_amc(index):
    results = rank_search_candidates("HDFC", index)
    hdfc_symbols = [r.record.symbol for r in results if r.record.symbol in {"HDFCBANK", "HDFCAMC"}]
    assert hdfc_symbols[:2] == ["HDFCBANK", "HDFCAMC"]


def test_bls_collision_resolves_to_bls_international(index):
    symbol, results = _top_symbol("BLS", index)
    assert symbol == "BLS"
    assert "BLS International" in results[0].record.display_name


def test_ace_collision_resolves_to_action_construction_equipment(index):
    symbol, results = _top_symbol("ACE", index)
    assert symbol == "ACE"
    assert "Action Construction Equipment" in results[0].record.display_name


def test_vijaya_collision_resolves_to_vijaya_diagnostic(index):
    symbol, results = _top_symbol("VIJAYA", index)
    assert symbol == "VIJAYA"
    assert "Vijaya Diagnostic" in results[0].record.display_name


def test_unknown_company_returns_no_matches(index):
    results = rank_search_candidates("Zzznotarealcompanyxyz999", index)
    assert results == []


def test_research_company_is_type_modeled_with_rank_and_score(index):
    dixon = next(r for r in index if r.instrument_id == DIXON_ID)
    assert dixon.result_type == SearchResultType.MODELED
    assert dixon.research_available is True
    assert dixon.rank == 12
    assert dixon.multibagger_score == 74.2
    assert dixon.report_url == f"/company/{DIXON_ID}.html"


def test_non_research_company_is_type_known_with_no_fabricated_score(index):
    reliance_id = _instrument_id("RELIANCE", "INE002A01018")
    reliance = next(r for r in index if r.instrument_id == reliance_id)
    assert reliance.result_type == SearchResultType.KNOWN
    assert reliance.research_available is False
    assert reliance.rank is None
    assert reliance.multibagger_score is None
    assert reliance.confidence is None
    assert reliance.risk_score is None
    assert reliance.report_url == f"/company/{reliance_id}.html"


def test_quote_unavailable_renders_the_lightweight_page_honestly():
    """api/company.py must render a real 200 page — not a fabricated quote —
    when the live provider fails for a non-research company."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "company_fn_regression", Path("api/company.py"),
    )
    company_fn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(company_fn)

    reliance_id = _instrument_id("RELIANCE", "INE002A01018")
    record = {
        "instrument_id": reliance_id, "display_name": "Reliance Industries Limited",
        "legal_name": "Reliance Industries Limited", "symbol": "RELIANCE", "exchange": "NSE",
        "isin": "INE002A01018", "bse_code": None, "sector": None, "industry": None,
        "listing_status": "active", "is_sme": False, "market_cap_category": None,
        "aliases": [], "provider_symbol": "RELIANCE.NS", "result_type": "known",
        "research_available": False, "rank": None, "multibagger_score": None,
        "confidence": None, "risk_score": None, "report_url": f"/company/{reliance_id}.html",
    }

    def broken(_symbol):
        raise TimeoutError("provider unreachable")

    status, html = company_fn.render_company(reliance_id, index=[record], quote_fetcher=broken)
    assert status == 200
    assert "Reliance Industries Limited" in html
    assert "Limited research available" in html
    assert "Not currently included in the Multibagger ranking universe." in html


def test_research_page_unavailable_for_a_modeled_instrument_fails_honestly():
    """If the lightweight fallback is ever reached for an already-modeled
    company (static build out of sync), it must not silently render a
    downgraded stub — it must fail loudly instead."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "company_fn_regression2", Path("api/company.py"),
    )
    company_fn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(company_fn)

    dixon_record = {
        "instrument_id": DIXON_ID, "display_name": "Dixon Technologies (India) Ltd.",
        "legal_name": "Dixon Technologies (India) Ltd.", "symbol": "DIXON", "exchange": "NSE",
        "isin": "INE935N01020", "bse_code": None, "sector": "Consumer Durables",
        "industry": "Consumer Electronics", "listing_status": "active", "is_sme": False,
        "market_cap_category": None, "aliases": [], "provider_symbol": "DIXON.NS",
        "result_type": "modeled", "research_available": True, "rank": 12,
        "multibagger_score": 74.2, "confidence": 0.68, "risk_score": 31.0,
        "report_url": f"/company/{DIXON_ID}.html",
    }
    status, html = company_fn.render_company(
        DIXON_ID, index=[dixon_record], quote_fetcher=lambda s: {},
    )
    assert status == 404
