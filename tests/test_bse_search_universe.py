"""BSE search-universe source (Phase 10B).

BSE's official endpoints (api.bseindia.com, www.bseindia.com downloads) are
not reachable from this repository's network sandbox — every attempt during
development returned either a bot-protection error page or the site's
client-side-routed app shell instead of data (verified, not assumed). Rather
than fabricate broad BSE coverage, `BseListedSecurityProvider` is built to
the same fail-closed contract as the NSE provider and is fetch-capable for
whenever an official feed is reachable (CI, a different network, a future
authorized mirror); the pinned snapshot committed at
universes/bse-search-universe.json is instead a small, explicitly-labeled
starter fixture of long-stable, extremely well-documented large-cap BSE
scrip codes, cross-linked by the real ISINs already verified against the
live-fetched NSE snapshot in Phase 10A. See docs/search-architecture.md
"BSE coverage and honesty about sourcing".
"""

import json
from pathlib import Path

import pytest

from mbe.data.bse_search_master import (
    BSE_SEARCH_SOURCES,
    BseListedSecurityProvider,
    parse_bse_listed_security_csv,
)
from mbe.data.provider import ProviderError
from mbe.instruments.importer import SourceInstrumentRow

MAIN_CSV = (
    "Security Code,Security Id,Security Name,Status,Group,Face Value,ISIN No,Industry\n"
    "500325,RELIANCE,Reliance Industries Ltd.,Active,A,10,INE002A01018,Refineries\n"
    "532540,TCS,Tata Consultancy Services Ltd.,Active,A,1,INE467B01029,Computer Education\n"
    "500009,DEFUNCTCO,Defunct Company Ltd.,Delisted,Z,10,INE999Z01019,Textiles\n"
)


def test_main_board_csv_parses_into_canonical_source_rows():
    rows = [SourceInstrumentRow(**row) for row in parse_bse_listed_security_csv(MAIN_CSV)]
    by_code = {row.bse_code: row for row in rows}

    assert set(by_code) == {"500325", "532540", "500009"}
    reliance = by_code["500325"]
    assert reliance.company_name == "Reliance Industries Ltd."
    assert reliance.isin == "INE002A01018"
    assert reliance.exchange == "BSE"
    assert reliance.symbol == "RELIANCE"
    assert reliance.listing_status == "active"
    assert reliance.industry == "Refineries"
    assert reliance.provider_symbols == {}  # BSE has no Yahoo-style provider symbol convention here

    delisted = by_code["500009"]
    assert delisted.listing_status == "delisted"


def test_bse_code_is_validated_as_six_digits():
    rows = [SourceInstrumentRow(**row) for row in parse_bse_listed_security_csv(MAIN_CSV)]
    for row in rows:
        assert row.bse_code is not None
        assert len(row.bse_code) == 6 and row.bse_code.isdigit()


def test_reshaped_or_empty_source_fails_closed():
    with pytest.raises(ProviderError):
        parse_bse_listed_security_csv("Code,Name\n500325,Reliance\n")
    with pytest.raises(ProviderError):
        parse_bse_listed_security_csv(
            "Security Code,Security Id,Security Name,Status,Group,Face Value,ISIN No,Industry\n"
        )


def test_rows_missing_code_or_isin_are_skipped():
    text = MAIN_CSV + ",NONAME,No Code Ltd.,Active,A,10,INE888A01011,Other\n"
    text += "500700,NOISIN,No ISIN Ltd.,Active,A,10,,Other\n"
    rows = parse_bse_listed_security_csv(text)
    assert len(rows) == 3


def test_provider_snapshot_is_versioned_and_offline_capable():
    provider = BseListedSecurityProvider(fetcher=lambda url: MAIN_CSV)
    snapshot = provider.fetch_instruments()

    assert snapshot.source == "bse_listed_securities:main"
    assert snapshot.source_url == BSE_SEARCH_SOURCES["main"]
    assert snapshot.source_version.startswith("sha256:")
    assert len(snapshot.records) == 3
    assert provider.health()["capability"] == "search_universe"


def test_provider_failure_is_loud():
    def broken(_url: str) -> str:
        raise TimeoutError("BSE site blocked automated access")

    with pytest.raises(ProviderError):
        BseListedSecurityProvider(fetcher=broken).fetch_instruments()


def test_pinned_starter_fixture_is_explicitly_labeled_and_isin_verified():
    """The committed pinned snapshot must disclose that it is a small,
    curated starter set rather than full BSE breadth, and every ISIN in it
    must match the corresponding NSE symbol already verified in Phase 10A's
    live-fetched universes/nse-search-universe.json."""
    payload = json.loads(Path("universes/bse-search-universe.json").read_text())
    assert payload["coverage_status"] == "curated_starter_fixture_pending_live_verification"
    assert 15 <= payload["n"] <= 40
    assert payload["n"] == len(payload["records"])

    nse_by_isin = {
        row["isin"]: row["symbol"]
        for row in json.loads(Path("universes/nse-search-universe.json").read_text())["records"]
    }
    for row in payload["records"]:
        assert row["isin"] in nse_by_isin, f"BSE fixture ISIN {row['isin']} has no NSE cross-check"
        assert row["bse_code"] and len(row["bse_code"]) == 6 and row["bse_code"].isdigit()
