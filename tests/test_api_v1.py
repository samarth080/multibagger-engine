from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from mbe.api.app import create_app
from mbe.data.market import NormalizedQuote
from mbe.data.registry import ProviderRegistry
from mbe.db.base import Base
from mbe.db.models import FinancialDatasetBuildRow, InstrumentRow, ProviderSymbolRow
from mbe.db.repository import PlatformRepository
from mbe.instruments.importer import import_instruments
from mbe.models.instrument import FreshnessState, QualityStatus
from mbe.pipeline import screen
from mbe.financials.projection import financial_build, project_history
from mbe.financials.repository import persist_projection_build
from mbe.financials.nse_official import parse_discovery_entry
from mbe.financials.official_domain import AttachmentFormat, FetchedDocument
from mbe.financials.official_importer import ingest_official_filings
from mbe.financials.official_repository import persist_reconciliation
from mbe.financials.reconciliation import reconcile_values
from mbe.financials.domain import ConsolidationBasis
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
        ("Also Foods Limited", "ALSO", "INE000B01017", "Consumer", "Foods", []),
    )]
    with Session(engine) as session:
        import_instruments(session, records, source_code="test_master", source_version="v1")
        mappings = session.scalars(select(ProviderSymbolRow)).all()
        ids = {m.provider_symbol: m.instrument_id for m in mappings}
    result = screen(["GOOD.NS", "ALSO.NS"], StubProvider())
    manifest = build_manifest(
        universe_name="unit", tickers=["GOOD.NS", "ALSO.NS"],
        built_at=datetime.now(timezone.utc), source_date="v1",
        attempted=2, scored=2, failed=0,
    )
    with Session(engine) as session:
        PlatformRepository(session).persist_build(manifest, result, ids)
        projections = [project_history(bundle.fin, instrument_id=ids[bundle.card.ticker], cutoff=manifest.data_cutoff) for bundle in result.ranked]
        persist_projection_build(session, financial_build(projections, cutoff=manifest.data_cutoff), projections)
    registry = ProviderRegistry()
    registry.register("quotes", "mock", MockQuotes(), default=True)
    return TestClient(create_app(engine=engine, provider_registry=registry)), ids, manifest


def test_health_status_and_security_headers(api):
    client, _, _ = api
    health = client.get("/api/v1/health", headers={"X-Request-ID": "test-request"})
    assert health.status_code == 200
    assert health.json()["data"]["database"] == "connected"
    assert health.json()["request_id"] == "test-request"
    assert health.headers["x-content-type-options"] == "nosniff"
    status = client.get("/api/v1/status")
    assert status.json()["data"]["instrument_counts"] == {"total": 2, "active": 2}
    assert status.json()["data"]["latest_model_build"] is not None


def test_instrument_pagination_filter_search_and_lookup(api):
    client, ids, _ = api
    response = client.get("/api/v1/instruments?page_size=1&sort=symbol")
    body = response.json()
    assert response.status_code == 200
    assert body["meta"]["total"] == 2 and len(body["data"]) == 1
    assert body["meta"]["total_pages"] == 2
    filtered = client.get("/api/v1/instruments?sector=Industrials&search=Good")
    assert [item["symbol"] for item in filtered.json()["data"]] == ["GOOD"]
    lookup = client.get("/api/v1/instruments/lookup?q=GEL").json()["data"]
    assert lookup[0]["matched_by"] == "exact_common_name"
    detail = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}")
    assert detail.json()["data"]["provider_mappings"][0]["provider_symbol"] == "GOOD.NS"


def test_rankings_filter_detail_and_unknown(api):
    client, ids, manifest = api
    response = client.get("/api/v1/rankings?page_size=1&sort=-score&min_score=0")
    assert response.status_code == 200
    assert response.json()["meta"]["build"]["build_id"] == manifest.build_id
    assert len(response.json()["data"]) == 1
    row = response.json()["data"][0]
    assert row["technical_trend"]
    assert len(row["components"]) == 8
    filtered = client.get("/api/v1/rankings", params={
        "search": row["symbol"],
        "technical_trend": row["technical_trend"],
        "min_rank": row["rank"],
        "max_rank": row["rank"],
        "sort": "-confidence",
    })
    assert filtered.status_code == 200
    assert [item["instrument_id"] for item in filtered.json()["data"]] == [
        row["instrument_id"]
    ]
    detail = client.get(f"/api/v1/rankings/{ids['GOOD.NS']}")
    assert detail.status_code == 200
    assert len(detail.json()["data"]["components"]) == 8
    unknown = client.get("/api/v1/rankings/not-an-id")
    assert unknown.status_code == 404
    assert unknown.json()["errors"][0]["code"] == "ranking_not_found"


