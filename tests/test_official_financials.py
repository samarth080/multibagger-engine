from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import urllib.error

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from mbe.data.provider import ProviderError
from mbe.db.base import Base
from mbe.db.models import (
    CompanyRow,
    FinancialFactRow,
    FinancialFilingRow,
    InstrumentRow,
    OfficialFilingAttachmentRow,
    OfficialFilingSourceRow,
)
from mbe.cli import app as cli_app
from mbe.instruments.importer import import_instruments
from mbe.financials.document_fetch import (
    FetchPolicy,
    HttpResult,
    SafeDocumentFetcher,
    sanitize_filename,
    validate_official_url,
)
from mbe.financials.domain import ConsolidationBasis
from mbe.financials.domain import FilingInput, FinancialPeriod, SourceFact
from mbe.financials.importer import import_filings
from mbe.financials.nse_official import parse_discovery_entry
from mbe.financials.official_domain import AttachmentFormat, FetchedDocument, ReconciliationStatus
from mbe.financials.official_importer import ingest_official_filings
from mbe.financials.official_metrics import derive_official_public_metrics
from mbe.financials.official_repository import official_fact_view
from mbe.financials.parsers import OfficialParserRegistry, parse_nse_results_xbrl
from mbe.financials.reconciliation import reconcile_values


FIXTURES = Path(__file__).parent / "fixtures" / "nse-official"


def _metadata(**changes):
    value = json.loads((FIXTURES / "kfintech-2024-metadata.json").read_text())
    value.update(changes)
    return value


def _discovery(**changes):
    return parse_discovery_entry(
        _metadata(**changes),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source_url="https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=KFINTECH&period=Annual",
    )


def _document(content: bytes | None = None, *, cache_hit=False):
    content = content or (FIXTURES / "kfintech-2024-results.xml").read_bytes()
    return FetchedDocument(
        source_url="https://nsearchives.nseindia.com/corporate/xbrl/INDAS_104961_1111394_29042024090825.xml",
        filename="INDAS_104961_1111394_29042024090825.xml",
        detected_content_type="application/xml",
        attachment_format=AttachmentFormat.XBRL_XML,
        content_length=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        cache_hit=cache_hit,
        content=content,
    )


def _store():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(CompanyRow(company_id="company", display_name="Kfin Technologies Limited", country="IN"))
        session.add(InstrumentRow(
            instrument_id="instrument",
            company_id="company",
            security_type="equity",
            country="IN",
            currency="INR",
            timezone="Asia/Kolkata",
            quality_status="valid",
        ))
        session.commit()
    return engine


def test_discovery_preserves_official_identity_period_basis_and_attachment():
    filing = _discovery()
    assert filing.source_filing_id == "1169770"
    assert filing.nse_symbol == "KFINTECH"
    assert filing.isin == "INE138Y01010"
    assert filing.period.period_start == date(2023, 4, 1)
    assert filing.period.period_end == date(2024, 3, 31)
    assert filing.period.period_type.value == "annual"
    assert filing.basis_hint == ConsolidationBasis.CONSOLIDATED
    assert filing.publication_timestamp == datetime(2024, 4, 29, 15, 38, 26, tzinfo=timezone.utc)
    assert filing.attachments[0].format_hint == AttachmentFormat.XBRL_XML
    assert len(filing.raw_metadata_hash) == len(filing.canonical_identity_hash) == 64


def test_quarter_discovery_distinguishes_non_cumulative_from_ytd():
    quarter = _discovery(
        period="Quarterly",
        relatingTo="Quarter ended",
        cumulative="Non-Cumulative",
        fromDate="01-Apr-2024",
        toDate="30-Jun-2024",
        financialYear="01-Apr-2024 To 31-Mar-2025",
    )
    assert quarter.period.period_type.value == "quarter"
    assert quarter.period.fiscal_quarter == 1
    ytd = _discovery(
        period="Quarterly",
        relatingTo="Six months ended",
        cumulative="Cumulative",
        fromDate="01-Apr-2024",
        toDate="30-Sep-2024",
        financialYear="01-Apr-2024 To 31-Mar-2025",
    )
    assert ytd.period.period_type.value == "year_to_date"
    assert ytd.period.fiscal_quarter == 2


