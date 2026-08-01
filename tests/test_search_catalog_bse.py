"""Phase 10B: BSE cross-listing merge in mbe.search.catalog.

An NSE row and a BSE row sharing an ISIN must fold into ONE SearchIndexRecord
with two listings, never two separate results and never a silent overwrite —
the Phase 10A regression this guards against was exactly "later row wins."
"""

from mbe.models.instrument import stable_instrument_id
from mbe.search.catalog import build_search_index
from mbe.search.domain import SearchResultType


def _nse_row(symbol, name, isin, **extra):
    row = {
        "source_record_id": isin, "company_name": name, "symbol": symbol,
        "exchange": "NSE", "exchange_segment": None, "series": "EQ", "isin": isin,
        "bse_code": None, "industry": None, "sector": None, "listing_status": "active",
        "listing_date": None, "delisting_date": None, "is_sme": False,
        "security_type": "equity", "provider_symbols": {"yahoo": f"{symbol}.NS"},
        "aliases": [],
    }
    row.update(extra)
    return row


def _bse_row(symbol, bse_code, name, isin, **extra):
    row = {
        "source_record_id": isin, "company_name": name, "symbol": symbol,
        "exchange": "BSE", "exchange_segment": None, "series": "A", "isin": isin,
        "bse_code": bse_code, "industry": None, "sector": None, "listing_status": "active",
        "listing_date": None, "delisting_date": None, "is_sme": False,
        "security_type": "equity",
    }
    row.update(extra)
    return row


def test_bse_only_company_becomes_a_known_result_with_bse_as_primary_exchange():
    index = build_search_index([], [], [], bse_rows=[_bse_row("SOMECO", "500999", "Some Company Ltd.", "INE999X01011")])
    assert len(index) == 1
    record = index[0]
    assert record.primary_exchange == "BSE"
    assert record.exchange == "BSE"
    assert record.bse_code == "500999"
    assert record.result_type == SearchResultType.KNOWN
    assert len(record.listings) == 1
    assert record.listings[0].exchange == "BSE" and record.listings[0].is_primary is True


def test_matching_isin_merges_nse_and_bse_into_one_record_with_two_listings():
    nse = _nse_row("RELIANCE", "Reliance Industries Limited", "INE002A01018")
    bse = _bse_row("RELIANCE", "500325", "Reliance Industries Ltd.", "INE002A01018")
    index = build_search_index([nse], [], [], bse_rows=[bse])

    assert len(index) == 1
    record = index[0]
    assert record.primary_exchange == "NSE"
    assert record.symbol == "RELIANCE"
    assert record.bse_code == "500325"
    expected_id = stable_instrument_id(exchange_code="NSE", symbol="RELIANCE", isin="INE002A01018")
    assert record.instrument_id == expected_id
    exchanges = {listing.exchange for listing in record.listings}
    assert exchanges == {"NSE", "BSE"}
    nse_listing = next(l for l in record.listings if l.exchange == "NSE")
    bse_listing = next(l for l in record.listings if l.exchange == "BSE")
    assert nse_listing.is_primary is True
    assert bse_listing.is_primary is False
    assert bse_listing.bse_code == "500325"


def test_research_company_still_merges_its_bse_cross_listing():
    research = [{
        "instrument_id": stable_instrument_id(exchange_code="NSE", symbol="DIXON", isin="INE935N01020"),
        "display_name": "Dixon Technologies (India) Ltd.", "legal_name": "Dixon Technologies (India) Ltd.",
        "symbol": "DIXON", "exchange": "NSE", "isin": "INE935N01020",
        "sector": "Consumer Durables", "industry": "Consumer Electronics",
    }]
    bse = _bse_row("DIXON", "540699", "Dixon Technologies Ltd.", "INE935N01020")
    index = build_search_index([], research, [], bse_rows=[bse])

    assert len(index) == 1
    record = index[0]
    assert record.result_type in {SearchResultType.MODELED, SearchResultType.KNOWN}
    assert record.sector == "Consumer Durables"  # research identity still wins
    exchanges = {listing.exchange for listing in record.listings}
    assert exchanges == {"NSE", "BSE"}
    assert record.bse_code == "540699"


def test_bse_cross_listing_never_overwrites_nse_listing_status():
    nse = _nse_row("ALPHA", "Alpha Ltd.", "INE000A01018", listing_status="active")
    bse = _bse_row("ALPHA", "500700", "Alpha Ltd.", "INE000A01018", listing_status="delisted")
    index = build_search_index([nse], [], [], bse_rows=[bse])

    record = index[0]
    assert record.listing_status == "active"  # primary (NSE) listing status
    bse_listing = next(l for l in record.listings if l.exchange == "BSE")
    assert bse_listing.listing_status == "delisted"


def test_bse_cross_listing_backfills_missing_industry_with_exchange_source():
    """The Phase 10B gap this guards: a BSE row's Industry classification
    must enrich an existing unmodeled NSE-only record when that record has
    no classification yet — not be silently dropped on merge."""
    nse = _nse_row("RELIANCE", "Reliance Industries Limited", "INE002A01018")
    bse = _bse_row("RELIANCE", "500325", "Reliance Industries Ltd.", "INE002A01018", industry="Refineries")
    index = build_search_index([nse], [], [], bse_rows=[bse])

    record = index[0]
    assert record.industry == "Refineries"
    assert record.industry_source == "exchange_master"


def test_bse_cross_listing_never_overwrites_an_existing_industry_classification():
    nse = _nse_row("RELIANCE", "Reliance Industries Limited", "INE002A01018", industry="Oil & Gas")
    bse = _bse_row("RELIANCE", "500325", "Reliance Industries Ltd.", "INE002A01018", industry="Refineries")
    index = build_search_index([nse], [], [], bse_rows=[bse])

    record = index[0]
    assert record.industry == "Oil & Gas"  # first-seen (NSE) source wins; never silently overwritten


def test_two_unrelated_bse_only_companies_stay_separate_results():
    index = build_search_index([], [], [], bse_rows=[
        _bse_row("ONE", "500001", "One Company Ltd.", "INE001A01011"),
        _bse_row("TWO", "500002", "Two Company Ltd.", "INE002B01012"),
    ])
    assert len(index) == 2
    assert {r.symbol for r in index} == {"ONE", "TWO"}
