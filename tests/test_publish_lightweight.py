"""render_lightweight_company_page: the Jinja page for a search-universe
company outside the research universe (Phase 10A)."""

from mbe.publish import render_lightweight_company_page

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


def test_page_shows_identity_badge_and_quote():
    html = render_lightweight_company_page(RECORD, QUOTE)
    assert "Reliance Industries Limited" in html
    assert "RELIANCE" in html
    assert "Not currently included in the Multibagger ranking universe." in html
    assert "This company has not yet been evaluated by the Multibagger scoring model." in html
    assert "2,945.50" in html
    assert "3,217.90" in html and "2,221.00" in html


def test_page_never_shows_a_fabricated_score_rank_or_explanations():
    html = render_lightweight_company_page(RECORD, QUOTE)
    assert "Multibagger Score</strong>" not in html
    assert "Strengths</h2>" not in html
    assert "Risks &amp; limitations</h2>" not in html
    assert "Research checklist</h2>" not in html
    assert "Score &amp; rank history</h2>" not in html


def test_page_handles_a_missing_quote_honestly():
    html = render_lightweight_company_page(RECORD, None)
    assert "Limited research available" in html
    assert "Unavailable" in html


def test_page_is_canonical_and_noindex_is_not_forced():
    html = render_lightweight_company_page(RECORD, QUOTE)
    assert '/company/abc-123.html' in html


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
    html = render_lightweight_company_page(CROSS_LISTED_RECORD, QUOTE)
    assert "BSE 500325" in html
    assert "Listed on NSE and BSE" in html
    assert "exchange master" in html


def test_page_shows_a_prominent_banner_for_a_delisted_company():
    delisted = {**RECORD, "listing_status": "delisted"}
    html = render_lightweight_company_page(delisted, None)
    assert "Not currently active" in html
    assert "Delisted" in html
