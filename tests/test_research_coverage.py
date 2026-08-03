from datetime import datetime, timezone

import pytest

from mbe.coverage.policy import assess_coverage
from mbe.research.coverage import build_coverage_research

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


def _coverage(**kwargs):
    defaults = {"has_financial_data": False, "has_model_score": False, "has_full_research_payload": False}
    return assess_coverage(RECORD, now=NOW, **{**defaults, **kwargs})


def test_level_1_payload_carries_identity_and_quote_but_no_financial_summary():
    payload = build_coverage_research(RECORD, QUOTE, _coverage(), now=NOW)
    assert payload["identity"]["display_name"] == "Reliance Industries Limited"
    assert payload["quote"]["price"] == 2945.5
    assert payload["financial_summary"] is None
    assert payload["coverage"]["research_coverage_level"] == 1


def test_level_2_payload_includes_the_financial_summary_when_given():
    coverage = _coverage(has_financial_data=True)
    summary = {"revenue_cagr_3y": 0.12, "roce_3y": 0.18, "source_label": "Yahoo compatibility fallback"}
    payload = build_coverage_research(RECORD, QUOTE, coverage, financial_summary=summary, now=NOW)
    assert payload["coverage"]["research_coverage_level"] == 2
    assert payload["financial_summary"] == summary


def test_level_0_payload_omits_financial_summary_even_if_one_is_passed():
    coverage = assess_coverage(
        {**RECORD, "provider_symbol": None}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    payload = build_coverage_research(
        {**RECORD, "provider_symbol": None}, None, coverage,
        financial_summary={"revenue_cagr_3y": 0.1}, now=NOW,
    )
    assert payload["financial_summary"] is None


def test_refuses_a_level_3_assessment():
    coverage = _coverage(has_financial_data=True, has_model_score=True, has_full_research_payload=True)
    with pytest.raises(ValueError, match="Level 3"):
        build_coverage_research(RECORD, QUOTE, coverage, now=NOW)


def test_never_fabricates_score_or_rank_fields():
    payload = build_coverage_research(RECORD, QUOTE, _coverage(), now=NOW)
    assert "score" not in payload
    assert "rank" not in payload
    assert "strengths" not in payload
