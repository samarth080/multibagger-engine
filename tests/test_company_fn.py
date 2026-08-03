"""Offline tests for the lightweight-company Vercel function (loaded from
file path — api/ sits outside the mbe package). This is the serverless
fallback that lets a known-but-unmodeled NSE company (e.g. Reliance) get a
canonical /company/{id}.html page even though no static file was built for
it — the actual Phase 10A production fix, since the 250 static pages
otherwise take priority over this route."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "company_fn", Path(__file__).parent.parent / "api" / "company.py"
)
company_fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(company_fn)

RELIANCE = {
    "instrument_id": "reliance-id", "company_id": None,
    "display_name": "Reliance Industries Limited", "legal_name": "Reliance Industries Limited",
    "symbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018", "bse_code": None,
    "sector": None, "industry": None, "listing_status": "active", "is_sme": False,
    "market_cap_category": None, "aliases": [], "provider_symbol": "RELIANCE.NS",
    "result_type": "known", "research_available": False,
    "rank": None, "multibagger_score": None, "confidence": None, "risk_score": None,
    "report_url": "/company/reliance-id.html",
}
MODELED = {**RELIANCE, "instrument_id": "modeled-id", "research_available": True, "result_type": "modeled"}
INDEX = [RELIANCE, MODELED]


def _chart_payload(**meta):
    base = {"regularMarketPrice": 2945.5, "regularMarketTime": 1_700_000_000, "marketState": "CLOSED"}
    base.update(meta)
    return {"chart": {"result": [{"meta": base, "timestamp": [1_700_000_000]}]}}


def test_unknown_instrument_id_is_404_no_matching_company():
    status, html = company_fn.render_company("nonexistent-id", index=INDEX, quote_fetcher=lambda s: {})
    assert status == 404
    assert "No matching listed company" in html


def test_invalid_instrument_id_format_is_400():
    status, html = company_fn.render_company("../etc/passwd", index=INDEX, quote_fetcher=lambda s: {})
    assert status == 400


def test_known_unmodeled_company_renders_lightweight_page_with_live_quote():
    status, html = company_fn.render_company(
        "reliance-id", index=INDEX, quote_fetcher=lambda s: _chart_payload(),
    )
    assert status == 200
    assert "Reliance Industries Limited" in html
    assert "Not currently included in the Multibagger ranking universe." in html
    assert "2,945.50" in html


def test_quote_provider_failure_renders_page_without_a_fabricated_quote():
    def broken(_symbol):
        raise TimeoutError("provider down")

    status, html = company_fn.render_company("reliance-id", index=INDEX, quote_fetcher=broken)
    assert status == 200
    assert "Limited research available" in html


def test_research_available_company_is_not_served_by_the_lightweight_fallback():
    """Static routing should have served the real page already; if this
    function is somehow reached for a modeled company, it must not silently
    downgrade the page — it fails honestly instead."""
    status, html = company_fn.render_company("modeled-id", index=INDEX, quote_fetcher=lambda s: {})
    assert status == 404


def test_index_defaults_to_the_bundled_search_index_file(tmp_path, monkeypatch):
    import json

    bundled = tmp_path / "search-index.json"
    bundled.write_text(json.dumps({"data": INDEX}))
    monkeypatch.setattr(company_fn, "SEARCH_INDEX_PATHS", (bundled,))
    status, html = company_fn.render_company("reliance-id", quote_fetcher=lambda s: {})
    assert status == 200
    assert "Reliance Industries Limited" in html


def test_level_1_instrument_renders_market_coverage_label():
    status, html = company_fn.render_company(
        "reliance-id", index=INDEX, quote_fetcher=lambda s: _chart_payload(),
    )
    assert status == 200
    assert "Level 1 — Market Coverage" in html


def test_level_0_instrument_renders_identity_only_label_without_fetching_a_quote():
    calls = []
    no_symbol_index = [{**RELIANCE, "provider_symbol": None}, MODELED]
    status, html = company_fn.render_company(
        "reliance-id", index=no_symbol_index, quote_fetcher=lambda s: calls.append(s),
    )
    assert status == 200
    assert "Level 0 — Identity Coverage" in html
    assert calls == []


def test_every_coverage_level_resolves_without_a_404():
    index = [
        {**RELIANCE, "instrument_id": "id-l0", "provider_symbol": None},
        {**RELIANCE, "instrument_id": "id-l1", "provider_symbol": "L1.NS"},
    ]
    for row in index:
        status, _html = company_fn.render_company(row["instrument_id"], index=index, quote_fetcher=lambda s: None)
        assert status == 200
    # Level 3 is verified separately: it is served as a static file by
    # Vercel before this function ever runs (see api/company.py's docstring
    # and mbe.publish.render_site), so a 200-from-static-file check belongs
    # with the existing render_site tests, not here.