def test_validation_errors_and_quote_limits_are_stable(api):
    client, ids, _ = api
    invalid = client.get("/api/v1/instruments?page_size=101")
    assert invalid.status_code == 422
    assert invalid.json()["errors"][0]["code"] == "validation_error"
    too_many = ",".join(f"id-{i}" for i in range(31))
    limited = client.get("/api/v1/quotes", params={"instrument_ids": too_many})
    assert limited.status_code == 429
    assert limited.json()["errors"][0]["code"] == "quote_batch_limit"
    empty = client.get("/api/v1/quotes", params={"instrument_ids": ","})
    assert empty.status_code == 400
    assert empty.json()["errors"][0]["code"] == "empty_quote_request"

    quote = client.get("/api/v1/quotes", params={
        "instrument_ids": f"{ids['GOOD.NS']},missing-id"
    })
    body = quote.json()
    assert quote.status_code == 200
    assert body["data"]["quotes"][0]["instrument_id"] == ids["GOOD.NS"]
    assert body["errors"][0]["code"] == "provider_mapping_missing"
    assert "secret" not in quote.text.lower()


def test_quotes_endpoint_deduplicates_repeated_instrument_ids_in_one_request(api):
    client, ids, _ = api
    good_id = ids["GOOD.NS"]
    response = client.get("/api/v1/quotes", params={"instrument_ids": f"{good_id},{good_id},{good_id}"})
    assert response.status_code == 200
    assert len(response.json()["data"]["quotes"]) == 1


def test_quotes_endpoint_sets_a_short_public_cache_header(api):
    client, ids, _ = api
    response = client.get("/api/v1/quotes", params={"instrument_ids": ids["GOOD.NS"]})
    assert response.headers["cache-control"] == "public, max-age=60"


def test_company_summary_for_a_delisted_unmapped_instrument_never_fabricates_a_quote():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        import_instruments(session, [{
            "company_name": "Delisted Shell Limited", "symbol": "DELIST", "exchange": "NSE",
            "isin": "INE999Z01019", "sector": None, "industry": None,
            "listing_status": "delisted", "provider_symbols": {}, "aliases": [],
        }], source_code="test_master", source_version="v1")
        instrument_id = session.scalars(select(InstrumentRow.instrument_id)).one()
    client = TestClient(create_app(engine=engine, provider_registry=ProviderRegistry()))
    response = client.get(f"/api/v1/company/{instrument_id}/summary")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["listing_status"] == "delisted"
    assert body["quote"] is None
    assert body["research_available"] is False


def test_methodology_is_machine_readable_and_database_absence_is_safe():
    client = TestClient(create_app())
    health = client.get("/api/v1/health")
    assert health.status_code == 200 and health.json()["data"]["database"] == "not_configured"
    status = client.get("/api/v1/status")
    assert status.status_code == 503
    assert status.json()["errors"][0]["code"] == "database_not_configured"
    methodology = client.get("/api/v1/methodology")
    assert methodology.status_code == 200
    assert "multibagger" in methodology.json()["data"]["components"]


def test_coverage_route_returns_bounded_503_without_configured_database():
    client = TestClient(create_app())
    response = client.get("/api/v1/company/some-id/coverage")
    assert response.status_code == 503
    assert response.json()["errors"][0]["code"] == "database_not_configured"


