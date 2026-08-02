"""New additive dynamic routes: GET /api/v1/search and
GET /api/v1/company/{id}/summary. These exist for when PostgreSQL is
provisioned (search-universe-import CLI has populated the wider instrument
master); today's production static build is covered separately by
tests/test_search_static_build.py and tests/test_phase10a_regression.py.

Existing /api/v1/instruments, /api/v1/instruments/lookup and
/api/v1/rankings routes are unchanged — see tests/test_api_v1.py.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mbe.api.app import create_app
from mbe.data.market import NormalizedQuote
from mbe.data.registry import ProviderRegistry
from mbe.db.base import Base
from mbe.db.models import ProviderSymbolRow
from mbe.db.repository import PlatformRepository
from mbe.instruments.importer import import_instruments
from mbe.models.instrument import FreshnessState, QualityStatus
from mbe.pipeline import screen
from mbe.versioning import build_manifest
from tests.test_pipeline import StubProvider


class MockQuotes:
    name = "mock"

    def health(self):
        return {"provider": "mock", "status": "ok"}

    def get_quotes(self, mappings):
        return [NormalizedQuote(
            instrument_id=item.instrument_id, provider="mock",
            provider_symbol=item.provider_symbol, last_price=123.45,
            market_status="closed", freshness_state=FreshnessState.FRESH,
            quality_status=QualityStatus.VALID,
        ) for item in mappings]


@pytest.fixture()
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    records = [{
        "company_name": name, "symbol": symbol, "exchange": "NSE",
        "isin": isin, "sector": sector, "industry": industry,
        "listing_status": "active", "provider_symbols": {"yahoo": f"{symbol}.NS"},
        "aliases": aliases,
    } for name, symbol, isin, sector, industry, aliases in (
        ("Good Engineering Limited", "GOOD", "INE000A01018", "Industrials", "Engineering", ["GEL"]),
        # Imported into the instrument master (the wider search universe) but
        # never scored — the exact Phase 10A scenario (Reliance-shaped).
        ("Reliance Industries Limited", "RELIANCE", "INE002A01018", None, None, []),
    )]
    with Session(engine) as session:
        import_instruments(session, records, source_code="test_master", source_version="v1")
        mappings = session.scalars(select(ProviderSymbolRow)).all()
        ids = {m.provider_symbol: m.instrument_id for m in mappings}
    result = screen(["GOOD.NS"], StubProvider())
    manifest = build_manifest(
        universe_name="unit", tickers=["GOOD.NS"],
        built_at=datetime.now(timezone.utc), source_date="v1",
        attempted=1, scored=1, failed=0,
    )
    with Session(engine) as session:
        PlatformRepository(session).persist_build(manifest, result, {"GOOD.NS": ids["GOOD.NS"]})
    registry = ProviderRegistry()
    registry.register("quotes", "mock", MockQuotes(), default=True)
    return TestClient(create_app(engine=engine, provider_registry=registry)), ids, manifest


def test_search_returns_modeled_and_unmodeled_results_with_honest_typing(api):
    client, ids, _ = api

    modeled = client.get("/api/v1/search?q=Good").json()["data"]
    assert modeled[0]["symbol"] == "GOOD"
    assert modeled[0]["result_type"] == "modeled"
    assert modeled[0]["research_available"] is True
    assert modeled[0]["rank"] == 1
    assert modeled[0]["multibagger_score"] is not None

    unmodeled = client.get("/api/v1/search?q=Reliance").json()["data"]
    assert unmodeled[0]["symbol"] == "RELIANCE"
    assert unmodeled[0]["result_type"] == "known"
    assert unmodeled[0]["research_available"] is False
    assert unmodeled[0]["rank"] is None
    assert unmodeled[0]["multibagger_score"] is None
    assert unmodeled[0]["report_url"] == f"/company/{ids['RELIANCE.NS']}.html"


def test_search_preserves_entity_disambiguation_for_short_aliases(api):
    client, _, _ = api
    lookup = client.get("/api/v1/search?q=GEL").json()["data"]
    assert lookup[0]["symbol"] == "GOOD"
    assert lookup[0]["matched_by"] == "exact_common_name"


def test_search_query_too_short_returns_empty_not_an_error(api):
    client, _, _ = api
    response = client.get("/api/v1/search?q=g")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_search_respects_limit_and_is_bounded(api):
    client, _, _ = api
    response = client.get("/api/v1/search?q=e&limit=1")
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 1


def test_company_summary_for_modeled_instrument_has_no_ranking_badge(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['GOOD.NS']}/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_available"] is True
    assert data["result_type"] == "modeled"
    assert data["rank"] == 1
    assert data["ranking_universe_badge"] is None
    assert data["scoring_disclosure"] is None


def test_company_summary_for_unmodeled_instrument_shows_badges_no_fake_score(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['RELIANCE.NS']}/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["display_name"] == "Reliance Industries Limited"
    assert data["research_available"] is False
    assert data["result_type"] == "known"
    assert data["rank"] is None
    assert data["multibagger_score"] is None
    assert data["ranking_universe_badge"] == (
        "Not currently included in the Multibagger ranking universe."
    )
    assert data["scoring_disclosure"] == (
        "This company has not yet been evaluated by the Multibagger scoring model."
    )
    assert data["quote"]["last_price"] == 123.45


def test_company_summary_unknown_instrument_is_404(api):
    client, _, _ = api
    response = client.get("/api/v1/company/not-a-real-id/summary")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "company_not_found"


def test_coverage_route_returns_level_3_for_a_modeled_instrument(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['GOOD.NS']}/coverage")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_coverage_level"] == 3
    assert data["research_eligible"] is True
    assert "score" not in data


def test_coverage_route_returns_level_1_for_an_unmodeled_instrument(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['RELIANCE.NS']}/coverage")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_coverage_level"] == 1
    assert data["research_eligible"] is False
    assert "not_in_model_universe" in data["research_eligibility_reasons"]


def test_coverage_route_unknown_instrument_is_404(api):
    client, _, _ = api
    response = client.get("/api/v1/company/not-a-real-id/coverage")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "company_not_found"


def test_summary_route_gains_additive_coverage_fields(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['RELIANCE.NS']}/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_coverage_level"] == 1
    assert data["coverage_label"] == "Level 1 — Market Coverage"
    assert data["research_eligible"] is False
