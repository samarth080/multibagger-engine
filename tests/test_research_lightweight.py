"""Lightweight (non-research) company payload: identity plus an optional live
quote, never a fabricated score/rank/strengths/risks/checklist/history.
"""

from datetime import datetime, timezone

import pytest

from mbe.research.lightweight import build_lightweight_research

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

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

QUOTE = {
    "price": 2945.5, "currency": "INR", "market_status": "open",
    "day_change_pct": 1.2, "week52_high": 3217.9, "week52_low": 2221.0,
}


def test_lightweight_payload_carries_identity_fields():
    payload = build_lightweight_research(RECORD, QUOTE, now=NOW)
    assert payload["identity"]["display_name"] == "Reliance Industries Limited"
    assert payload["identity"]["symbol"] == "RELIANCE"
    assert payload["identity"]["exchange"] == "NSE"
    assert payload["identity"]["instrument_id"] == "abc-123"


def test_lightweight_payload_never_fabricates_score_or_rank():
    payload = build_lightweight_research(RECORD, QUOTE, now=NOW)
    assert "score" not in payload
    assert "rank" not in payload
    assert "strengths" not in payload
    assert "risks" not in payload
    assert "checklist" not in payload
    assert "score_history" not in payload
    assert "explanations" not in payload


def test_lightweight_payload_carries_the_quote_and_52_week_range():
    payload = build_lightweight_research(RECORD, QUOTE, now=NOW)
    assert payload["quote"]["price"] == 2945.5
    assert payload["quote"]["week52_high"] == 3217.9
    assert payload["quote"]["week52_low"] == 2221.0
    assert payload["quote_state"] == "available"


def test_lightweight_payload_handles_quote_unavailable_gracefully():
    payload = build_lightweight_research(RECORD, None, now=NOW)
    assert payload["quote"] is None
    assert payload["quote_state"] == "unavailable"


def test_lightweight_payload_carries_the_required_badges():
    payload = build_lightweight_research(RECORD, QUOTE, now=NOW)
    assert payload["ranking_universe_badge"] == (
        "Not currently included in the Multibagger ranking universe."
    )
    assert payload["scoring_disclosure"] == (
        "This company has not yet been evaluated by the Multibagger scoring model."
    )


def test_lightweight_payload_reports_missing_sector_and_industry_honestly():
    payload = build_lightweight_research(RECORD, QUOTE, now=NOW)
    assert payload["identity"]["sector"] is None
    assert payload["identity"]["industry"] is None


def test_lightweight_payload_rejects_a_research_available_record():
    """A fully modeled instrument must never render the stub page — that
    would silently hide its real score/rank behind a downgraded view."""
    modeled = {**RECORD, "research_available": True, "result_type": "modeled"}
    with pytest.raises(ValueError):
        build_lightweight_research(modeled, QUOTE, now=NOW)


# --- Phase 10B: BSE cross-listing / listing-status enrichment ---

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


def test_lightweight_payload_carries_bse_code_and_all_listings():
    payload = build_lightweight_research(CROSS_LISTED_RECORD, QUOTE, now=NOW)
    assert payload["identity"]["bse_code"] == "500325"
    assert payload["identity"]["primary_exchange"] == "NSE"
    exchanges = {listing["exchange"] for listing in payload["identity"]["listings"]}
    assert exchanges == {"NSE", "BSE"}


def test_lightweight_payload_carries_classification_source_when_reliable():
    payload = build_lightweight_research(CROSS_LISTED_RECORD, QUOTE, now=NOW)
    assert payload["identity"]["sector"] == "Energy"
    assert payload["identity"]["sector_source"] == "exchange_master"
    assert payload["identity"]["industry_source"] == "exchange_master"


def test_lightweight_payload_flags_a_delisted_company_prominently():
    delisted = {**RECORD, "listing_status": "delisted"}
    payload = build_lightweight_research(delisted, None, now=NOW)
    assert payload["identity"]["listing_status"] == "delisted"
    assert payload["is_inactive"] is True
    assert "delisted" in payload["listing_status_disclosure"].lower()


def test_lightweight_payload_does_not_flag_an_active_company_as_inactive():
    payload = build_lightweight_research(RECORD, QUOTE, now=NOW)
    assert payload["is_inactive"] is False
    assert payload["listing_status_disclosure"] is None