def test_screener_metadata_query_and_safe_errors(api):
    client, _, manifest = api
    metadata = client.get("/api/v1/screener/fields")
    assert metadata.status_code == 200
    assert metadata.json()["data"]["build"]["build_id"] == manifest.build_id
    assert any(field["field_id"] == "quality_score" for field in metadata.json()["data"]["fields"])

    query = {
        "schema_version": "1.0",
        "conditions": [{"condition_id": "score", "field_id": "multibagger_score", "operator": "gte", "value": 0}],
        "sorts": [{"field_id": "rank", "direction": "asc"}],
        "columns": ["company", "nse_symbol", "rank", "quality_score"],
        "page": 1,
        "page_size": 1,
    }
    response = client.post("/api/v1/screener/query", json=query)
    body = response.json()
    assert response.status_code == 200
    assert body["data"]["pagination"]["total"] == 2
    assert body["data"]["mode"] == "dynamic"
    assert body["data"]["rows"][0]["matched_conditions"][0]["actual_value"] is not None

    invalid = client.post("/api/v1/screener/query", json={
        **query,
        "conditions": [{"condition_id": "bad", "field_id": "risk_score", "operator": "contains", "value": "x"}],
    })
    assert invalid.status_code == 422
    assert invalid.json()["errors"][0]["code"] == "unsupported_operator"
    assert "sql" not in invalid.text.lower()

    oversized = client.post(
        "/api/v1/screener/query", content=" " * 65_537,
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["errors"][0]["code"] == "request_too_large"


def test_financial_coverage_summary_and_screener_filter(api):
    client, ids, _ = api
    metrics = client.get("/api/v1/financials/metrics")
    assert metrics.status_code == 200
    assert any(item["metric_id"] == "revenue_cagr_3y" for item in metrics.json()["data"]["metrics"])
    coverage = client.get("/api/v1/financials/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["data"]["companies_completed"] == 2
    summary = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/financials")
    assert summary.status_code == 200
    assert summary.json()["data"]["derived_metrics"]
    invalid = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/financials?metrics=secret_metric")
    assert invalid.status_code == 422
    assert invalid.json()["errors"][0]["code"] == "unknown_financial_metric"
    screen = client.post("/api/v1/screener/query", json={
        "conditions": [{"condition_id": "growth", "field_id": "revenue_cagr_3y", "operator": "is_available"}],
        "sorts": [{"field_id": "revenue_cagr_3y", "direction": "desc"}],
        "columns": ["company", "revenue_cagr_3y", "roce_3y"], "page_size": 100,
    })
    assert screen.status_code == 200
    assert screen.json()["data"]["pagination"]["total"] == 2
    assert screen.json()["data"]["financial_dataset_build"] is not None


def test_company_research_history_and_peer_endpoints_share_the_canonical_contract(api):
    client, ids, manifest = api
    response = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/research")
    assert response.status_code == 200
    research = response.json()["data"]
    assert research["schema_version"] == "1.0"
    assert research["identity"]["instrument_id"] == ids["GOOD.NS"]
    assert research["identity"]["canonical_url"] == f"/company/{ids['GOOD.NS']}.html"
    assert research["ranking"]["model_build_id"] == manifest.build_id
    assert research["financials"]["source_label"] == "Yahoo compatibility fallback"
    assert research["financials"]["official_tier_a_status"] == "unavailable"
    assert "raw_metadata" not in response.text and "/Users/" not in response.text

    history = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/score-history?limit=1")
    assert history.status_code == 200 and history.json()["meta"]["returned"] == 1
    assert history.json()["data"]["points"][0]["build_id"] == manifest.build_id

    peers = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/peers?limit=4")
    assert peers.status_code == 200
    assert peers.json()["meta"]["policy_version"] == "2026-08-01.1"
    assert all(item["instrument_id"] != ids["GOOD.NS"] for item in peers.json()["data"])

    missing = client.get("/api/v1/instruments/not-an-id/research")
    assert missing.status_code == 404 and missing.json()["errors"][0]["code"] == "research_not_found"


def test_static_and_sqlite_dynamic_research_core_sections_are_equivalent(api):
    from mbe.publish import build_data
    from mbe.research.static import build_static_research

    client, ids, manifest = api
    result = screen(["GOOD.NS", "ALSO.NS"], StubProvider())
    canonical = {
        "GOOD.NS": {"company_name": "Good Engineering Limited", "symbol": "GOOD", "exchange": "NSE",
                    "isin": "INE000A01018", "sector": "Industrials", "industry": "Engineering",
                    "listing_status": "active", "provider_symbols": {"yahoo": "GOOD.NS"}},
        "ALSO.NS": {"company_name": "Also Foods Limited", "symbol": "ALSO", "exchange": "NSE",
                    "isin": "INE000B01017", "sector": "Consumer", "industry": "Foods",
                    "listing_status": "active", "provider_symbols": {"yahoo": "ALSO.NS"}},
    }
    data = build_data(
        result, {}, [], built_at=manifest.built_at, manifest=manifest,
        instrument_ids=ids, canonical_records=canonical,
    )
    static = build_static_research(data, result)[ids["GOOD.NS"]]
    dynamic = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/research").json()["data"]
    assert static["identity"] == dynamic["identity"]
    for field in ("rank", "multibagger_score", "investment_score", "confidence", "risk_score", "technical_trend", "model_build_id"):
        assert static["ranking"][field] == dynamic["ranking"][field]
    assert [item["code"] for item in static["explanations"]] == [item["code"] for item in dynamic["explanations"]]
    assert static["financials"]["revenue_cagr_3y"] == pytest.approx(dynamic["financials"]["revenue_cagr_3y"], abs=1e-11)
    assert static["financials"]["roce_3y"] == pytest.approx(dynamic["financials"]["roce_3y"], abs=1e-11)
    assert static["financials"]["source_label"] == dynamic["financials"]["source_label"]
    assert static["technical"] == dynamic["technical"]
    assert static["peers"] == dynamic["peers"]
    assert static["history"]["points"] == dynamic["history"]["points"]


def test_official_filing_and_reconciliation_endpoints_are_bounded_and_safe(api):
    client, ids, manifest = api
    fixture_dir = Path(__file__).parent / "fixtures" / "nse-official"
    metadata = json.loads((fixture_dir / "kfintech-2024-metadata.json").read_text())
    metadata.update({
        "companyName": "Good Engineering Limited",
        "symbol": "GOOD",
        "isin": "INE000A01018",
        "seqNumber": "fixture-good-1",
    })
    discovery = parse_discovery_entry(
        metadata,
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source_url="https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=GOOD&period=Annual",
    )
    xml = (fixture_dir / "kfintech-2024-results.xml").read_bytes()
    document = FetchedDocument(
        source_url=discovery.attachments[0].source_url,
        filename=discovery.attachments[0].filename,
        detected_content_type="application/xml",
        attachment_format=AttachmentFormat.XBRL_XML,
        content_length=len(xml),
        sha256=hashlib.sha256(xml).hexdigest(),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        cache_hit=False,
        content=xml,
    )
    with Session(client.app.state.engine) as session:
        instrument = session.get(InstrumentRow, ids["GOOD.NS"])
        ingest_official_filings(
            session,
            [(discovery, instrument.company_id, instrument.instrument_id)],
            document_loader=lambda _: document,
        )
        build = session.scalar(select(FinancialDatasetBuildRow).order_by(FinancialDatasetBuildRow.built_at.desc()))
        reconciliation = reconcile_values(
            instrument_id=instrument.instrument_id,
            metric_id="revenue",
            official_period=discovery.period,
            compatibility_period=discovery.period,
            official_basis=ConsolidationBasis.CONSOLIDATED,
            compatibility_basis=ConsolidationBasis.UNKNOWN,
            official_value=Decimal("8375330000"),
            compatibility_value=Decimal("8375330000"),
            official_unit="INR",
            compatibility_unit="INR",
        )
        persist_reconciliation(
            session,
            reconciliation,
            financial_dataset_build_id=build.financial_dataset_build_id,
            source_cutoff=manifest.data_cutoff,
        )
        session.commit()

    listing = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/filings?limit=1")
    assert listing.status_code == 200 and len(listing.json()["data"]) == 1
    filing = listing.json()["data"][0]
    assert filing["source"] == "nse_financial_results"
    assert filing["basis"] == "consolidated"
    assert filing["attachments"][0]["parse_status"] == "parsed"
    detail = client.get(f"/api/v1/filings/{filing['filing_id']}")
    assert detail.status_code == 200
    assert "data/official-filings" not in detail.text and "/Users/" not in detail.text
    reconciled = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/financials/reconciliation")
    assert reconciled.status_code == 200
    assert reconciled.json()["data"][0]["status"] == "unresolved"
    assert "raw_metadata" not in listing.text and "cache" not in listing.text.lower()
    invalid = client.get(f"/api/v1/instruments/{ids['GOOD.NS']}/filings?limit=101")
    assert invalid.status_code == 422
    missing = client.get("/api/v1/filings/not-a-filing")
    assert missing.status_code == 404