def test_xbrl_parser_maps_real_fixture_with_units_periods_and_basis():
    parsed = parse_nse_results_xbrl(_document(), _discovery())
    facts = {item.metric_id: item for item in parsed.facts}
    assert parsed.recognition.required_fields_present
    assert parsed.basis == ConsolidationBasis.CONSOLIDATED
    assert facts["revenue"].value == Decimal("8375330000.00")
    assert facts["operating_income"].value == Decimal("3382250000.00")
    assert facts["total_debt"].value == Decimal("0.00")
    assert facts["fcf"].value == Decimal("2613690000.00")
    assert facts["total_assets"].period.period_type.value == "instant"
    assert facts["revenue"].period.period_type.value == "annual"


def test_xbrl_basis_conflict_is_explicit_and_not_guessed():
    parsed = parse_nse_results_xbrl(_document(), _discovery(consolidated="Standalone"))
    assert parsed.basis == ConsolidationBasis.CONFLICTING
    assert any("disagree" in warning for warning in parsed.warnings)


def test_parser_registry_rejects_unqualified_formats():
    document = _document().model_copy(update={"attachment_format": AttachmentFormat.XLSX})
    with pytest.raises(ProviderError, match="unsupported official filing format"):
        OfficialParserRegistry().parse(document, _discovery())
    assert OfficialParserRegistry.support(AttachmentFormat.XLSX)["status"] == "unsupported"


def test_safe_fetch_is_allowlisted_bounded_atomic_and_cache_first(tmp_path):
    calls = []
    body = (FIXTURES / "kfintech-2024-results.xml").read_bytes()

    def transport(url, headers, timeout, policy):
        calls.append((url, headers, timeout))
        return HttpResult(200, url, {"content-type": "application/xml", "etag": '"fixture"'}, body)

    policy = FetchPolicy(
        cache_dir=tmp_path,
        request_interval_seconds=0,
        max_document_bytes=len(body) + 1,
        max_requests=2,
    )
    fetcher = SafeDocumentFetcher(policy, transport=transport, sleeper=lambda _: None)
    url = "https://nsearchives.nseindia.com/corporate/xbrl/fixture.xml"
    first = fetcher.fetch_document(url, filename="../../unsafe fixture.xml", declared_content_type="application/xml")
    second = fetcher.fetch_document(url, filename="ignored.xml", declared_content_type="application/xml")
    assert first.filename == "unsafe_fixture.xml"
    assert not first.cache_hit and second.cache_hit
    assert first.sha256 == second.sha256 and len(calls) == 1
    assert fetcher.stats.cache_hits == 1
    assert all("unsafe fixture" not in str(path) for path in tmp_path.rglob("*"))
    with pytest.raises(ProviderError):
        validate_official_url("https://example.com/filing.xml")
    assert sanitize_filename("../../a b?.xml") == "a_b_.xml"


def test_safe_fetch_rejects_oversize_and_mime_signature_mismatch(tmp_path):
    def too_large(url, headers, timeout, policy):
        return HttpResult(200, url, {"content-type": "application/xml"}, b"x" * 50)

    fetcher = SafeDocumentFetcher(FetchPolicy(cache_dir=tmp_path, request_interval_seconds=0, max_document_bytes=10), transport=too_large, sleeper=lambda _: None)
    # Injected transports are still checked by the same byte boundary.
    with pytest.raises(ProviderError, match="byte limit"):
        fetcher.fetch_document(
            "https://nsearchives.nseindia.com/a.pdf",
            filename="a.pdf",
            declared_content_type="application/pdf",
        )
    mismatch = SafeDocumentFetcher(
        FetchPolicy(cache_dir=tmp_path / "mismatch", request_interval_seconds=0, max_document_bytes=100),
        transport=lambda url, headers, timeout, policy: HttpResult(
            200, url, {"content-type": "application/pdf"}, b"not-a-pdf"
        ),
        sleeper=lambda _: None,
    )
    with pytest.raises(ProviderError, match="MIME/signature mismatch"):
        mismatch.fetch_document(
            "https://nsearchives.nseindia.com/a.pdf",
            filename="a.pdf",
            declared_content_type="application/pdf",
        )


