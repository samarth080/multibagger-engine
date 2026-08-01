"""official NSE filing ingestion and reconciliation

Revision ID: 20260801_0004
Revises: 20260801_0003
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0004"
down_revision = "20260801_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "official_filing_sources",
        sa.Column("source_record_id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.instrument_id"), nullable=False),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.source_id"), nullable=False),
        sa.Column("source_filing_id", sa.String(240), nullable=False),
        sa.Column("canonical_identity_hash", sa.String(64), nullable=False),
        sa.Column("company_name", sa.String(300), nullable=False),
        sa.Column("nse_symbol", sa.String(40), nullable=False),
        sa.Column("isin", sa.String(12)),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("filing_type", sa.String(48), nullable=False),
        sa.Column("filing_date", sa.Date, nullable=False),
        sa.Column("publication_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(24), nullable=False),
        sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("fiscal_quarter", sa.Integer),
        sa.Column("basis_hint", sa.String(24), nullable=False),
        sa.Column("audited_status", sa.String(24), nullable=False),
        sa.Column("revision_hint", sa.String(24), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("raw_metadata_hash", sa.String(64), nullable=False),
        sa.Column("raw_response_hash", sa.String(64), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_status", sa.String(24), nullable=False, server_default="discovered"),
        sa.UniqueConstraint("source_id", "source_filing_id", "raw_metadata_hash", name="uq_official_sources_metadata_revision"),
        sa.CheckConstraint("length(raw_metadata_hash) = 64", name="official_source_hash_length"),
        sa.CheckConstraint("length(raw_response_hash) = 64", name="official_response_hash_length"),
        sa.CheckConstraint("length(canonical_identity_hash) = 64", name="official_identity_hash_length"),
    )
    op.create_index("ix_official_sources_instrument_filed", "official_filing_sources", ["instrument_id", "publication_timestamp"])
    op.create_index("ix_official_sources_identity", "official_filing_sources", ["canonical_identity_hash"])
    op.create_index("ix_official_sources_source_filing", "official_filing_sources", ["source_id", "source_filing_id"])

    op.create_table(
        "official_filing_attachments",
        sa.Column("attachment_id", sa.String(36), primary_key=True),
        sa.Column("source_record_id", sa.String(36), sa.ForeignKey("official_filing_sources.source_record_id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_filing_id", sa.String(36), sa.ForeignKey("financial_filings.filing_id")),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("filename", sa.String(180), nullable=False),
        sa.Column("declared_content_type", sa.String(160)),
        sa.Column("detected_content_type", sa.String(160)),
        sa.Column("attachment_format", sa.String(32), nullable=False),
        sa.Column("content_length", sa.Integer),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("etag", sa.String(240)),
        sa.Column("last_modified", sa.String(120)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("cache_state", sa.String(24), nullable=False),
        sa.Column("parse_status", sa.String(24), nullable=False),
        sa.Column("parser_version", sa.String(40)),
        sa.Column("template_id", sa.String(100)),
        sa.Column("template_version", sa.String(40)),
        sa.Column("recognition_confidence", sa.Numeric(5, 4)),
        sa.Column("unsupported_reason", sa.Text),
        sa.Column("quarantine_code", sa.String(80)),
        sa.Column("warning_summary", sa.Text),
        sa.UniqueConstraint("source_record_id", "sequence", name="uq_official_attachments_sequence"),
        sa.CheckConstraint("sequence > 0", name="official_attachment_sequence_positive"),
        sa.CheckConstraint("content_length IS NULL OR content_length >= 0", name="official_attachment_length_nonnegative"),
    )
    op.create_index("ix_official_attachments_checksum", "official_filing_attachments", ["checksum_sha256"])
    op.create_index("ix_official_attachments_parse_status", "official_filing_attachments", ["parse_status", "attachment_format"])

    op.create_table(
        "financial_filing_relationships",
        sa.Column("relationship_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("from_filing_id", sa.String(36), sa.ForeignKey("financial_filings.filing_id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_filing_id", sa.String(36), sa.ForeignKey("financial_filings.filing_id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(40), nullable=False),
        sa.Column("evidence", sa.Text, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("from_filing_id", "to_filing_id", "relationship_type", name="uq_financial_filing_relationship"),
        sa.CheckConstraint("from_filing_id <> to_filing_id", name="financial_relationship_distinct_filings"),
    )
    op.create_index("ix_financial_relationships_target", "financial_filing_relationships", ["to_filing_id", "relationship_type"])

    op.create_table(
        "financial_reconciliations",
        sa.Column("reconciliation_id", sa.String(36), primary_key=True),
        sa.Column("financial_dataset_build_id", sa.String(36), sa.ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE")),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.instrument_id"), nullable=False),
        sa.Column("metric_id", sa.String(80), nullable=False),
        sa.Column("period_type", sa.String(24), nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("consolidation_basis", sa.String(24), nullable=False),
        sa.Column("official_fact_id", sa.String(36), sa.ForeignKey("financial_facts.fact_id")),
        sa.Column("official_value", sa.Numeric(38, 12)),
        sa.Column("compatibility_value", sa.Numeric(38, 12)),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("absolute_difference", sa.Numeric(38, 12)),
        sa.Column("percentage_difference", sa.Numeric(38, 12)),
        sa.Column("reconciliation_status", sa.String(40), nullable=False),
        sa.Column("selected_value", sa.Numeric(38, 12)),
        sa.Column("selected_source", sa.String(80)),
        sa.Column("selection_reason", sa.Text, nullable=False),
        sa.Column("rejected_alternatives", sa.JSON, nullable=False),
        sa.Column("reconciliation_rule_version", sa.String(40), nullable=False),
        sa.Column("selection_rule_version", sa.String(40), nullable=False),
        sa.Column("source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("financial_dataset_build_id", "instrument_id", "metric_id", "period_end", "consolidation_basis", name="uq_financial_reconciliation_build_metric"),
    )
    op.create_index("ix_financial_reconciliations_status", "financial_reconciliations", ["reconciliation_status", "metric_id"])
    op.create_index("ix_financial_reconciliations_instrument_period", "financial_reconciliations", ["instrument_id", "metric_id", "period_end"])

    op.create_table(
        "financial_source_selections",
        sa.Column("selection_id", sa.String(36), primary_key=True),
        sa.Column("financial_dataset_build_id", sa.String(36), sa.ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.instrument_id"), nullable=False),
        sa.Column("metric_id", sa.String(80), nullable=False),
        sa.Column("period_type", sa.String(24), nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("consolidation_basis", sa.String(24), nullable=False),
        sa.Column("selected_fact_id", sa.String(36), sa.ForeignKey("financial_facts.fact_id")),
        sa.Column("reconciliation_id", sa.String(36), sa.ForeignKey("financial_reconciliations.reconciliation_id")),
        sa.Column("selected_source", sa.String(80), nullable=False),
        sa.Column("selected_value", sa.Numeric(38, 12), nullable=False),
        sa.Column("selection_rule_version", sa.String(40), nullable=False),
        sa.Column("selection_reason", sa.Text, nullable=False),
        sa.Column("rejected_alternatives", sa.JSON, nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("financial_dataset_build_id", "instrument_id", "metric_id", "period_end", "consolidation_basis", name="uq_financial_source_selection"),
    )
    op.create_index("ix_financial_selections_lookup", "financial_source_selections", ["financial_dataset_build_id", "metric_id", "instrument_id"])


def downgrade() -> None:
    op.drop_table("financial_source_selections")
    op.drop_table("financial_reconciliations")
    op.drop_table("financial_filing_relationships")
    op.drop_table("official_filing_attachments")
    op.drop_table("official_filing_sources")
