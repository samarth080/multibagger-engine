"""Search-universe source: official NSE listed-security lists.

The search universe is deliberately wider than the ranking universe.  These
tests pin the parser/provider contract for the official NSE equity and SME
lists so a silently-empty or reshaped source fails closed instead of shrinking
search back to the modelled universe.
"""

import json
from pathlib import Path

import pytest

from mbe.data.nse_search_master import (
    NSE_SEARCH_SOURCES,
    NseListedSecurityProvider,
    parse_nse_listed_security_csv,
)
from mbe.data.provider import ProviderError
from mbe.instruments.importer import SourceInstrumentRow
from mbe.models.instrument import stable_instrument_id

MAIN_CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE,"
    " MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
    "TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,1,1,INE467B01029,1\n"
    "HAL,Hindustan Aeronautics Limited,EQ,28-MAR-2018,10,1,INE066F01020,10\n"
)
SME_CSV = (
    "SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,"
    "ISIN_NUMBER,FACE_VALUE,\n"
    "METALIC,Metalic Technoforge Limited,ST,28-Jul-26,10,INE1II801013,10,\n"
)


def test_main_board_csv_parses_into_canonical_source_rows():
    rows = [SourceInstrumentRow(**row) for row in parse_nse_listed_security_csv(MAIN_CSV)]
    by_symbol = {row.symbol: row for row in rows}

    assert set(by_symbol) == {"RELIANCE", "TCS", "HAL"}
    reliance = by_symbol["RELIANCE"]
    assert reliance.company_name == "Reliance Industries Limited"
    assert reliance.isin == "INE002A01018"
    assert reliance.series == "EQ"
    assert reliance.exchange == "NSE"
    assert reliance.is_sme is False
    assert reliance.listing_status == "active"
    assert reliance.provider_symbols == {"yahoo": "RELIANCE.NS"}
    assert reliance.listing_date is not None and reliance.listing_date.year == 1995


def test_sme_csv_variant_parses_and_marks_sme_listings():
    rows = [SourceInstrumentRow(**row) for row in parse_nse_listed_security_csv(SME_CSV, is_sme=True)]

    assert len(rows) == 1
    assert rows[0].symbol == "METALIC"
    assert rows[0].company_name == "Metalic Technoforge Limited"
    assert rows[0].isin == "INE1II801013"
    assert rows[0].is_sme is True
    assert rows[0].exchange_segment == "SME"


def test_reshaped_or_empty_source_fails_closed():
    with pytest.raises(ProviderError):
        parse_nse_listed_security_csv("TICKER,NAME\nRELIANCE,Reliance\n")
    with pytest.raises(ProviderError):
        parse_nse_listed_security_csv(
            "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE,"
            " MARKET LOT, ISIN NUMBER, FACE VALUE\n"
        )


def test_rows_without_symbol_or_with_unsupported_series_are_skipped():
    text = MAIN_CSV + ",Nameless Company,EQ,01-JAN-2020,10,1,INE000A01001,10\n"
    rows = parse_nse_listed_security_csv(text)
    assert len(rows) == 3


def test_provider_snapshot_is_versioned_and_offline_capable():
    provider = NseListedSecurityProvider("nse_equity", fetcher=lambda url: MAIN_CSV)
    snapshot = provider.fetch_instruments()

    assert snapshot.source == "nse_listed_securities:nse_equity"
    assert snapshot.source_url == NSE_SEARCH_SOURCES["nse_equity"]["url"]
    assert snapshot.source_version.startswith("sha256:")
    assert len(snapshot.records) == 3
    assert provider.health()["capability"] == "search_universe"


def test_provider_failure_is_loud():
    def broken(_url: str) -> str:
        raise TimeoutError("network down")

    with pytest.raises(ProviderError):
        NseListedSecurityProvider("nse_equity", fetcher=broken).fetch_instruments()


def test_unknown_segment_is_rejected():
    with pytest.raises(KeyError):
        NseListedSecurityProvider("bse_everything")


def test_pinned_search_universe_covers_the_research_universe_with_identical_ids():
    """The regression guard: every modelled instrument must keep its canonical
    ID inside the wider search universe, and the search universe must be
    strictly larger than the ranking universe."""
    search_universe = json.loads(Path("universes/nse-search-universe.json").read_text())
    research_master = json.loads(
        Path("universes/nifty-smallcap250-instruments.json").read_text()
    )
    records = search_universe["records"]

    assert search_universe["n"] == len(records)
    assert len(records) > 2000, "search universe must span the NSE main board"

    search_ids = {
        stable_instrument_id(exchange_code="NSE", symbol=row["symbol"], isin=row["isin"]): row
        for row in records
    }
    assert len(search_ids) == len(records), "duplicate canonical identity in search universe"

    for row in research_master["records"]:
        canonical = stable_instrument_id(
            exchange_code="NSE", symbol=row["symbol"], isin=row["isin"]
        )
        assert canonical in search_ids, f"{row['symbol']} disappeared from the search universe"
        assert search_ids[canonical]["symbol"] == row["symbol"]

    symbols = {row["symbol"] for row in records}
    for expected in ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "HAL", "BEL", "DIXON", "POLYCAB", "TRENT"):
        assert expected in symbols