def test_safe_fetch_retries_only_transient_failures_and_invalidates_exact_checksum(tmp_path):
    body = (FIXTURES / "kfintech-2024-results.xml").read_bytes()
    calls = []

    def transient(url, headers, timeout, policy):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 503, "temporary", {}, None)
        return HttpResult(200, url, {"content-type": "application/xml"}, body)

    fetcher = SafeDocumentFetcher(
        FetchPolicy(cache_dir=tmp_path, request_interval_seconds=0, max_retries=1),
        transport=transient,
        sleeper=lambda _: None,
    )
    url = "https://nsearchives.nseindia.com/retry.xml"
    document = fetcher.fetch_document(url, filename="retry.xml")
    assert fetcher.stats.retries == 1 and len(calls) == 2
    with pytest.raises(ValueError, match="does not match"):
        fetcher.invalidate(url, expected_sha256="0" * 64)
    assert fetcher.invalidate(url, expected_sha256=document.sha256)
    assert not fetcher.invalidate(url, expected_sha256=document.sha256)

    permanent_calls = []

    def permanent(url, headers, timeout, policy):
        permanent_calls.append(url)
        raise urllib.error.HTTPError(url, 404, "missing", {}, None)

    permanent_fetcher = SafeDocumentFetcher(
        FetchPolicy(cache_dir=tmp_path / "permanent", request_interval_seconds=0, max_retries=2),
        transport=permanent,
        sleeper=lambda _: None,
    )
    with pytest.raises(ProviderError, match="failed safely"):
        permanent_fetcher.fetch_document(url, filename="missing.xml")
    assert len(permanent_calls) == 1 and permanent_fetcher.stats.retries == 0


def test_official_import_is_idempotent_and_links_canonical_facts():
    engine = _store()
    filing = _discovery()
    with Session(engine) as session:
        summary = ingest_official_filings(
            session,
            [(filing, "company", "instrument")],
            document_loader=lambda _: _document(),
        )
        assert summary.source_records_created == 1
        assert summary.templates_recognized == 1
        assert summary.facts_accepted >= 10
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OfficialFilingSourceRow)) == 1
        assert session.scalar(select(func.count()).select_from(OfficialFilingAttachmentRow)) == 1
        assert session.scalar(select(func.count()).select_from(FinancialFilingRow)) == 1
        assert session.scalar(select(FinancialFactRow.normalized_value).where(FinancialFactRow.metric_id == "revenue")) == Decimal("8375330000.00000000")
        summary = ingest_official_filings(
            session,
            [(filing, "company", "instrument")],
            document_loader=lambda _: pytest.fail("an already parsed attachment must not refetch"),
        )
        assert summary.source_records_unchanged == 1 and summary.attachments_reused == 1


