"""Idempotent normalized financial filing import."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from mbe.db.models import DataSourceRow, FinancialFactRow, FinancialFilingRow, FinancialQualityIssueRow
from mbe.financials.domain import FilingInput, ImportSummary, QualityState
from mbe.financials.metrics import FINANCIAL_METRICS
from mbe.financials.normalization import normalize_decimal
from mbe.financials.quality import validate_filing


def import_filings(
    session: Session,
    filings: list[FilingInput],
    *,
    dry_run: bool = False,
    manage_transaction: bool = True,
) -> ImportSummary:
    summary = ImportSummary(companies_attempted=len({f.company_id for f in filings}), filings_discovered=len(filings))
    imported_companies: set[str] = set()
    try:
        for filing in filings:
            source = session.scalar(select(DataSourceRow).where(DataSourceRow.code == filing.source_code))
            if source is None:
                source = DataSourceRow(code=filing.source_code, name=filing.source_code.replace("_", " ").title(),
                                       source_type="financial_statements", is_official=filing.source_code.startswith("nse"),
                                       limitations="Import-created source; review provider documentation.")
                session.add(source); session.flush()
            existing = session.scalar(select(FinancialFilingRow).where(
                FinancialFilingRow.source_id == source.source_id,
                FinancialFilingRow.source_filing_id == filing.source_filing_id,
                FinancialFilingRow.revision_number == filing.revision_number))
            issues = validate_filing(filing)
            if any(issue.state == QualityState.REJECTED for issue in issues):
                summary.facts_rejected += len(filing.facts); summary.errors.append(f"rejected filing {filing.source_filing_id}")
                continue
            if existing is None:
                filing_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{filing.source_code}:{filing.source_filing_id}:{filing.revision_number}"))
                existing = FinancialFilingRow(filing_id=filing_id, company_id=filing.company_id,
                    instrument_id=filing.instrument_id, source_id=source.source_id,
                    source_filing_id=filing.source_filing_id, filing_type=filing.filing_type,
                    fiscal_year=filing.period.fiscal_year, fiscal_quarter=filing.period.fiscal_quarter,
                    period_type=filing.period.period_type.value, period_start=filing.period.period_start,
                    period_end=filing.period.period_end, filing_date=filing.filing_date,
                    publication_timestamp=filing.publication_timestamp, audited_status=filing.audited_status,
                    consolidation_basis=filing.basis.value, revision_number=filing.revision_number,
                    currency=filing.currency, original_unit=filing.original_unit, source_url=filing.source_url,
                    retrieved_at=filing.retrieved_at, normalized_at=datetime.now(timezone.utc),
                    raw_payload_hash=filing.raw_payload_hash,
                    quality_status="valid_with_warning" if issues else "valid",
                    warning_state="; ".join(issue.message for issue in issues) or None)
                if filing.restates_source_filing_id:
                    predecessor = session.scalar(select(FinancialFilingRow).where(
                        FinancialFilingRow.source_id == source.source_id,
                        FinancialFilingRow.source_filing_id == filing.restates_source_filing_id,
                    ).order_by(FinancialFilingRow.revision_number.desc()).limit(1))
                    if predecessor is None:
                        summary.errors.append(f"orphan restatement {filing.source_filing_id}")
                        summary.facts_rejected += len(filing.facts)
                        continue
                    existing.restates_filing_id = predecessor.filing_id
                    predecessor.quality_status = "superseded"
                    summary.restatements_detected += 1
                session.add(existing); session.flush(); summary.filings_created += 1
            elif existing.raw_payload_hash == filing.raw_payload_hash:
                summary.filings_unchanged += 1
            else:
                summary.errors.append(f"revision collision for {filing.source_filing_id}; increment revision_number")
                summary.facts_rejected += len(filing.facts); continue
            summary.facts_read += len(filing.facts)
            for fact in filing.facts:
                definition = FINANCIAL_METRICS.get(fact.metric_id)
                if definition is None:
                    summary.unknown_source_fields += 1; summary.facts_rejected += 1
                    session.add(FinancialQualityIssueRow(filing_id=existing.filing_id,
                        instrument_id=filing.instrument_id, metric_id=fact.metric_id,
                        issue_code="unknown_metric", severity="error",
                        message="Source fact did not map to the versioned metric dictionary.",
                        quality_status="rejected"))
                    continue
                if fact.value is None:
                    continue
                try:
                    normalized, factor = normalize_decimal(fact.value, fact.unit)
                except ValueError:
                    summary.unit_anomalies += 1; summary.facts_rejected += 1
                    session.add(FinancialQualityIssueRow(filing_id=existing.filing_id,
                        instrument_id=filing.instrument_id, metric_id=fact.metric_id,
                        issue_code="unresolved_unit", severity="error",
                        message="Source unit was unresolved or unsupported; original fact was not published.",
                        quality_status="rejected"))
                    continue
                fact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{existing.filing_id}:{fact.metric_id}:{fact.period.period_end}:{fact.source_field}"))
                row = session.get(FinancialFactRow, fact_id)
                if row is not None:
                    summary.facts_unchanged += 1; continue
                session.add(FinancialFactRow(fact_id=fact_id, filing_id=existing.filing_id,
                    company_id=filing.company_id, metric_id=fact.metric_id,
                    normalized_value=normalized, original_value=fact.value,
                    normalized_unit=definition.unit, original_unit=fact.unit,
                    conversion_factor=factor, currency=fact.currency or filing.currency,
                    period_type=fact.period.period_type.value, period_start=fact.period.period_start,
                    period_end=fact.period.period_end, instant_date=fact.period.instant_date,
                    consolidation_basis=fact.basis.value, audited_status=filing.audited_status,
                    source_field=fact.source_field, source_location=fact.source_location,
                    is_derived=fact.is_derived, quality_status="derived" if fact.is_derived else existing.quality_status,
                    created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
                summary.facts_normalized += 1
            for issue in issues:
                session.add(FinancialQualityIssueRow(filing_id=existing.filing_id,
                    instrument_id=filing.instrument_id, metric_id=issue.metric_id,
                    issue_code=issue.code, severity=issue.severity, message=issue.message,
                    quality_status=issue.state.value))
            imported_companies.add(filing.company_id)
        summary.companies_imported = len(imported_companies)
        summary.companies_skipped = summary.companies_attempted - summary.companies_imported
        if dry_run:
            session.rollback()
        elif manage_transaction:
            session.commit()
    except Exception:
        session.rollback(); raise
    return summary
