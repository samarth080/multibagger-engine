"""Phase 10B: BSE rows flow into the static search-index.json build alongside
the unchanged NSE search-universe rows, without altering instruments.json,
rankings.json or any 250-company research page.
"""

import json

from mbe.publish import build_data, render_site
from tests.test_publish import NOW, _result


def _nse_rows():
    return [{
        "source_record_id": "INE002A01018", "company_name": "Reliance Industries Limited",
        "symbol": "RELIANCE", "exchange": "NSE", "exchange_segment": None, "series": "EQ",
        "isin": "INE002A01018", "bse_code": None, "industry": None, "sector": None,
        "listing_status": "active", "listing_date": None, "delisting_date": None,
        "is_sme": False, "security_type": "equity",
        "provider_symbols": {"yahoo": "RELIANCE.NS"}, "aliases": [],
    }]


def _bse_rows():
    return [
        {
            "source_record_id": "INE002A01018", "company_name": "Reliance Industries Ltd.",
            "symbol": "RELIANCE", "exchange": "BSE", "exchange_segment": None, "series": "A",
            "isin": "INE002A01018", "bse_code": "500325", "industry": "Refineries", "sector": None,
            "listing_status": "active", "is_sme": False, "security_type": "equity",
        },
        {
            "source_record_id": "INE999X01011", "company_name": "BSE Only Company Ltd.",
            "symbol": "BSEONLY", "exchange": "BSE", "exchange_segment": None, "series": "B",
            "isin": "INE999X01011", "bse_code": "500999", "industry": "Trading", "sector": None,
            "listing_status": "active", "is_sme": False, "security_type": "equity",
        },
    ]


def test_search_index_merges_bse_rows_by_isin_and_adds_bse_only_companies(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(
        data, {"entered": [], "exited": []}, result, tmp_path,
        search_universe_rows=_nse_rows(), bse_rows=_bse_rows(),
    )

    search_index = json.loads((tmp_path / "api" / "v1" / "search-index.json").read_text())
    by_symbol = {row["symbol"]: row for row in search_index["data"]}

    reliance = by_symbol["RELIANCE"]
    assert reliance["bse_code"] == "500325"
    exchanges = {listing["exchange"] for listing in reliance["listings"]}
    assert exchanges == {"NSE", "BSE"}

    bse_only = by_symbol["BSEONLY"]
    assert bse_only["primary_exchange"] == "BSE"
    assert bse_only["bse_code"] == "500999"

    assert search_index["meta"]["bse_count"] == 2
    assert search_index["meta"]["cross_listed_count"] == 1

    # Unaffected by BSE ingestion:
    instruments = json.loads((tmp_path / "api" / "v1" / "instruments.json").read_text())
    assert instruments["warnings"] == [
        "Static instrument master is limited to the pinned Nifty Smallcap 250 universe."
    ]


def test_search_index_defaults_bse_rows_to_the_pinned_snapshot_when_not_overridden(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)

    search_index = json.loads((tmp_path / "api" / "v1" / "search-index.json").read_text())
    by_symbol = {row["symbol"]: row for row in search_index["data"]}
    reliance = by_symbol["RELIANCE"]
    assert reliance["bse_code"] == "500325"
    exchanges = {listing["exchange"] for listing in reliance["listings"]}
    assert exchanges == {"NSE", "BSE"}
    assert search_index["meta"]["bse_count"] > 0