def test_latest_known_and_as_filed_views_respect_revision_cutoffs():
    engine = _store()
    original = _discovery()
    original_xml = (FIXTURES / "kfintech-2024-results.xml").read_bytes()
    revised = _discovery(
        seqNumber="1169771",
        reInd="Y",
        resultDescription="Revised financial results",
        broadCastDate="02-May-2024 10:00:00",
        filingDate="02-May-2024 10:00",
        xbrl="https://nsearchives.nseindia.com/corporate/xbrl/INDAS_REVISED_FIXTURE.xml",
    )
    revised_xml = original_xml.replace(b"8375330000.00", b"8376330000.00")
    documents = {
        original.source_filing_id: _document(original_xml),
        revised.source_filing_id: _document(revised_xml).model_copy(update={"source_url": revised.attachments[0].source_url, "sha256": hashlib.sha256(revised_xml).hexdigest()}),
    }
    with Session(engine) as session:
        ingest_official_filings(
            session,
            [(original, "company", "instrument")],
            document_loader=lambda _: documents[original.source_filing_id],
        )
        ingest_official_filings(
            session,
            [(revised, "company", "instrument")],
            document_loader=lambda _: documents[revised.source_filing_id],
        )
    with Session(engine) as session:
        before = official_fact_view(
            session,
            "instrument",
            metric_ids=("revenue",),
            as_of=datetime(2024, 4, 30, tzinfo=timezone.utc),
        )
        after = official_fact_view(
            session,
            "instrument",
            metric_ids=("revenue",),
            as_of=datetime(2024, 5, 3, tzinfo=timezone.utc),
        )
        as_filed = official_fact_view(
            session,
            "instrument",
            metric_ids=("revenue",),
            as_of=datetime(2024, 5, 3, tzinfo=timezone.utc),
            view="as_filed",
        )
        assert [row.normalized_value for row in before] == [Decimal("8375330000.00000000")]
        assert [row.normalized_value for row in after] == [Decimal("8376330000.00000000")]
        assert len(as_filed) == 2


def test_public_metrics_require_compatible_official_multi_year_lineage():
    engine = _store()
    filings = []
    values = {
        2021: ("100", "10", "50", "50"),
        2022: ("110", "11", "55", "45"),
        2023: ("121", "12", "60", "40"),
        2024: ("133.1", "15", "70", "30"),
    }
    for year, (revenue, operating, equity, debt) in values.items():
        period = FinancialPeriod(
            period_type="annual", fiscal_year=year,
            period_start=date(year - 1, 4, 1), period_end=date(year, 3, 31),
        )
        instant = FinancialPeriod(
            period_type="instant", fiscal_year=year,
            period_end=date(year, 3, 31), instant_date=date(year, 3, 31),
        )
        facts = [
            SourceFact(source_field="RevenueFromOperations", metric_id="revenue", value=Decimal(revenue), unit="INR", currency="INR", period=period, basis="consolidated"),
            SourceFact(source_field="EBIT", metric_id="operating_income", value=Decimal(operating), unit="INR", currency="INR", period=period, basis="consolidated"),
            SourceFact(source_field="Equity", metric_id="total_equity", value=Decimal(equity), unit="INR", currency="INR", period=instant, basis="consolidated"),
            SourceFact(source_field="Borrowings", metric_id="total_debt", value=Decimal(debt), unit="INR", currency="INR", period=instant, basis="consolidated"),
        ]
        filings.append(FilingInput(
            source_code="nse_financial_results", source_filing_id=f"official-{year}",
            company_id="company", instrument_id="instrument", filing_type="annual_results",
            period=period, basis="consolidated", currency="INR", original_unit="INR",
            filing_date=date(year, 5, 1), publication_timestamp=datetime(year, 5, 1, tzinfo=timezone.utc),
            audited_status="audited", retrieved_at=datetime(year, 5, 2, tzinfo=timezone.utc),
            raw_payload_hash=f"{year:064d}"[-64:], source_url=f"https://nsearchives.nseindia.com/{year}.xml",
            facts=facts,
        ))
    with Session(engine) as session:
        assert import_filings(session, filings).facts_normalized == 16
    with Session(engine) as session:
        metrics = derive_official_public_metrics(
            session, "instrument", as_of=datetime(2025, 1, 1, tzinfo=timezone.utc)
        )
        assert metrics["revenue_cagr_3y"]["value"] == pytest.approx(Decimal("0.1"))
        assert metrics["roce_3y"]["value"] == Decimal("0.1266666666666666666666666667")
        assert metrics["revenue_cagr_3y"]["basis"] == "consolidated"


