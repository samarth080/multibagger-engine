import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from mbe.db.base import Base
from mbe.db.models import ImportIssueRow, InstrumentAliasRow, InstrumentListingRow, InstrumentRow
from mbe.instruments.importer import import_instruments, parse_nifty_instrument_csv


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _record(**updates):
    row = {
        "source_record_id": "INE000A01018",
        "company_name": "Alpha Industries Limited",
        "symbol": "ALPHA",
        "exchange": "NSE",
        "series": "EQ",
        "isin": "INE000A01018",
        "industry": "Industrial Products",
        "sector": "Industrials",
        "listing_status": "active",
        "provider_symbols": {"yahoo": "ALPHA.NS"},
        "aliases": ["Alpha"],
    }
    row.update(updates)
    return row


def test_import_is_idempotent_and_reports_summary():
    with _session() as session:
        first = import_instruments(
            session, [_record()], source_code="nse_official", source_version="2026-08-01"
        )
        second = import_instruments(
            session, [_record()], source_code="nse_official", source_version="2026-08-01"
        )
        assert first.instruments_created == 1 and first.aliases_added == 1
        assert second.records_unchanged == 1
        assert session.scalar(select(func.count()).select_from(InstrumentRow)) == 1


def test_index_membership_sync_is_idempotent_and_closes_removed_members():
    with _session() as session:
        second_record = _record(
            source_record_id="INE000B01017", company_name="Beta Limited",
            symbol="BETA", isin="INE000B01017",
            provider_symbols={"yahoo": "BETA.NS"}, aliases=[],
        )
        first = import_instruments(
            session, [_record(), second_record], source_code="nse_official",
            index_code="smallcap250",
        )
        second = import_instruments(
            session, [_record()], source_code="nse_official", index_code="smallcap250"
        )
        assert first.index_memberships_added == 2
        assert second.index_memberships_added == 0
        assert second.index_memberships_closed == 1


def test_empty_source_fails_before_closing_memberships():
    with _session() as session:
        with pytest.raises(ValueError, match="source is empty"):
            import_instruments(
                session, [], source_code="nse_official", index_code="smallcap250"
            )


def test_symbol_and_name_change_preserve_identity_and_aliases():
    with _session() as session:
        import_instruments(session, [_record()], source_code="nse_official")
        instrument_id = session.scalar(select(InstrumentRow.instrument_id))
        changed = _record(
            company_name="Alpha Engineering Limited", symbol="ALPHAENG",
            provider_symbols={"yahoo": "ALPHAENG.NS"},
        )
        summary = import_instruments(session, [changed], source_code="nse_official")
        assert summary.symbols_changed == 1
        assert session.scalar(select(InstrumentRow.instrument_id)) == instrument_id
        aliases = session.scalars(select(InstrumentAliasRow)).all()
        assert {a.value for a in aliases} >= {"Alpha", "ALPHA", "Alpha Industries Limited"}
        current = session.scalar(select(InstrumentListingRow).where(
            InstrumentListingRow.valid_to.is_(None)
        ))
        assert current.symbol == "ALPHAENG"


def test_invalid_and_ambiguous_records_are_not_silently_discarded():
    with _session() as session:
        import_instruments(session, [_record()], source_code="nse_official")
        # Seed a deliberately inconsistent duplicate to exercise review behavior.
        base = session.scalar(select(InstrumentRow))
        session.add(InstrumentRow(
            instrument_id="duplicate-instrument", company_id=None, security_type="equity",
            country="IN", currency="INR", timezone="Asia/Kolkata", quality_status="review",
        ))
        session.add(InstrumentListingRow(
            instrument_id="duplicate-instrument", exchange_code="NSE", symbol="OTHER",
            isin="INE000A01018", status="active", is_primary=True, is_sme=False,
        ))
        session.commit()
        summary = import_instruments(session, [
            _record(provider_symbols={}),
            {"symbol": "", "exchange": "NSE"},
        ], source_code="nse_official")
        assert summary.ambiguous_records == 1
        assert summary.invalid_records == 1
        issues = session.scalars(select(ImportIssueRow)).all()
        assert {i.issue_type for i in issues} == {"ambiguous_identity", "invalid"}


def test_conflicting_isin_never_hijacks_an_existing_provider_symbol():
    with _session() as session:
        import_instruments(session, [_record()], source_code="nse_official")
        conflict = _record(
            source_record_id="INE999Z01019", company_name="Different Company Limited",
            isin="INE999Z01019", symbol="DIFFERENT",
            provider_symbols={"yahoo": "ALPHA.NS"},
        )
        summary = import_instruments(session, [conflict], source_code="nse_official")
        assert summary.ambiguous_records == 1
        issue = session.scalar(select(ImportIssueRow).where(
            ImportIssueRow.issue_type == "conflicting_identity"
        ))
        assert issue and "INE999Z01019" in issue.message
        assert session.scalar(select(func.count()).select_from(InstrumentRow)) == 1


def test_dry_run_rolls_back_every_write():
    with _session() as session:
        summary = import_instruments(
            session, [_record()], source_code="nse_official", dry_run=True
        )
        assert summary.dry_run and summary.instruments_created == 1
        assert session.scalar(select(func.count()).select_from(InstrumentRow)) == 0


def test_official_csv_schema_is_validated_and_retained():
    csv_text = (
        "Company Name,Industry,Symbol,Series,ISIN Code\n"
        "Alpha Industries Limited,Industrial Products,ALPHA,EQ,INE000A01018\n"
    )
    rows = parse_nifty_instrument_csv(csv_text)
    assert rows[0]["company_name"] == "Alpha Industries Limited"
    assert rows[0]["provider_symbols"] == {"yahoo": "ALPHA.NS"}
    with pytest.raises(ValueError, match="missing columns"):
        parse_nifty_instrument_csv("Symbol\nALPHA\n")


def test_instrument_master_provider_reports_source_version_and_failure():
    from mbe.data.instrument_master import NiftyIndexInstrumentProvider
    from mbe.data.provider import ProviderError

    csv_text = (
        "Company Name,Industry,Symbol,Series,ISIN Code\n"
        "Alpha Industries Limited,Industrial Products,ALPHA,EQ,INE000A01018\n"
    )
    provider = NiftyIndexInstrumentProvider(fetcher=lambda _: csv_text)
    snapshot = provider.fetch_instruments()
    assert snapshot.source_version.startswith("sha256:")
    assert snapshot.records[0].isin == "INE000A01018"

    def failed(_):
        raise TimeoutError("source unavailable")

    with pytest.raises(ProviderError, match="instrument-master fetch failed"):
        NiftyIndexInstrumentProvider(fetcher=failed).fetch_instruments()
