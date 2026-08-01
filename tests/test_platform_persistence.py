from datetime import datetime, timezone

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from mbe.db.models import ModelBuildRow, ScoreComponentRow, ScoreSnapshotRow
from mbe.db.repository import PlatformRepository
from mbe.instruments.importer import import_instruments
from mbe.pipeline import screen
from mbe.storage import RunStore
from mbe.versioning import build_manifest
from tests.test_pipeline import StubProvider


def _migrated_engine(tmp_path):
    path = tmp_path / "platform.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(config, "head")
    return create_engine(f"sqlite:///{path}")


def _records():
    return [{
        "company_name": f"{symbol} Limited", "symbol": symbol,
        "exchange": "NSE", "isin": isin, "listing_status": "active",
        "provider_symbols": {"yahoo": f"{symbol}.NS"},
    } for symbol, isin in (
        ("GOOD", "INE000A01018"), ("ALSO", "INE000B01017"),
    )]


def test_alembic_upgrade_and_rollback(tmp_path):
    engine = _migrated_engine(tmp_path)
    tables = set(inspect(engine).get_table_names())
    assert {"instruments", "provider_symbols", "model_builds", "score_snapshots"} <= tables
    assert inspect(engine).get_pk_constraint("instruments")["constrained_columns"] == ["instrument_id"]

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", str(engine.url))
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}


def test_model_build_and_normalized_score_history_persistence(tmp_path):
    engine = _migrated_engine(tmp_path)
    with Session(engine) as session:
        import_instruments(session, _records(), source_code="test_master", source_version="v1")
        from mbe.db.models import ProviderSymbolRow
        mappings = session.scalars(select(ProviderSymbolRow)).all()
        instrument_ids = {m.provider_symbol: m.instrument_id for m in mappings}

    result = screen(["GOOD.NS", "ALSO.NS"], StubProvider())
    built_at = datetime.now(timezone.utc)
    manifest = build_manifest(
        universe_name="unit", tickers=["GOOD.NS", "ALSO.NS"], built_at=built_at,
        source_date="v1", attempted=2, scored=2, failed=0,
    )
    with Session(engine) as session:
        PlatformRepository(session).persist_build(manifest, result, instrument_ids)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ModelBuildRow)) == 1
        assert session.scalar(select(func.count()).select_from(ScoreSnapshotRow)) == 2
        assert session.scalar(select(func.count()).select_from(ScoreComponentRow)) == 16
        rows, total, build = PlatformRepository(session).rankings(min_score=0)
        assert total == 2 and build.build_id == manifest.build_id
        assert rows[0]["rank"] == 1


def test_manifest_hash_is_reproducible_and_sensitive_to_configuration():
    from mbe.models.instrument import BuildManifest

    one = BuildManifest.configuration_hash({"b": 2, "a": [1, 2]})
    two = BuildManifest.configuration_hash({"a": [1, 2], "b": 2})
    changed = BuildManifest.configuration_hash({"a": [1, 3], "b": 2})
    assert one == two and one != changed


def test_legacy_duckdb_is_migrated_additively_and_history_remains_readable(tmp_path):
    import duckdb

    path = tmp_path / "legacy.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, as_of DATE, universe TEXT, created_at TIMESTAMP)")
    connection.execute("CREATE TABLE results (run_id TEXT, ticker TEXT, investment DOUBLE, multibagger DOUBLE, confidence DOUBLE, risk_score DOUBLE, trend_state TEXT, price DOUBLE, market_cap DOUBLE, verdict TEXT, pillars_json TEXT, metrics_json TEXT)")
    connection.execute("INSERT INTO runs VALUES ('old', DATE '2025-01-01', 'legacy', TIMESTAMP '2025-01-01')")
    connection.execute("INSERT INTO results VALUES ('old', 'OLD.NS', 50, 55, .8, 20, 'up', 10, 100, 'Watch', '{}', '{}')")
    connection.close()

    store = RunStore(path)
    assert store.history("OLD.NS")[0]["universe"] == "legacy"
    connection = duckdb.connect(str(path))
    columns = {row[1] for row in connection.execute("PRAGMA table_info('results')").fetchall()}
    assert {"instrument_id", "build_id"} <= columns
    assert connection.execute("SELECT version FROM schema_migrations").fetchone()[0] == 1
    connection.close()