@pytest.mark.parametrize(("official", "compatibility", "expected"), [
    ("10", "10", ReconciliationStatus.EXACT_MATCH),
    ("1000", "1000.50", ReconciliationStatus.WITHIN_ROUNDING),
    ("1000", "1200", ReconciliationStatus.MATERIAL_DIFFERENCE),
    ("10", None, ReconciliationStatus.OFFICIAL_ONLY),
    (None, "10", ReconciliationStatus.COMPATIBILITY_ONLY),
    (None, None, ReconciliationStatus.BOTH_MISSING),
])
def test_reconciliation_status_and_source_selection(official, compatibility, expected):
    period = _discovery().period
    result = reconcile_values(
        instrument_id="instrument",
        metric_id="revenue_cagr_3y",
        official_period=period,
        compatibility_period=period,
        official_basis=ConsolidationBasis.CONSOLIDATED,
        compatibility_basis=ConsolidationBasis.CONSOLIDATED,
        official_value=Decimal(official) if official is not None else None,
        compatibility_value=Decimal(compatibility) if compatibility is not None else None,
        official_unit="ratio",
        compatibility_unit="ratio",
        official_publication_state="eligible",
    )
    assert result.status == expected
    if official is not None:
        assert result.selected_source == "nse_financial_results"
    elif compatibility is not None:
        assert result.selected_source == "yahoo_compatibility"


def test_reconciliation_rejects_period_unit_and_basis_mismatch_from_official_selection():
    period = _discovery().period
    changed_period = period.model_copy(update={"period_end": date(2023, 3, 31), "fiscal_year": 2023})
    mismatch = reconcile_values(
        instrument_id="instrument",
        metric_id="revenue_cagr_3y",
        official_period=period,
        compatibility_period=changed_period,
        official_basis=ConsolidationBasis.CONSOLIDATED,
        compatibility_basis=ConsolidationBasis.CONSOLIDATED,
        official_value=Decimal("0.2"),
        compatibility_value=Decimal("0.2"),
        official_unit="ratio",
        compatibility_unit="ratio",
    )
    assert mismatch.status == ReconciliationStatus.PERIOD_MISMATCH
    assert mismatch.selected_source == "yahoo_compatibility"


def test_fixture_cli_ingestion_is_offline_bounded_and_dry_run_safe(tmp_path, monkeypatch):
    database = tmp_path / "platform.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        imported = import_instruments(session, [{
            "company_name": "Kfin Technologies Limited",
            "symbol": "KFINTECH",
            "exchange": "NSE",
            "isin": "INE138Y01010",
            "listing_status": "active",
            "provider_symbols": {"yahoo": "KFINTECH.NS"},
        }], source_code="fixture_master", source_version="1")
        assert imported.instruments_created == 1
    monkeypatch.setenv("MBE_DATABASE_URL", f"sqlite:///{database}")
    runner = CliRunner()
    discovered = runner.invoke(cli_app, [
        "nse-filings-discover", "--fixture-dir", str(FIXTURES), "--max-filings", "1",
    ])
    assert discovered.exit_code == 0 and '"fixture_mode": true' in discovered.stdout
    dry = runner.invoke(cli_app, [
        "nse-financials-ingest", "--fixture-dir", str(FIXTURES), "--dry-run",
    ])
    assert dry.exit_code == 0 and '"dry_run": true' in dry.stdout
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OfficialFilingSourceRow)) == 0
    actual = runner.invoke(cli_app, [
        "nse-financials-ingest", "--fixture-dir", str(FIXTURES),
    ])
    assert actual.exit_code == 0 and '"facts_accepted"' in actual.stdout
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OfficialFilingSourceRow)) == 1
