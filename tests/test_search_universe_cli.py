"""search-universe-import CLI: an additive, optional operational step that
lets the dynamic API's /api/v1/search and /api/v1/instruments/lookup see the
wider NSE search universe once PostgreSQL is provisioned. It must never
touch index/ranking membership — only mbe.cli's existing instruments-import
(with --index-code) does that."""

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from mbe.cli import app as cli_app
from mbe.db.base import Base
from mbe.db.models import IndexMembershipRow, ProviderSymbolRow

runner = CliRunner()


def _snapshot(tmp_path):
    payload = {
        "source": "nse_listed_securities:combined", "source_url": "https://example/",
        "retrieved_at": "2026-08-01T00:00:00+00:00", "source_version": "sha256:test",
        "universe": "nse-search-universe", "n": 2,
        "records": [
            {
                "source_record_id": "INE002A01018", "company_name": "Reliance Industries Limited",
                "symbol": "RELIANCE", "exchange": "NSE", "exchange_segment": None, "series": "EQ",
                "isin": "INE002A01018", "bse_code": None, "industry": None, "sector": None,
                "listing_status": "active", "listing_date": None, "delisting_date": None,
                "is_sme": False, "security_type": "equity",
                "provider_symbols": {"yahoo": "RELIANCE.NS"}, "aliases": [],
            },
            {
                "source_record_id": "INE467B01029", "company_name": "Tata Consultancy Services Limited",
                "symbol": "TCS", "exchange": "NSE", "exchange_segment": None, "series": "EQ",
                "isin": "INE467B01029", "bse_code": None, "industry": None, "sector": None,
                "listing_status": "active", "listing_date": None, "delisting_date": None,
                "is_sme": False, "security_type": "equity",
                "provider_symbols": {"yahoo": "TCS.NS"}, "aliases": [],
            },
        ],
    }
    path = tmp_path / "nse-search-universe.json"
    path.write_text(json.dumps(payload))
    return path


def test_search_universe_import_populates_instruments_without_index_membership(tmp_path, monkeypatch):
    database = tmp_path / "platform.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("MBE_DATABASE_URL", f"sqlite:///{database}")

    result = runner.invoke(cli_app, [
        "search-universe-import", "--source", str(_snapshot(tmp_path)),
    ])
    assert result.exit_code == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["instruments_created"] == 2

    with Session(engine) as session:
        mappings = session.scalars(select(ProviderSymbolRow)).all()
        assert {m.provider_symbol for m in mappings} == {"RELIANCE.NS", "TCS.NS"}
        memberships = session.scalars(select(IndexMembershipRow)).all()
        assert memberships == []  # search-universe import never touches ranking/index membership


def test_search_universe_import_defaults_to_the_pinned_snapshot(tmp_path, monkeypatch):
    database = tmp_path / "platform.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("MBE_DATABASE_URL", f"sqlite:///{database}")

    result = runner.invoke(cli_app, ["search-universe-import"])
    assert result.exit_code == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["instruments_created"] > 2000
