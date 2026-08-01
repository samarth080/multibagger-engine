from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mbe.db.base import Base
from mbe.db.models import (
    CompanyRow, ExchangeRow, InstrumentAliasRow, InstrumentListingRow,
    InstrumentRow, ProviderSymbolRow,
)
from mbe.instruments.resolution import InstrumentResolver
from mbe.models.instrument import normalize_name, normalize_symbol, stable_instrument_id


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ExchangeRow(
            code="NSE", name="National Stock Exchange of India", mic="XNSE",
            country="IN", currency="INR", timezone="Asia/Kolkata",
        ))
        session.add(ExchangeRow(
            code="BSE", name="BSE Limited", mic="XBOM",
            country="IN", currency="INR", timezone="Asia/Kolkata",
        ))
        company_id = "company-a"
        instrument_id = stable_instrument_id(
            exchange_code="NSE", symbol="ALPHA", isin="INE000A01018"
        )
        session.add(CompanyRow(
            company_id=company_id, legal_name="Alpha Industries Limited",
            current_legal_name="Alpha Industries Limited", display_name="Alpha Industries",
            country="IN",
        ))
        session.add(InstrumentRow(
            instrument_id=instrument_id, company_id=company_id, security_type="equity",
            country="IN", currency="INR", timezone="Asia/Kolkata", quality_status="valid",
        ))
        session.add(InstrumentListingRow(
            instrument_id=instrument_id, exchange_code="NSE", symbol="ALPHA",
            isin="INE000A01018", status="active", is_primary=True, is_sme=False,
        ))
        session.add(ProviderSymbolRow(
            instrument_id=instrument_id, provider="yahoo", provider_symbol="ALPHA.NS",
            is_primary=True,
        ))
        session.add_all([
            InstrumentAliasRow(
                instrument_id=instrument_id, alias_type="former_name",
                value="Old Alpha Limited", normalized_value=normalize_name("Old Alpha Limited"),
            ),
            InstrumentAliasRow(
                instrument_id=instrument_id, alias_type="abbreviation",
                value="AIL", normalized_value="ail",
            ),
        ])
        session.commit()
        yield session


def test_identity_normalization_and_stable_id():
    assert normalize_symbol(" alpha.ns ") == "ALPHA.NS"
    assert normalize_name("Alpha Industries, Ltd.", strip_suffixes=True) == "alpha industries"
    a = stable_instrument_id(exchange_code="NSE", symbol="ALPHA", isin="INE000A01018")
    b = stable_instrument_id(exchange_code="BSE", symbol="500001", isin="INE000A01018")
    assert a == b  # cross-listing/provider symbols do not become identity


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("alpha", "exact_nse_symbol"),
        ("ALPHA.NS", "exact_nse_symbol"),
        ("INE000A01018", "exact_isin"),
        ("Alpha Industries Limited", "exact_company_name"),
        ("Old Alpha Limited", "exact_former_name"),
        ("ALPHA.NS", "exact_nse_symbol"),
    ],
)
def test_resolution_match_priority(session, query, reason):
    matches = InstrumentResolver(session).resolve(query)
    assert matches and matches[0].matched_by == reason


def test_bse_code_inactive_and_sme_are_representable(session):
    instrument_id = session.scalar(select(InstrumentRow.instrument_id))
    # A secondary listing is not primary and can carry different lifecycle flags.
    session.add(InstrumentListingRow(
        instrument_id=instrument_id, exchange_code="BSE", symbol="ALPHA-B",
        bse_code="500001", isin="INE000A01018", status="inactive",
        is_primary=False, is_sme=True, delisting_date=date(2025, 1, 1),
    ))
    session.commit()
    match = InstrumentResolver(session).resolve("500001")[0]
    assert match.matched_by == "exact_bse_code"
    row = session.scalar(select(InstrumentListingRow).where(
        InstrumentListingRow.bse_code == "500001"
    ))
    assert row.status == "inactive" and row.is_sme is True

    # Phase 10B: the full cross-listing detail is exposed, not just primary.
    by_exchange = {listing.exchange: listing for listing in match.listings}
    assert set(by_exchange) == {"NSE", "BSE"}
    assert by_exchange["BSE"].bse_code == "500001"
    assert by_exchange["BSE"].is_primary is False
    assert by_exchange["NSE"].is_primary is True


def test_short_alias_never_outranks_exact_company_name(session):
    session.add(CompanyRow(
        company_id="company-ail", legal_name="AIL Limited",
        current_legal_name="AIL Limited", display_name="AIL Limited", country="IN",
    ))
    session.add(InstrumentRow(
        instrument_id="instrument-ail", company_id="company-ail", security_type="equity",
        country="IN", currency="INR", timezone="Asia/Kolkata", quality_status="warning",
    ))
    session.add(InstrumentListingRow(
        instrument_id="instrument-ail", exchange_code="NSE", symbol="AILCO",
        status="active", is_primary=True, is_sme=False,
    ))
    session.commit()
    matches = InstrumentResolver(session).resolve("AIL")
    assert matches[0].instrument_id == "instrument-ail"
    assert matches[0].matched_by == "exact_company_name"


def test_duplicate_current_provider_symbol_is_constrained(session):
    session.add(InstrumentRow(
        instrument_id="instrument-b", company_id=None, security_type="equity",
        country="IN", currency="INR", timezone="Asia/Kolkata", quality_status="warning",
    ))
    session.add(ProviderSymbolRow(
        instrument_id="instrument-b", provider="yahoo", provider_symbol="ALPHA.NS",
        is_primary=True,
    ))
    with pytest.raises(IntegrityError):
        session.commit()
