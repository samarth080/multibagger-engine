"""Offline tests for the lightweight-company Vercel function (loaded from
file path — api/ sits outside the mbe package). This is the serverless
fallback that lets a known-but-unmodeled NSE company (e.g. Reliance) get a
canonical /company/{id}.html page even though no static file was built for
it — the actual Phase 10A production fix, since the 250 static pages
otherwise take priority over this route."""

import importlib.util
from pathlib import Path

import pandas as pd

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


_SAMPLE_CHART = _chart_payload()


def _record(*, instrument_id, provider_symbol, research_available=False, **overrides):
    """Build an index record from the RELIANCE fixture shape, overriding
    only the fields a given test cares about — reuses the existing fixture
    rather than duplicating its full identity shape."""
    return {
        **RELIANCE, "instrument_id": instrument_id, "provider_symbol": provider_symbol,
        "research_available": research_available, **overrides,
    }


def _fail_if_called_provider_factory():
    """Passed as `universal_provider` (a zero-arg factory, not a provider
    instance) — raising here proves render_company never even constructs a
    live provider on the cache-hit / no-provider-symbol paths, a stronger
    guarantee than merely never calling the provider's methods."""
    raise AssertionError("universal provider factory should not have been called")


class _StubUniversalProvider:
    """Same shape as tests/test_universal_pipeline.py's _StubProvider —
    enough fabricated financial/price data for mbe.universal.pipeline to
    produce a real (non-None) score."""

    def get_info(self, ticker):
        from mbe.models.company import CompanyInfo
        return CompanyInfo(ticker=ticker, sector="Technology", industry="Software", market_cap=5e10)

    def get_financials(self, ticker):
        from mbe.models.company import FinancialHistory
        years = {2023: 100.0, 2024: 130.0, 2025: 170.0}
        return FinancialHistory(data={
            "revenue": years, "net_income": {y: v * 0.1 for y, v in years.items()},
            "cfo": {y: v * 0.12 for y, v in years.items()}, "capex": {y: -v * 0.04 for y, v in years.items()},
            "fcf": {y: v * 0.08 for y, v in years.items()}, "total_equity": {y: v * 0.5 for y, v in years.items()},
            "total_debt": {y: v * 0.1 for y, v in years.items()}, "cash": {y: v * 0.2 for y, v in years.items()},
            "total_assets": {y: v * 0.9 for y, v in years.items()},
            "current_assets": {y: v * 0.4 for y, v in years.items()},
            "current_liabilities": {y: v * 0.2 for y, v in years.items()},
            "interest_expense": {y: v * 0.01 for y, v in years.items()},
            "shares_diluted": {y: 1_000_000.0 for y in years},
        })

    def get_prices(self, ticker, years=3):
        from mbe.models.company import PriceHistory
        idx = pd.bdate_range("2023-01-01", periods=260)
        closes = [100 + i * 0.1 for i in range(len(idx))]
        df = pd.DataFrame({
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000 for _ in closes],
        }, index=idx)
        return PriceHistory(ticker=ticker, df=df)

    def benchmark_ticker(self, ticker):
        return "^NSEI"


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


def _capture_universal(monkeypatch, captured):
    """Patch company_fn.render_coverage_company_page to record the
    `universal` kwarg it was called with, while still delegating to the
    real function so status/html assertions keep working unchanged.

    Note: company_coverage.html (Task 14, not yet landed) doesn't render
    anything from company.universal yet, so the raw HTML has no string to
    assert on for the score. These tests instead verify the Python-level
    payload threading — record -> _universal_payload -> render_coverage_
    company_page — which is what this task actually implements."""
    original = company_fn.render_coverage_company_page

    def _capture(record, quote, coverage, financial_summary=None, *, universal=None):
        captured["universal"] = universal
        return original(record, quote, coverage, financial_summary, universal=universal)

    monkeypatch.setattr(company_fn, "render_coverage_company_page", _capture)


def test_render_company_uses_a_prewarmed_universal_artifact_when_present(tmp_path, monkeypatch):
    from mbe.universal.cache import write_cached_report

    index = [_record(instrument_id="id-1", provider_symbol="AAA.NS")]
    artifacts_dir = tmp_path / "universal-scores"
    write_cached_report(artifacts_dir / "id-1.json", {
        "instrument_id": "id-1", "cache_key": "k1", "policy_version": "universal-score-v1",
        "generated_at": "2026-08-04T00:00:00+00:00",
        "report": {"executive_summary": {
            "overall_score": 70.0, "confidence": "Medium", "data_coverage_pct": 60.0,
            "report_state": "full_evaluated_report", "company_type": "general_corporate",
        }},
    })
    captured = {}
    _capture_universal(monkeypatch, captured)

    status, html = company_fn.render_company(
        "id-1", index=index, quote_fetcher=lambda symbol: _SAMPLE_CHART,
        universal_artifacts_dir=artifacts_dir, universal_provider=_fail_if_called_provider_factory,
    )

    assert status == 200
    # Rendered from the pre-warmed artifact, not live-computed — the
    # fail-if-called factory proves no live computation (not even provider
    # construction) was attempted.
    assert captured["universal"]["executive_summary"]["overall_score"] == 70.0


def test_render_company_falls_back_to_live_computation_when_no_artifact(tmp_path, monkeypatch):
    index = [_record(instrument_id="id-2", provider_symbol="BBB.NS")]
    captured = {}
    _capture_universal(monkeypatch, captured)

    status, html = company_fn.render_company(
        "id-2", index=index, quote_fetcher=lambda symbol: _SAMPLE_CHART,
        universal_artifacts_dir=tmp_path / "empty",
        universal_provider=_StubUniversalProvider,
    )

    assert status == 200
    assert captured["universal"] is not None
    assert captured["universal"]["executive_summary"]["overall_score"] is not None


def test_render_company_never_computes_universal_score_without_a_provider_symbol(tmp_path):
    index = [_record(instrument_id="id-3", provider_symbol=None)]

    status, html = company_fn.render_company(
        "id-3", index=index, quote_fetcher=lambda s: (_ for _ in ()).throw(AssertionError("quote should not be fetched")),
        universal_artifacts_dir=tmp_path, universal_provider=_fail_if_called_provider_factory,
    )

    assert status == 200  # no exception raised — the fail-if-called provider was never touched
