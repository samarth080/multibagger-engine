"""Phase 10B additive dynamic-API surface: BSE cross-listing exposure on
GET /api/v1/search and GET /api/v1/company/{id}/summary, exchange/active/
SME/inactive query params, and the new GET /api/v1/search/meta route.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mbe.api.app import create_app
from mbe.data.registry import ProviderRegistry
from mbe.db.base import Base
from mbe.db.models import InstrumentListingRow, ProviderSymbolRow
from mbe.db.repository import PlatformRepository
from mbe.instruments.importer import import_instruments
from mbe.pipeline import screen
from mbe.versioning import build_manifest
from tests.test_pipeline import StubProvider


class NoQuotes:
    name = "none"

    def health(self):
        return {"provider": "none", "status": "ok"}

    def get_quotes(self, mappings):
        return []


@pytest.fixture()
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        import_instruments(session, [{
            "company_name": "Reliance Industries Limited", "symbol": "RELIANCE", "exchange": "NSE",
            "isin": "INE002A01018", "listing_status": "active",
            "provider_symbols": {"yahoo": "RELIANCE.NS"}, "aliases": [],
        }], source_code="nse_test", source_version="v1")
        import_instruments(session, [{
            "company_name": "Reliance Industries Ltd.", "symbol": "RELIANCE", "exchange": "BSE",
            "bse_code": "500325", "isin": "INE002A01018", "listing_status": "active",
        }], source_code="bse_test", source_version="v1")
        import_instruments(session, [{
            "company_name": "SME Only Company Limited", "symbol": "SMEONLY", "exchange": "NSE",
            "isin": "INE111S01011", "listing_status": "active", "is_sme": True,
            "provider_symbols": {"yahoo": "SMEONLY.NS"},
        }], source_code="nse_test", source_version="v1")
        import_instruments(session, [{
            "company_name": "Delisted Company Limited", "symbol": "GONE", "exchange": "NSE",
            "isin": "INE222D01012", "listing_status": "delisted",
            "provider_symbols": {"yahoo": "GONE.NS"},
        }], source_code="nse_test", source_version="v1")
        mappings = session.scalars(select(ProviderSymbolRow)).all()
        ids = {m.provider_symbol: m.instrument_id for m in mappings}
        reliance_id = ids["RELIANCE.NS"]
    result = screen(["RELIANCE.NS"], StubProvider())
    manifest = build_manifest(
        universe_name="unit", tickers=["RELIANCE.NS"],
        built_at=datetime.now(timezone.utc), source_date="v1",
        attempted=1, scored=1, failed=0,
    )
    with Session(engine) as session:
        PlatformRepository(session).persist_build(manifest, result, {"RELIANCE.NS": reliance_id})
    registry = ProviderRegistry()
    registry.register("quotes", "none", NoQuotes(), default=True)
    return TestClient(create_app(engine=engine, provider_registry=registry)), ids, manifest


def test_search_exposes_the_bse_cross_listing(api):
    client, ids, _ = api
    data = client.get("/api/v1/search?q=RELIANCE").json()["data"]
    reliance = next(r for r in data if r["instrument_id"] == ids["RELIANCE.NS"])
    assert reliance["bse_code"] == "500325"
    assert reliance["primary_exchange"] == "NSE"
    exchanges = {listing["exchange"] for listing in reliance["listings"]}
    assert exchanges == {"NSE", "BSE"}


def test_search_by_exact_bse_code_finds_the_cross_listed_company(api):
    client, ids, _ = api
    data = client.get("/api/v1/search?q=500325").json()["data"]
    assert data and data[0]["instrument_id"] == ids["RELIANCE.NS"]
    assert data[0]["matched_by"] == "exact_bse_code"


def test_search_active_only_excludes_delisted_companies(api):
    client, ids, _ = api
    all_results = client.get("/api/v1/search?q=GONE&limit=10").json()["data"]
    symbols_all = {r["symbol"] for r in all_results}
    assert "GONE" in symbols_all

    active_only = client.get("/api/v1/search?q=GONE&active_only=true").json()["data"]
    symbols_active = {r["symbol"] for r in active_only}
    assert "GONE" not in symbols_active


def test_search_include_sme_false_excludes_sme_companies(api):
    client, ids, _ = api
    default = client.get("/api/v1/search?q=SMEONLY").json()["data"]
    assert any(r["symbol"] == "SMEONLY" for r in default)

    excluded = client.get("/api/v1/search?q=SMEONLY&include_sme=false").json()["data"]
    assert not any(r["symbol"] == "SMEONLY" for r in excluded)


def test_search_exchange_param_scopes_to_listings_on_that_exchange(api):
    client, ids, _ = api
    bse_only = client.get("/api/v1/search?q=RELIANCE&exchange=BSE").json()["data"]
    assert bse_only and bse_only[0]["instrument_id"] == ids["RELIANCE.NS"]

    smeonly_on_bse = client.get("/api/v1/search?q=SMEONLY&exchange=BSE").json()["data"]
    assert smeonly_on_bse == []  # SMEONLY has no BSE listing at all


def test_company_summary_exposes_all_listings(api):
    client, ids, _ = api
    data = client.get(f"/api/v1/company/{ids['RELIANCE.NS']}/summary").json()["data"]
    assert data["bse_code"] == "500325"
    assert data["primary_exchange"] == "NSE"
    exchanges = {listing["exchange"] for listing in data["listings"]}
    assert exchanges == {"NSE", "BSE"}


def test_search_response_includes_v3_evidence_fields(api):
    client, ids, _ = api
    data = client.get("/api/v1/search?q=RELIANCE").json()["data"]
    reliance = next(r for r in data if r["instrument_id"] == ids["RELIANCE.NS"])
    assert reliance["ranking_policy_version"]
    assert reliance["match_reason"] == "Exact company symbol"
    assert reliance["matched_field"] == "symbol"
    assert reliance["active_listing"] is True
    assert reliance["primary_listing"] is True
    assert reliance["ranking_available"] is True  # RELIANCE.NS was screened in the api fixture


def test_search_meta_reports_universe_statistics(api):
    client, _, manifest = api
    data = client.get("/api/v1/search/meta").json()["data"]
    assert data["nse_count"] >= 3
    assert data["bse_count"] >= 1
    assert data["cross_listed_count"] >= 1
    assert data["research_count"] >= 1
    assert data["ranked_count"] >= 1
    assert data["sme_count"] >= 1
    assert data["search_ranking_policy_version"]
    assert data["search_schema_version"]
    assert data["generated_at"]
