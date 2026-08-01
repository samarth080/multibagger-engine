import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from mbe.db.base import Base
from mbe.db.models import IndexMembershipRow, ProviderSymbolRow
from mbe.instruments.importer import import_instruments
from mbe.models.instrument import stable_instrument_id


def test_pinned_master_exactly_covers_production_universe_and_ids_match_import():
    universe = json.loads(Path("universes/nifty-smallcap250.json").read_text())
    master = json.loads(
        Path("universes/nifty-smallcap250-instruments.json").read_text()
    )
    records = master["records"]
    tickers = {row["provider_symbols"]["yahoo"] for row in records}
    assert master["n"] == len(records) == len(tickers) == 250
    assert tickers == set(universe["tickers"])
    assert all(row["company_name"] and row["isin"] and row["industry"] for row in records)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        summary = import_instruments(
            session, records, source_code="pinned_master",
            source_version=master["source_version"], index_code="nifty-smallcap250",
        )
        assert summary.instruments_created == 250
        mappings = session.scalars(select(ProviderSymbolRow)).all()
        memberships = session.scalars(select(IndexMembershipRow)).all()
        assert len(memberships) == 250
        imported = {row.provider_symbol: row.instrument_id for row in mappings}

    for row in records:
        ticker = row["provider_symbols"]["yahoo"]
        expected = stable_instrument_id(
            exchange_code="NSE", symbol=row["symbol"], isin=row["isin"]
        )
        assert imported[ticker] == expected
