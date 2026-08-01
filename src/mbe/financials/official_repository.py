"""Persistence and safe public reads for official filing lineage."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mbe.db.models import (
    DataSourceRow,
    FinancialFactRow,
    FinancialFilingRelationshipRow,
    FinancialFilingRow,
    FinancialReconciliationRow,
    FinancialSourceSelectionRow,
    OfficialFilingAttachmentRow,
    OfficialFilingSourceRow,
)
from mbe.financials.official_domain import (
    DiscoveredOfficialFiling,
    FetchedDocument,
    FilingRelationshipType,
    ParseStatus,
    ParsedOfficialFiling,
    ReconciliationResult,
)


def ensure_official_source(session: Session) -> DataSourceRow:
    source = session.scalar(select(DataSourceRow).where(DataSourceRow.code == "nse_financial_results"))
    if source is None:
        source = DataSourceRow(
            code="nse_financial_results",
            name="NSE Corporate Financial Results",
            source_type="official_financial_filings",
            url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
            is_official=True,
            limitations="Bounded public result-announcement metadata and fixture-qualified Ind-AS XBRL only; operator terms review required.",
        )
        session.add(source)
        session.flush()
    return source


def persist_discovery(
    session: Session,
    filing: DiscoveredOfficialFiling,
    *,
    company_id: str,
    instrument_id: str,
) -> tuple[OfficialFilingSourceRow, bool]:
    source = ensure_official_source(session)
    existing = session.scalar(select(OfficialFilingSourceRow).where(
        OfficialFilingSourceRow.source_id == source.source_id,
        OfficialFilingSourceRow.source_filing_id == filing.source_filing_id,
        OfficialFilingSourceRow.raw_metadata_hash == filing.raw_metadata_hash,
    ))
    if existing is not None:
        return existing, False
    source_record_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"nse-source:{filing.source_filing_id}:{filing.raw_metadata_hash}",
    ))
    row = OfficialFilingSourceRow(
        source_record_id=source_record_id,
        company_id=company_id,
        instrument_id=instrument_id,
        source_id=source.source_id,
        source_filing_id=filing.source_filing_id,
        canonical_identity_hash=filing.canonical_identity_hash,
        company_name=filing.company_name,
        nse_symbol=filing.nse_symbol,
        isin=filing.isin,
        subject=filing.subject[:500],
        category=filing.category,
        filing_type=filing.filing_type,
        filing_date=filing.filing_date,
        publication_timestamp=filing.publication_timestamp,
        source_timestamp=filing.source_timestamp,
        period_type=filing.period.period_type.value,
        period_start=filing.period.period_start,
        period_end=filing.period.period_end,
        fiscal_year=filing.period.fiscal_year,
        fiscal_quarter=filing.period.fiscal_quarter,
        basis_hint=filing.basis_hint.value,
        audited_status=filing.audited_status[:24],
        revision_hint=filing.revision_hint,
        source_url=filing.source_url,
        raw_metadata_hash=filing.raw_metadata_hash,
        raw_response_hash=filing.raw_response_hash,
        discovered_at=datetime.now(timezone.utc),
        retrieved_at=filing.retrieved_at,
        metadata_status="discovered",
    )
    session.add(row)
    session.flush()
    for attachment in filing.attachments:
        session.add(OfficialFilingAttachmentRow(
            attachment_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"nse-attachment:{source_record_id}:{attachment.sequence}")),
            source_record_id=source_record_id,
            sequence=attachment.sequence,
            source_url=attachment.source_url,
            filename=attachment.filename[:180],
            declared_content_type=attachment.declared_content_type,
            attachment_format=attachment.format_hint.value,
            cache_state="not_fetched",
            parse_status=ParseStatus.METADATA_ONLY.value,
        ))
    session.flush()
    return row, True


def attachment_for(session: Session, source_record_id: str, sequence: int) -> OfficialFilingAttachmentRow:
    row = session.scalar(select(OfficialFilingAttachmentRow).where(
        OfficialFilingAttachmentRow.source_record_id == source_record_id,
        OfficialFilingAttachmentRow.sequence == sequence,
    ))
    if row is None:
        raise LookupError("official attachment metadata was not persisted")
    return row


def record_fetched(
    row: OfficialFilingAttachmentRow,
    document: FetchedDocument,
) -> None:
    row.filename = document.filename
    row.detected_content_type = document.detected_content_type
    row.attachment_format = document.attachment_format.value
    row.content_length = document.content_length
    row.checksum_sha256 = document.sha256
    row.etag = document.etag
    row.last_modified = document.last_modified
    row.retrieved_at = document.retrieved_at
    row.cache_state = "reused" if document.cache_hit else "downloaded"


def record_parse(
    row: OfficialFilingAttachmentRow,
    parsed: ParsedOfficialFiling | None,
    *,
    status: ParseStatus,
    unsupported_reason: str | None = None,
    quarantine_code: str | None = None,
) -> None:
    row.parse_status = status.value
    row.unsupported_reason = unsupported_reason
    row.quarantine_code = quarantine_code
    if parsed:
        row.parser_version = parsed.parser_version
        row.template_id = parsed.recognition.template_id
        row.template_version = parsed.recognition.template_version
        row.recognition_confidence = parsed.recognition.confidence
        row.warning_summary = "; ".join(parsed.warnings) or None


def link_canonical_filing(row: OfficialFilingAttachmentRow, filing_id: str) -> None:
    row.canonical_filing_id = filing_id
    row.parse_status = ParseStatus.PARSED.value


def detect_checksum_duplicate(
    session: Session,
    row: OfficialFilingAttachmentRow,
) -> OfficialFilingAttachmentRow | None:
    if not row.checksum_sha256:
        return None
    return session.scalar(select(OfficialFilingAttachmentRow).where(
        OfficialFilingAttachmentRow.checksum_sha256 == row.checksum_sha256,
        OfficialFilingAttachmentRow.attachment_id != row.attachment_id,
        OfficialFilingAttachmentRow.canonical_filing_id.is_not(None),
    ).order_by(OfficialFilingAttachmentRow.retrieved_at.asc()).limit(1))


def add_relationship(
    session: Session,
    *,
    from_filing_id: str,
    to_filing_id: str,
    relationship_type: FilingRelationshipType,
    evidence: str,
) -> None:
    if from_filing_id == to_filing_id:
        return
    exists = session.scalar(select(FinancialFilingRelationshipRow).where(
        FinancialFilingRelationshipRow.from_filing_id == from_filing_id,
        FinancialFilingRelationshipRow.to_filing_id == to_filing_id,
        FinancialFilingRelationshipRow.relationship_type == relationship_type.value,
    ))
    if not exists:
        session.add(FinancialFilingRelationshipRow(
            from_filing_id=from_filing_id,
            to_filing_id=to_filing_id,
            relationship_type=relationship_type.value,
            evidence=evidence,
            detected_at=datetime.now(timezone.utc),
        ))


def persist_reconciliation(
    session: Session,
    result: ReconciliationResult,
    *,
    financial_dataset_build_id: str | None,
    source_cutoff: datetime,
) -> str:
    identity = f"{financial_dataset_build_id}:{result.instrument_id}:{result.metric_id}:{result.period.period_end}:{result.basis.value}"
    reconciliation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mbe-reconciliation:{identity}"))
    row = session.get(FinancialReconciliationRow, reconciliation_id)
    if row is None:
        row = FinancialReconciliationRow(
            reconciliation_id=reconciliation_id,
            financial_dataset_build_id=financial_dataset_build_id,
            instrument_id=result.instrument_id,
            metric_id=result.metric_id,
            period_type=result.period.period_type.value,
            period_end=result.period.period_end,
            consolidation_basis=result.basis.value,
            official_fact_id=result.official_fact_id,
            official_value=result.official_value,
            compatibility_value=result.compatibility_value,
            unit=result.unit,
            absolute_difference=result.absolute_difference,
            percentage_difference=result.percentage_difference,
            reconciliation_status=result.status.value,
            selected_value=result.selected_value,
            selected_source=result.selected_source,
            selection_reason=result.selection_reason,
            rejected_alternatives=result.rejected_alternatives,
            reconciliation_rule_version=result.rule_version,
            selection_rule_version=result.selection_rule_version,
            source_cutoff=source_cutoff,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
    if financial_dataset_build_id and result.selected_source and result.selected_value is not None:
        selection_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mbe-selection:{identity}"))
        if session.get(FinancialSourceSelectionRow, selection_id) is None:
            session.add(FinancialSourceSelectionRow(
                selection_id=selection_id,
                financial_dataset_build_id=financial_dataset_build_id,
                instrument_id=result.instrument_id,
                metric_id=result.metric_id,
                period_type=result.period.period_type.value,
                period_end=result.period.period_end,
                consolidation_basis=result.basis.value,
                selected_fact_id=result.official_fact_id if result.selected_source == "nse_financial_results" else None,
                reconciliation_id=reconciliation_id,
                selected_source=result.selected_source,
                selected_value=result.selected_value,
                selection_rule_version=result.selection_rule_version,
                selection_reason=result.selection_reason,
                rejected_alternatives=result.rejected_alternatives,
                selected_at=datetime.now(timezone.utc),
            ))
    return reconciliation_id


def filing_list(
    session: Session,
    instrument_id: str,
    *,
    filing_type: str | None = None,
    date_from=None,
    date_to=None,
    basis: str | None = None,
    revised: bool | None = None,
    source: str | None = None,
    limit: int = 20,
    as_of: datetime | None = None,
) -> list[dict]:
    stmt = select(OfficialFilingSourceRow).where(OfficialFilingSourceRow.instrument_id == instrument_id)
    if filing_type:
        stmt = stmt.where(OfficialFilingSourceRow.filing_type == filing_type)
    if date_from:
        stmt = stmt.where(OfficialFilingSourceRow.filing_date >= date_from)
    if date_to:
        stmt = stmt.where(OfficialFilingSourceRow.filing_date <= date_to)
    if basis:
        stmt = stmt.where(OfficialFilingSourceRow.basis_hint == basis)
    if revised is not None:
        stmt = stmt.where(OfficialFilingSourceRow.revision_hint == ("revised" if revised else "original"))
    if source and source != "nse_financial_results":
        return []
    if as_of:
        stmt = stmt.where(OfficialFilingSourceRow.publication_timestamp <= as_of)
    rows = session.scalars(stmt.order_by(
        OfficialFilingSourceRow.publication_timestamp.desc(),
        OfficialFilingSourceRow.source_record_id,
    ).limit(limit)).all()
    attachments_by_source: dict[str, list[OfficialFilingAttachmentRow]] = {
        row.source_record_id: [] for row in rows
    }
    if rows:
        attachments = session.scalars(select(OfficialFilingAttachmentRow).where(
            OfficialFilingAttachmentRow.source_record_id.in_(attachments_by_source)
        ).order_by(
            OfficialFilingAttachmentRow.source_record_id,
            OfficialFilingAttachmentRow.sequence,
        )).all()
        for attachment in attachments:
            attachments_by_source[attachment.source_record_id].append(attachment)
    result = []
    for row in rows:
        attachments = attachments_by_source[row.source_record_id]
        result.append({
            "filing_id": row.source_record_id,
            "source_filing_id": row.source_filing_id,
            "source": "nse_financial_results",
            "company_name": row.company_name,
            "nse_symbol": row.nse_symbol,
            "subject": row.subject,
            "category": row.category,
            "filing_type": row.filing_type,
            "filing_date": row.filing_date,
            "publication_timestamp": row.publication_timestamp,
            "period_type": row.period_type,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "basis": row.basis_hint,
            "audited_status": row.audited_status,
            "revision_status": row.revision_hint,
            "source_url": row.source_url,
            "metadata_status": row.metadata_status,
            "attachments": [{
                "attachment_id": item.attachment_id,
                "filename": item.filename,
                "format": item.attachment_format,
                "content_type": item.detected_content_type or item.declared_content_type,
                "parse_status": item.parse_status,
                "template_id": item.template_id,
                "parser_version": item.parser_version,
                "quality_warning": item.warning_summary,
                "source_url": item.source_url,
            } for item in attachments],
        })
    return result


def filing_detail(session: Session, source_record_id: str) -> dict | None:
    row = session.get(OfficialFilingSourceRow, source_record_id)
    if row is None:
        return None
    results = filing_list(session, row.instrument_id, limit=100)
    detail = next((item for item in results if item["filing_id"] == source_record_id), None)
    if detail is None:
        return None
    attachments = session.scalars(select(OfficialFilingAttachmentRow).where(
        OfficialFilingAttachmentRow.source_record_id == source_record_id,
    )).all()
    canonical_ids = {item.canonical_filing_id for item in attachments if item.canonical_filing_id}
    relationships = []
    if canonical_ids:
        relations = session.scalars(select(FinancialFilingRelationshipRow).where(
            (FinancialFilingRelationshipRow.from_filing_id.in_(canonical_ids))
            | (FinancialFilingRelationshipRow.to_filing_id.in_(canonical_ids))
        )).all()
        relationships = [{
            "type": item.relationship_type,
            "from_filing_id": item.from_filing_id,
            "to_filing_id": item.to_filing_id,
            "evidence": item.evidence,
        } for item in relations]
    detail["canonical_filing_ids"] = sorted(canonical_ids)
    detail["relationships"] = relationships
    return detail


def reconciliation_summary(session: Session, instrument_id: str, *, limit: int = 50) -> list[dict]:
    rows = session.scalars(select(FinancialReconciliationRow).where(
        FinancialReconciliationRow.instrument_id == instrument_id,
    ).order_by(FinancialReconciliationRow.period_end.desc(), FinancialReconciliationRow.metric_id).limit(limit)).all()
    return [{
        "reconciliation_id": row.reconciliation_id,
        "financial_dataset_build_id": row.financial_dataset_build_id,
        "metric_id": row.metric_id,
        "period_type": row.period_type,
        "period_end": row.period_end,
        "basis": row.consolidation_basis,
        "official_value": float(row.official_value) if row.official_value is not None else None,
        "compatibility_value": float(row.compatibility_value) if row.compatibility_value is not None else None,
        "unit": row.unit,
        "absolute_difference": float(row.absolute_difference) if row.absolute_difference is not None else None,
        "percentage_difference": float(row.percentage_difference) if row.percentage_difference is not None else None,
        "status": row.reconciliation_status,
        "selected_source": row.selected_source,
        "selection_reason": row.selection_reason,
        "warnings": [item.get("reason") for item in row.rejected_alternatives],
    } for row in rows]


def official_coverage(session: Session) -> dict:
    filings = session.scalar(select(func.count()).select_from(OfficialFilingSourceRow)) or 0
    instruments = session.scalar(select(func.count(func.distinct(OfficialFilingSourceRow.instrument_id)))) or 0
    attachments = session.scalar(select(func.count()).select_from(OfficialFilingAttachmentRow)) or 0
    formats = dict(session.execute(select(
        OfficialFilingAttachmentRow.attachment_format, func.count()
    ).group_by(OfficialFilingAttachmentRow.attachment_format)).all())
    parsing = dict(session.execute(select(
        OfficialFilingAttachmentRow.parse_status, func.count()
    ).group_by(OfficialFilingAttachmentRow.parse_status)).all())
    basis = dict(session.execute(select(
        OfficialFilingSourceRow.basis_hint, func.count()
    ).group_by(OfficialFilingSourceRow.basis_hint)).all())
    reconciliation = dict(session.execute(select(
        FinancialReconciliationRow.reconciliation_status, func.count()
    ).group_by(FinancialReconciliationRow.reconciliation_status)).all())
    selections = dict(session.execute(select(
        FinancialSourceSelectionRow.selected_source, func.count()
    ).group_by(FinancialSourceSelectionRow.selected_source)).all())
    conflicting_basis = session.scalar(select(func.count()).select_from(OfficialFilingAttachmentRow).where(
        OfficialFilingAttachmentRow.quarantine_code == "conflicting_basis"
    )) or 0
    resolved_basis = max(0, sum(count for key, count in basis.items() if key in {"consolidated", "standalone"}) - conflicting_basis)
    return {
        "official_source": "NSE corporate financial results",
        "instruments_with_metadata": instruments,
        "filings_discovered": filings,
        "attachments": attachments,
        "format_distribution": formats,
        "parse_status_distribution": parsing,
        "unsupported_format_count": parsing.get("unsupported", 0),
        "basis_distribution": basis,
        "conflicting_basis_count": conflicting_basis,
        "basis_resolution_percent": round(resolved_basis / filings * 100, 1) if filings else 0.0,
        "reconciliation_status_distribution": reconciliation,
        "selected_source_distribution": selections,
        "material_conflict_count": reconciliation.get("material_difference", 0),
    }


def official_fact_view(
    session: Session,
    instrument_id: str,
    *,
    metric_ids: tuple[str, ...],
    as_of: datetime,
    view: str = "latest_known",
) -> list[FinancialFactRow]:
    """Return deterministic official facts at a cutoff without future revisions."""
    if view not in {"latest_known", "as_filed"}:
        raise ValueError("view must be latest_known or as_filed")
    filings = session.scalars(select(FinancialFilingRow).join(
        DataSourceRow, FinancialFilingRow.source_id == DataSourceRow.source_id
    ).where(
        DataSourceRow.code == "nse_financial_results",
        FinancialFilingRow.instrument_id == instrument_id,
        FinancialFilingRow.publication_timestamp <= as_of,
    ).order_by(
        FinancialFilingRow.period_end,
        FinancialFilingRow.publication_timestamp,
        FinancialFilingRow.revision_number,
    )).all()
    if view == "latest_known":
        grouped: dict[tuple, list[FinancialFilingRow]] = {}
        for filing in filings:
            key = (filing.period_type, filing.period_end, filing.consolidation_basis)
            grouped.setdefault(key, []).append(filing)
        selected = []
        for group in grouped.values():
            chosen = group[0]
            for candidate in group[1:]:
                if candidate.restates_filing_id == chosen.filing_id:
                    chosen = candidate
            selected.append(chosen)
        filings = selected
    filing_ids = [row.filing_id for row in filings]
    if not filing_ids:
        return []
    return list(session.scalars(select(FinancialFactRow).where(
        FinancialFactRow.filing_id.in_(filing_ids),
        FinancialFactRow.metric_id.in_(metric_ids),
        FinancialFactRow.quality_status.in_(("valid", "valid_with_warning", "derived")),
    ).order_by(
        FinancialFactRow.period_end,
        FinancialFactRow.metric_id,
        FinancialFactRow.fact_id,
    )).all())
