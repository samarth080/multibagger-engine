"""render_coverage_company_page: the Jinja page for a search-universe
company at coverage Level 0, 1 or 2 (Phase 11 Milestone 2A)."""

from datetime import datetime, timezone

from mbe.coverage.policy import assess_coverage
from mbe.publish import render_coverage_company_page

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

RECORD = {
    "instrument_id": "abc-123", "company_id": None,
    "display_name": "Reliance Industries Limited", "legal_name": "Reliance Industries Limited",
    "symbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018", "bse_code": None,
    "sector": None, "industry": None, "listing_status": "active", "is_sme": False,
    "market_cap_category": None, "aliases": [], "provider_symbol": "RELIANCE.NS",
    "result_type": "known", "research_available": False,
    "rank": None, "multibagger_score": None, "confidence": None, "risk_score": None,
    "report_url": "/company/abc-123.html",
}
QUOTE = {"price": 2945.5, "currency": "INR", "market_status": "open", "day_change_pct": 1.2,
         "week52_high": 3217.9, "week52_low": 2221.0}


def _coverage(record=RECORD, **kwargs):
    defaults = {"has_financial_data": False, "has_model_score": False, "has_full_research_payload": False}
    return assess_coverage(record, now=NOW, **{**defaults, **kwargs})


def test_level_1_page_shows_identity_badge_quote_and_coverage_label():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert "Reliance Industries Limited" in html
    assert "RELIANCE" in html
    assert "Level 1 — Market Coverage" in html
    assert "2,945.50" in html
    assert "3,217.90" in html and "2,221.00" in html


def test_level_0_page_shows_identity_only_label_when_no_quote_mapping():
    no_symbol = {**RECORD, "provider_symbol": None}
    html = render_coverage_company_page(no_symbol, None, _coverage(no_symbol))
    assert "Level 0 — Identity Coverage" in html


def test_page_never_shows_a_fabricated_score_rank_or_explanations():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert "Multibagger Score</strong>" not in html
    assert "Strengths</h2>" not in html
    assert "Risks &amp; limitations</h2>" not in html
    assert "Research checklist</h2>" not in html
    assert "Score &amp; rank history</h2>" not in html


def test_page_handles_a_missing_quote_honestly():
    html = render_coverage_company_page(RECORD, None, _coverage())
    assert "Limited research available" in html
    assert "Unavailable" in html


def test_page_is_canonical():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert '/company/abc-123.html' in html


def test_level_2_page_shows_the_financial_summary_section():
    coverage = _coverage(has_financial_data=True)
    summary = {"revenue_cagr_3y": 0.123, "roce_3y": 0.184, "source_label": "Yahoo compatibility fallback"}
    html = render_coverage_company_page(RECORD, QUOTE, coverage, financial_summary=summary)
    assert "Level 2 — Financial Coverage" in html
    assert "Financial summary" in html
    assert "12.3%" in html
    assert "18.4%" in html
    assert "Yahoo compatibility fallback" in html


def test_level_1_page_does_not_render_an_empty_financial_summary_section():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert "Financial summary" not in html


CROSS_LISTED_RECORD = {
    **RECORD,
    "bse_code": "500325", "primary_exchange": "NSE",
    "sector": "Energy", "sector_source": "exchange_master",
    "industry": "Refineries", "industry_source": "exchange_master",
    "listings": [
        {"exchange": "NSE", "symbol": "RELIANCE", "bse_code": None, "isin": "INE002A01018",
         "listing_status": "active", "is_primary": True, "is_sme": False},
        {"exchange": "BSE", "symbol": "RELIANCE", "bse_code": "500325", "isin": "INE002A01018",
         "listing_status": "active", "is_primary": False, "is_sme": False},
    ],
}


def test_page_shows_bse_code_and_cross_listing_detail():
    html = render_coverage_company_page(CROSS_LISTED_RECORD, QUOTE, _coverage(CROSS_LISTED_RECORD))
    assert "BSE 500325" in html
    assert "Listed on NSE and BSE" in html
    assert "exchange master" in html


def test_page_shows_a_prominent_banner_for_a_delisted_company():
    delisted = {**RECORD, "listing_status": "delisted"}
    html = render_coverage_company_page(delisted, None, _coverage(delisted))
    assert "Not currently active" in html
    assert "Delisted" in html
