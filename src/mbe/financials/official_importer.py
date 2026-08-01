"""Idempotent staged ingestion for discovered official NSE result filings."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from mbe.data.provider import ProviderError
from mbe.db.models import DataSourceRow, FinancialFilingRow, OfficialFilingAttachmentRow
from mbe.financials.domain import ConsolidationBasis, FilingInput, QualityState
from mbe.financials.importer import import_filings
from mbe.financials.official_domain import (
    DiscoveredAttachment,
    DiscoveredOfficialFiling,
    FetchedDocument,
    FilingRelationshipType,
    OfficialImportSummary,
    ParseStatus,
)
from mbe.financials.official_repository import (
    add_relationship,
    attachment_for,
    detect_checksum_duplicate,
    link_canonical_filing,
    persist_discovery,
    record_fetched,
    record_parse,
)
from mbe.financials.parsers import OfficialParserRegistry


DocumentLoader = Callable[[DiscoveredAttachment], FetchedDocument]


def _predecessor(
    session: Session,
    discovery: DiscoveredOfficialFiling,
    *,
    instrument_id: str,
    basis: ConsolidationBasis,
) -> FinancialFilingRow | None:
    if discovery.revision_hint != "revised":
        return None
    return session.scalar(select(FinancialFilingRow).join(
        DataSourceRow, FinancialFilingRow.source_id == DataSourceRow.source_id
    ).where(
        DataSourceRow.code == "nse_financial_results",
        FinancialFilingRow.instrument_id == instrument_id,
        FinancialFilingRow.filing_type == discovery.filing_type,
        FinancialFilingRow.period_end == discovery.period.period_end,
        FinancialFilingRow.consolidation_basis == basis.value,
        FinancialFilingRow.publication_timestamp < discovery.publication_timestamp,
    ).order_by(
        FinancialFilingRow.publication_timestamp.desc(),
        FinancialFilingRow.revision_number.desc(),
    ).limit(1))


def ingest_official_filings(
    session: Session,
    filings: list[tuple[DiscoveredOfficialFiling, str, str]],
    *,
    document_loader: DocumentLoader,
    parser_registry: OfficialParserRegistry | None = None,
    metadata_only: bool = False,
    dry_run: bool = False,
    max_documents: int = 100,
    quarantine_stop_rate: Decimal | None = None,
) -> OfficialImportSummary:
    """Ingest `(discovery, company_id, instrument_id)` tuples in one DB transaction."""
    registry = parser_registry or OfficialParserRegistry()
    summary = OfficialImportSummary(
        instruments_attempted=len({instrument_id for _, _, instrument_id in filings}),
        filings_discovered=len(filings),
    )
    instruments_with_filings: set[str] = set()
    documents_seen = 0
    try:
        for discovery, company_id, instrument_id in filings:
            instruments_with_filings.add(instrument_id)
            source_row, created = persist_discovery(
                session,
                discovery,
                company_id=company_id,
                instrument_id=instrument_id,
            )
            if created:
                summary.source_records_created += 1
            else:
                summary.source_records_unchanged += 1
            if discovery.revision_hint == "revised":
                summary.revised_filings += 1
            if discovery.basis_hint == ConsolidationBasis.CONSOLIDATED:
                summary.consolidated_filings += 1
            elif discovery.basis_hint == ConsolidationBasis.STANDALONE:
                summary.standalone_filings += 1
            else:
                summary.unknown_basis_filings += 1
            if metadata_only:
                source_row.metadata_status = "metadata_only"
                continue
            if not discovery.attachments:
                source_row.metadata_status = "missing_attachment"
                summary.errors.append(f"{discovery.source_filing_id}: no supported attachment URL")
                continue
            for attachment in discovery.attachments:
                if documents_seen >= max_documents:
                    summary.errors.append("official document cap reached")
                    break
                documents_seen += 1
                attachment_row = attachment_for(session, source_row.source_record_id, attachment.sequence)
                if attachment_row.parse_status == ParseStatus.PARSED.value and attachment_row.canonical_filing_id:
                    summary.attachments_reused += 1
                    continue
                try:
                    document = document_loader(attachment)
                    record_fetched(attachment_row, document)
                except Exception as exc:
                    attachment_row.parse_status = ParseStatus.CORRUPT.value
                    attachment_row.quarantine_code = "fetch_or_validation_failed"
                    summary.attachments_corrupt += 1
                    summary.errors.append(f"{discovery.source_filing_id}: {type(exc).__name__}")
                    continue
                if document.cache_hit:
                    summary.attachments_reused += 1
                else:
                    summary.attachments_downloaded += 1
                duplicate = detect_checksum_duplicate(session, attachment_row)
                if duplicate and duplicate.canonical_filing_id:
                    attachment_row.canonical_filing_id = duplicate.canonical_filing_id
                    attachment_row.parse_status = ParseStatus.PARSED.value
                    attachment_row.warning_summary = "Duplicate official attachment checksum; canonical filing reused."
                    source_row.metadata_status = "duplicate_attachment"
                    continue
                support = registry.support(document.attachment_format)
                if support["status"] != "supported":
                    record_parse(
                        attachment_row,
                        None,
                        status=ParseStatus.UNSUPPORTED,
                        unsupported_reason=support["reason"],
                    )
                    source_row.metadata_status = "unsupported_attachment"
                    summary.attachments_unsupported += 1
                    continue
                try:
                    parsed = registry.parse(document, discovery)
                except ProviderError as exc:
                    record_parse(
                        attachment_row,
                        None,
                        status=ParseStatus.QUARANTINED,
                        unsupported_reason=str(exc),
                        quarantine_code="template_or_semantics_failed",
                    )
                    source_row.metadata_status = "quarantined"
                    summary.templates_unrecognized += 1
                    summary.errors.append(f"{discovery.source_filing_id}: parser quarantine")
                    continue
                record_parse(attachment_row, parsed, status=ParseStatus.RECOGNIZED)
                summary.templates_recognized += 1
                summary.facts_parsed += len(parsed.facts)
                if parsed.basis == ConsolidationBasis.CONFLICTING:
                    summary.conflicting_basis_filings += 1
                    record_parse(
                        attachment_row,
                        parsed,
                        status=ParseStatus.QUARANTINED,
                        unsupported_reason="Filing metadata and parsed XBRL basis conflict.",
                        quarantine_code="conflicting_basis",
                    )
                    source_row.metadata_status = "quarantined"
                    summary.facts_rejected += len(parsed.facts)
                    summary.errors.append(f"{discovery.source_filing_id}: conflicting basis")
                    continue
                predecessor = _predecessor(
                    session,
                    discovery,
                    instrument_id=instrument_id,
                    basis=parsed.basis,
                )
                filing_input = FilingInput(
                    source_code="nse_financial_results",
                    source_filing_id=discovery.source_filing_id,
                    company_id=company_id,
                    instrument_id=instrument_id,
                    filing_type=discovery.filing_type,
                    period=parsed.period,
                    basis=parsed.basis,
                    currency=parsed.currency,
                    original_unit=parsed.original_unit,
                    filing_date=discovery.filing_date,
                    publication_timestamp=discovery.publication_timestamp,
                    audited_status=parsed.audited_status,
                    revision_number=(predecessor.revision_number + 1) if predecessor else 1,
                    restates_source_filing_id=predecessor.source_filing_id if predecessor else None,
                    retrieved_at=document.retrieved_at,
                    raw_payload_hash=document.sha256,
                    source_url=attachment.source_url,
                    facts=parsed.facts,
                )
                imported = import_filings(
                    session,
                    [filing_input],
                    dry_run=False,
                    manage_transaction=False,
                )
                summary.facts_accepted += imported.facts_normalized
                summary.facts_rejected += imported.facts_rejected
                summary.facts_warned += sum(
                    1 for fact in parsed.facts
                    if parsed.warnings or fact.basis == ConsolidationBasis.UNKNOWN
                )
                if imported.errors:
                    summary.errors.extend(imported.errors)
                    record_parse(
                        attachment_row,
                        parsed,
                        status=ParseStatus.QUARANTINED,
                        quarantine_code="canonical_import_rejected",
                    )
                    source_row.metadata_status = "quarantined"
                    continue
                source = session.scalar(select(DataSourceRow).where(DataSourceRow.code == "nse_financial_results"))
                canonical = session.scalar(select(FinancialFilingRow).where(
                    FinancialFilingRow.source_id == source.source_id,
                    FinancialFilingRow.source_filing_id == filing_input.source_filing_id,
                    FinancialFilingRow.revision_number == filing_input.revision_number,
                ))
                if canonical is None:
                    raise RuntimeError("canonical filing was not created")
                link_canonical_filing(attachment_row, canonical.filing_id)
                source_row.metadata_status = "parsed"
                if predecessor:
                    add_relationship(
                        session,
                        from_filing_id=canonical.filing_id,
                        to_filing_id=predecessor.filing_id,
                        relationship_type=FilingRelationshipType.REVISES,
                        evidence="Official NSE metadata identified the later result as revised.",
                    )
            quarantined = (
                summary.attachments_corrupt + summary.attachments_unsupported
                + summary.templates_unrecognized + summary.conflicting_basis_filings
            )
            if (
                quarantine_stop_rate is not None and documents_seen >= 4
                and Decimal(quarantined) / Decimal(documents_seen) > quarantine_stop_rate
            ):
                summary.errors.append("official quarantine stop rate exceeded")
                break
        summary.instruments_with_filings = len(instruments_with_filings)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    return summary
