"""Phase 10B operational CLI commands: bse-search-universe-import,
search-quality-evaluate, search-inspect. All must run offline (no live
network) and exit nonzero on material failure.
"""

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from mbe.cli import app as cli_app
from mbe.db.base import Base
from mbe.db.models import IndexMembershipRow, InstrumentListingRow, ProviderSymbolRow

runner = CliRunner()


def _bse_snapshot(tmp_path):
    payload = {
        "source": "curated_starter_fixture", "source_url": "https://example/",
        "retrieved_at": "2026-08-01T00:00:00+00:00", "source_version": "curated:test",
        "universe": "bse-search-universe", "coverage_status": "curated_starter_fixture_pending_live_verification",
        "n": 1, "records": [{
            "source_record_id": "INE002A01018", "company_name": "Reliance Industries Ltd.",
            "symbol": "RELIANCE", "exchange": "BSE", "exchange_segment": None, "series": "A",
            "isin": "INE002A01018", "bse_code": "500325", "industry": "Refineries",
            "listing_status": "active", "is_sme": False,
        }],
    }
    path = tmp_path / "bse-search-universe.json"
    path.write_text(json.dumps(payload))
    return path


def _nse_snapshot(tmp_path):
    payload = {
        "records": [{
            "source_record_id": "INE002A01018", "company_name": "Reliance Industries Limited",
            "symbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018",
            "listing_status": "active", "provider_symbols": {"yahoo": "RELIANCE.NS"},
        }],
    }
    path = tmp_path / "nse-search-universe.json"
    path.write_text(json.dumps(payload))
    return path


def test_bse_search_universe_import_cross_links_without_index_membership(tmp_path, monkeypatch):
    database = tmp_path / "platform.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("MBE_DATABASE_URL", f"sqlite:///{database}")

    from mbe.instruments.importer import import_instruments
    with Session(engine) as session:
        import_instruments(session, [{
            "company_name": "Reliance Industries Limited", "symbol": "RELIANCE", "exchange": "NSE",
            "isin": "INE002A01018", "listing_status": "active",
            "provider_symbols": {"yahoo": "RELIANCE.NS"},
        }], source_code="nse_test", source_version="v1")

    result = runner.invoke(cli_app, [
        "bse-search-universe-import", "--source", str(_bse_snapshot(tmp_path)),
    ])
    assert result.exit_code == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["cross_listings_added"] == 1
    assert summary["coverage_status"] == "curated_starter_fixture_pending_live_verification"

    with Session(engine) as session:
        listings = session.scalars(select(InstrumentListingRow)).all()
        assert {l.exchange_code for l in listings} == {"NSE", "BSE"}
        memberships = session.scalars(select(IndexMembershipRow)).all()
        assert memberships == []


def test_search_quality_evaluate_runs_offline_against_the_real_pinned_universe():
    result = runner.invoke(cli_app, ["search-quality-evaluate"])
    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["total"] >= 10
    assert report["top1_accuracy"] == 1.0
    assert report["false_positive_count"] == 0


def test_search_quality_evaluate_exits_nonzero_on_regression(tmp_path):
    # Point at an empty/irrelevant search universe so the evaluation set
    # cannot possibly pass — the command must fail loudly, not silently.
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"records": [{
        "source_record_id": "INE999Z01019", "company_name": "Irrelevant Ltd.",
        "symbol": "IRRELEVANT", "exchange": "NSE", "isin": "INE999Z01019",
        "listing_status": "active", "provider_symbols": {},
    }]}))
    result = runner.invoke(cli_app, [
        "search-quality-evaluate", "--search-universe", str(empty),
        "--instruments", str(tmp_path / "missing.json"),
        "--screener", str(tmp_path / "missing2.json"),
        "--bse-universe", str(tmp_path / "missing3.json"),
    ])
    assert result.exit_code == 1


def test_search_inspect_returns_ranked_evidence_for_a_real_query():
    result = runner.invoke(cli_app, ["search-inspect", "HDFC", "--limit", "3"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert rows[0]["symbol"] == "HDFCBANK"
    assert rows[0]["matched_by"]


def test_search_inspect_respects_exchange_filter():
    result = runner.invoke(cli_app, ["search-inspect", "RELIANCE", "--exchange", "BSE", "--limit", "5"])
    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert rows and rows[0]["bse_code"] == "500325"
