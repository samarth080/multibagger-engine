"""Read/write boundary for dataset builds and public financial summaries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mbe.db.models import (
    FinancialDatasetBuildRow, FinancialFactRow, FinancialFilingRow,
    FinancialMetricSnapshotRow, FinancialQualityIssueRow,
)


def persist_projection_build(session: Session, build: dict, projections: list[dict]) -> str:
    build_id = build["financial_dataset_build_id"]
    if session.get(FinancialDatasetBuildRow, build_id):
        return build_id
    cutoff = datetime.fromisoformat(build["source_cutoff"])
    row = FinancialDatasetBuildRow(financial_dataset_build_id=build_id,
        schema_version=build["schema_version"], metric_definition_version=build["metric_definition_version"],
        source_cutoff=cutoff, built_at=datetime.fromisoformat(build["built_at"]),
        companies_attempted=build["companies_attempted"], companies_completed=build["companies_completed"],
        companies_failed=build["companies_failed"], filings_processed=0, facts_processed=0,
        facts_rejected=0, derived_metrics_calculated=sum(
            value is not None for projection in projections for value in projection["values"].values()),
        coverage_summary=build["coverage"], quality_summary={
            **build["quality_summary"],
            "reconciliation": build.get("reconciliation_summary", {}),
            "selected_sources": build.get("selected_source_distribution", {}),
            "public_metric_eligibility": build.get("public_metric_eligibility", {}),
        },
        configuration_hash=build["configuration_hash"], source_versions={
            **build["source_versions"],
            "official_manifest": {
                "official_discovery_cutoff": build.get("official_discovery_cutoff"),
                "compatibility_source_cutoff": build.get("compatibility_source_cutoff"),
                "official_filing_count": build.get("official_filing_count", 0),
                "attachment_count": build.get("attachment_count", 0),
                "parser_versions": build.get("parser_versions", {}),
                "reconciliation_rule_version": build.get("reconciliation_rule_version"),
                "source_selection_rule_version": build.get("source_selection_rule_version"),
                "official_coverage": build.get("official_coverage", {}),
                "compatibility_fallback_coverage": build.get("compatibility_fallback_coverage", {}),
                "conflict_count": build.get("conflict_count", 0),
                "unknown_basis_count": build.get("unknown_basis_count", 0),
                "unsupported_format_count": build.get("unsupported_format_count", 0),
            },
        },
        status=build["status"], notes="; ".join(build.get("warnings", [])))
    session.add(row)
    for projection in projections:
        period_end = date(projection["latest_annual_fiscal_year"], 3, 31)
        for metric_id, value in projection["values"].items():
            if value is None:
                continue
            session.add(FinancialMetricSnapshotRow(financial_dataset_build_id=build_id,
                instrument_id=projection["instrument_id"], metric_id=metric_id,
                value=Decimal(str(value)), unit="ratio", period_type="annual",
                period_end=period_end, consolidation_basis=projection["basis"],
                quality_status=projection["quality_status"],
                metric_definition_version=build["metric_definition_version"],
                source_fact_ids=[], calculated_at=datetime.now(timezone.utc), data_cutoff=cutoff))
    session.commit()
    return build_id


def latest_build(session: Session, *, as_of: datetime | None = None):
    stmt = select(FinancialDatasetBuildRow).where(FinancialDatasetBuildRow.status == "complete")
    if as_of is not None:
        stmt = stmt.where(FinancialDatasetBuildRow.source_cutoff <= as_of)
    return session.scalar(stmt.order_by(FinancialDatasetBuildRow.built_at.desc()).limit(1))


def coverage(session: Session) -> dict | None:
    build = latest_build(session)
    if not build:
        return None
    quality = dict(session.execute(select(FinancialMetricSnapshotRow.quality_status, func.count()).where(
        FinancialMetricSnapshotRow.financial_dataset_build_id == build.financial_dataset_build_id
    ).group_by(FinancialMetricSnapshotRow.quality_status)).all())
    from mbe.financials.official_repository import official_coverage
    return {"financial_dataset_build_id": build.financial_dataset_build_id,
            "schema_version": build.schema_version, "metric_definition_version": build.metric_definition_version,
            "source_cutoff": build.source_cutoff, "built_at": build.built_at,
            "companies_attempted": build.companies_attempted, "companies_completed": build.companies_completed,
            "companies_failed": build.companies_failed, "metric_coverage": build.coverage_summary,
            "quality_state_counts": quality, "source_distribution": build.source_versions,
            "official_ingestion": official_coverage(session),
            "warnings": [build.notes] if build.notes else []}


def instrument_summary(session: Session, instrument_id: str, *, metrics: list[str], max_periods: int = 5,
                       period_type: str | None = None, basis: str | None = None,
                       as_of: datetime | None = None) -> dict | None:
    build = latest_build(session, as_of=as_of)
    if not build:
        return None
    snapshots = session.scalars(select(FinancialMetricSnapshotRow).where(
        FinancialMetricSnapshotRow.financial_dataset_build_id == build.financial_dataset_build_id,
        FinancialMetricSnapshotRow.instrument_id == instrument_id,
        FinancialMetricSnapshotRow.metric_id.in_(metrics))).all()
    filing_stmt = select(FinancialFilingRow).where(FinancialFilingRow.instrument_id == instrument_id)
    if as_of is not None:
        filing_stmt = filing_stmt.where(
            (FinancialFilingRow.publication_timestamp.is_(None) & (FinancialFilingRow.filing_date <= as_of.date())) |
            (FinancialFilingRow.publication_timestamp <= as_of)
        )
    if period_type:
        filing_stmt = filing_stmt.where(FinancialFilingRow.period_type == period_type)
    if basis:
        filing_stmt = filing_stmt.where(FinancialFilingRow.consolidation_basis == basis)
    else:
        available = set(session.scalars(select(FinancialFilingRow.consolidation_basis).where(
            FinancialFilingRow.instrument_id == instrument_id
        )).all())
        selected_basis = next((item for item in ("consolidated", "standalone", "unknown") if item in available), None)
        if selected_basis:
            filing_stmt = filing_stmt.where(FinancialFilingRow.consolidation_basis == selected_basis)
    filings = session.scalars(filing_stmt.order_by(FinancialFilingRow.period_end.desc(), FinancialFilingRow.revision_number.desc()).limit(max_periods)).all()
    if not snapshots and not filings:
        return None
    filing_ids = [item.filing_id for item in filings]
    facts = session.scalars(select(FinancialFactRow).where(
        FinancialFactRow.filing_id.in_(filing_ids), FinancialFactRow.metric_id.in_(metrics)
    ).order_by(FinancialFactRow.period_end.desc())).all() if filing_ids else []
    issues = session.scalars(select(FinancialQualityIssueRow).where(
        FinancialQualityIssueRow.instrument_id == instrument_id
    ).order_by(FinancialQualityIssueRow.created_at.desc()).limit(20)).all()
    return {"instrument_id": instrument_id,
            "selected_source": "yahoo_compatibility",
            "source_quality_tier": "B",
            "source_selection_status": "approved_metric_specific_fallback",
            "source_selection_reason": "Persisted public projections use the approved compatibility fallback unless an accepted official selection explicitly replaces them.",
            "selection_policy_version": "2026-08-01.2",
            "basis": snapshots[0].consolidation_basis if snapshots else "unknown",
            "quality_status": snapshots[0].quality_status if snapshots else "unavailable",
            "reconciliation_status": "not_reconciled",
            "financial_dataset_build_id": build.financial_dataset_build_id,
            "metric_definition_version": build.metric_definition_version,
            "data_cutoff": build.source_cutoff.isoformat(),
            "financial_dataset_build": {
                "financial_dataset_build_id": build.financial_dataset_build_id,
                "metric_definition_version": build.metric_definition_version,
                "source_cutoff": build.source_cutoff, "built_at": build.built_at},
            "derived_metrics": [{"metric_id": row.metric_id, "value": float(row.value), "unit": row.unit,
                "period_type": row.period_type, "period_end": row.period_end,
                "basis": row.consolidation_basis, "quality_status": row.quality_status}
                for row in snapshots],
            "filings": [{"filing_id": row.filing_id, "source_filing_id": row.source_filing_id,
                "filing_type": row.filing_type, "period_type": row.period_type, "period_end": row.period_end,
                "filing_date": row.filing_date, "publication_timestamp": row.publication_timestamp,
                "basis": row.consolidation_basis, "audited_status": row.audited_status,
                "revision_number": row.revision_number, "restates_filing_id": row.restates_filing_id,
                "currency": row.currency, "quality_status": row.quality_status, "source_url": row.source_url}
                for row in filings],
            "facts": [{"fact_id": row.fact_id, "metric_id": row.metric_id,
                "value": float(row.normalized_value), "unit": row.normalized_unit,
                "currency": row.currency, "period_type": row.period_type, "period_end": row.period_end,
                "basis": row.consolidation_basis, "quality_status": row.quality_status,
                "source_field": row.source_field}
                for row in facts],
            "quality_warnings": [{"code": row.issue_code, "severity": row.severity,
                "message": row.message, "metric_id": row.metric_id} for row in issues],
            "missing_metrics": sorted(set(metrics) - {r.metric_id for r in snapshots} - {r.metric_id for r in facts})}


def metric_matrix(session: Session, *, metrics: list[str]) -> tuple[dict[str, dict[str, float]], FinancialDatasetBuildRow | None]:
    """Return one-build public metric values without per-instrument queries."""
    build = latest_build(session)
    if not build:
        return {}, None
    rows = session.scalars(select(FinancialMetricSnapshotRow).where(
        FinancialMetricSnapshotRow.financial_dataset_build_id == build.financial_dataset_build_id,
        FinancialMetricSnapshotRow.metric_id.in_(metrics),
    )).all()
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        result.setdefault(row.instrument_id, {})[row.metric_id] = float(row.value)
    return result, build
