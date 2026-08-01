"""normalized financial lineage

Revision ID: 20260801_0003
Revises: 20260801_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260801_0003"
down_revision = "20260801_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("financial_dataset_builds",
        sa.Column("financial_dataset_build_id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(24), nullable=False),
        sa.Column("metric_definition_version", sa.String(40), nullable=False),
        sa.Column("source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Numeric(16,3)),
        sa.Column("companies_attempted", sa.Integer, nullable=False), sa.Column("companies_completed", sa.Integer, nullable=False), sa.Column("companies_failed", sa.Integer, nullable=False),
        sa.Column("filings_processed", sa.Integer, nullable=False, server_default="0"), sa.Column("facts_processed", sa.Integer, nullable=False, server_default="0"), sa.Column("facts_rejected", sa.Integer, nullable=False, server_default="0"), sa.Column("derived_metrics_calculated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("coverage_summary", sa.JSON, nullable=False), sa.Column("quality_summary", sa.JSON, nullable=False), sa.Column("configuration_hash", sa.String(64), nullable=False), sa.Column("source_versions", sa.JSON, nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("notes", sa.Text))
    op.create_index("ix_financial_builds_latest", "financial_dataset_builds", ["status", "built_at"])
    op.create_table("financial_filings",
        sa.Column("filing_id", sa.String(36), primary_key=True), sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.company_id"), nullable=False), sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.instrument_id")), sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.source_id"), nullable=False), sa.Column("import_run_id", sa.String(36), sa.ForeignKey("import_runs.import_run_id")),
        sa.Column("source_filing_id", sa.String(240), nullable=False), sa.Column("filing_type", sa.String(48), nullable=False), sa.Column("fiscal_year", sa.Integer, nullable=False), sa.Column("fiscal_quarter", sa.Integer), sa.Column("period_type", sa.String(24), nullable=False), sa.Column("period_start", sa.Date), sa.Column("period_end", sa.Date, nullable=False), sa.Column("filing_date", sa.Date), sa.Column("publication_timestamp", sa.DateTime(timezone=True)), sa.Column("audited_status", sa.String(24), nullable=False), sa.Column("consolidation_basis", sa.String(24), nullable=False), sa.Column("revision_number", sa.Integer, nullable=False, server_default="1"), sa.Column("restates_filing_id", sa.String(36), sa.ForeignKey("financial_filings.filing_id")), sa.Column("currency", sa.String(3), nullable=False), sa.Column("original_unit", sa.String(32), nullable=False), sa.Column("source_url", sa.Text), sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False), sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False), sa.Column("raw_payload_hash", sa.String(64), nullable=False), sa.Column("quality_status", sa.String(24), nullable=False), sa.Column("warning_state", sa.Text), sa.UniqueConstraint("source_id", "source_filing_id", "revision_number", name="uq_financial_filings_source_revision"))
    op.create_index("ix_financial_filings_company_period", "financial_filings", ["company_id", "period_end", "consolidation_basis"])
    op.create_index("ix_financial_filings_instrument_period", "financial_filings", ["instrument_id", "period_end"])
    op.create_table("financial_facts",
        sa.Column("fact_id", sa.String(36), primary_key=True), sa.Column("filing_id", sa.String(36), sa.ForeignKey("financial_filings.filing_id", ondelete="CASCADE"), nullable=False), sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.company_id"), nullable=False), sa.Column("metric_id", sa.String(80), nullable=False), sa.Column("normalized_value", sa.Numeric(38,8), nullable=False), sa.Column("original_value", sa.Numeric(38,8), nullable=False), sa.Column("normalized_unit", sa.String(32), nullable=False), sa.Column("original_unit", sa.String(32), nullable=False), sa.Column("conversion_factor", sa.Numeric(24,8), nullable=False), sa.Column("currency", sa.String(3)), sa.Column("period_type", sa.String(24), nullable=False), sa.Column("period_start", sa.Date), sa.Column("period_end", sa.Date, nullable=False), sa.Column("instant_date", sa.Date), sa.Column("consolidation_basis", sa.String(24), nullable=False), sa.Column("audited_status", sa.String(24), nullable=False), sa.Column("source_field", sa.String(240), nullable=False), sa.Column("source_location", sa.Text), sa.Column("is_derived", sa.Boolean, nullable=False, server_default=sa.false()), sa.Column("quality_status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("filing_id", "metric_id", "period_end", "consolidation_basis", "source_field", name="uq_financial_facts_identity"))
    op.create_index("ix_financial_facts_company_metric_period", "financial_facts", ["company_id", "metric_id", "period_end"])
    op.create_table("financial_metric_snapshots",
        sa.Column("metric_snapshot_id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("financial_dataset_build_id", sa.String(36), sa.ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE"), nullable=False), sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.instrument_id"), nullable=False), sa.Column("metric_id", sa.String(80), nullable=False), sa.Column("value", sa.Numeric(38,12), nullable=False), sa.Column("unit", sa.String(32), nullable=False), sa.Column("period_type", sa.String(24), nullable=False), sa.Column("period_end", sa.Date, nullable=False), sa.Column("consolidation_basis", sa.String(24), nullable=False), sa.Column("quality_status", sa.String(24), nullable=False), sa.Column("metric_definition_version", sa.String(40), nullable=False), sa.Column("source_fact_ids", sa.JSON, nullable=False), sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("financial_dataset_build_id", "instrument_id", "metric_id", name="uq_financial_metric_snapshots_identity"))
    op.create_index("ix_financial_metrics_build_metric_value", "financial_metric_snapshots", ["financial_dataset_build_id", "metric_id", "value"])
    op.create_index("ix_financial_metrics_instrument_period", "financial_metric_snapshots", ["instrument_id", "metric_id", "period_end"])
    op.create_table("financial_quality_issues",
        sa.Column("issue_id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("filing_id", sa.String(36), sa.ForeignKey("financial_filings.filing_id", ondelete="CASCADE")), sa.Column("financial_dataset_build_id", sa.String(36), sa.ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE")), sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.instrument_id")), sa.Column("metric_id", sa.String(80)), sa.Column("issue_code", sa.String(64), nullable=False), sa.Column("severity", sa.String(16), nullable=False), sa.Column("message", sa.Text, nullable=False), sa.Column("quality_status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_financial_issues_build_severity", "financial_quality_issues", ["financial_dataset_build_id", "severity"])


def downgrade() -> None:
    for table in ("financial_quality_issues", "financial_metric_snapshots", "financial_facts", "financial_filings", "financial_dataset_builds"):
        op.drop_table(table)
