"""SQLAlchemy schema for canonical identity, lineage and scored builds."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    JSON, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mbe.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeRow(Base):
    __tablename__ = "exchanges"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mic: Mapped[str | None] = mapped_column(String(4), unique=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)


class SectorRow(Base):
    __tablename__ = "sectors"
    sector_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)


class IndustryRow(Base):
    __tablename__ = "industries"
    industry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.sector_id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sub_industry: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint(
            "sector_id", "name", "sub_industry", name="uq_industries_classification"
        ),
    )


class DataSourceRow(Base):
    __tablename__ = "data_sources"
    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    limitations: Mapped[str | None] = mapped_column(Text)


class CompanyRow(Base):
    __tablename__ = "companies"
    company_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    display_name: Mapped[str | None] = mapped_column(String(300))
    current_legal_name: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (Index("ix_companies_display_name", "display_name"),)


class InstrumentRow(Base):
    __tablename__ = "instruments"
    instrument_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.company_id"))
    security_type: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.sector_id"))
    industry_id: Mapped[int | None] = mapped_column(ForeignKey("industries.industry_id"))
    market_cap_category: Mapped[str | None] = mapped_column(String(40))
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class InstrumentListingRow(Base):
    __tablename__ = "instrument_listings"
    listing_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id", ondelete="CASCADE"), nullable=False)
    exchange_code: Mapped[str] = mapped_column(ForeignKey("exchanges.code"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    bse_code: Mapped[str | None] = mapped_column(String(6))
    isin: Mapped[str | None] = mapped_column(String(12))
    exchange_segment: Mapped[str | None] = mapped_column(String(40))
    exchange_series: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    listing_date: Mapped[date | None] = mapped_column(Date)
    delisting_date: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_sme: Mapped[bool | None] = mapped_column(Boolean)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        CheckConstraint("bse_code IS NULL OR length(bse_code) = 6", name="bse_code_length"),
        CheckConstraint("isin IS NULL OR length(isin) = 12", name="isin_length"),
        Index("ix_listings_exchange_symbol", "exchange_code", "symbol"),
        Index("ix_listings_bse_code", "bse_code"),
        Index("ix_listings_isin", "isin"),
        Index("ix_listings_status", "status"),
        Index(
            "uq_listings_current_exchange_symbol", "exchange_code", "symbol",
            unique=True, sqlite_where=text("valid_to IS NULL"),
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index(
            "uq_listings_one_primary", "instrument_id", unique=True,
            sqlite_where=text("valid_to IS NULL AND is_primary = 1"),
            postgresql_where=text("valid_to IS NULL AND is_primary"),
        ),
    )


class InstrumentAliasRow(Base):
    __tablename__ = "instrument_aliases"
    alias_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id", ondelete="CASCADE"), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(300), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "alias_type", "normalized_value",
            name="uq_instrument_aliases_identity",
        ),
        Index("ix_aliases_normalized_value", "normalized_value"),
    )


class ProviderSymbolRow(Base):
    __tablename__ = "provider_symbols"
    mapping_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_instrument_id: Mapped[str | None] = mapped_column(String(160))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))
    __table_args__ = (
        Index("ix_provider_symbols_instrument_provider", "instrument_id", "provider"),
        Index(
            "uq_provider_symbols_current", "provider", "provider_symbol",
            unique=True, sqlite_where=text("valid_to IS NULL"),
            postgresql_where=text("valid_to IS NULL"),
        ),
    )


class IndexRow(Base):
    __tablename__ = "indices"
    index_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(16), nullable=False)


class IndexMembershipRow(Base):
    __tablename__ = "index_memberships"
    membership_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_id: Mapped[str] = mapped_column(ForeignKey("indices.index_id", ondelete="CASCADE"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id", ondelete="CASCADE"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))
    __table_args__ = (
        UniqueConstraint(
            "index_id", "instrument_id", "effective_from",
            name="uq_index_memberships_identity",
        ),
        Index("ix_memberships_instrument", "instrument_id", "effective_to"),
    )


class ImportRunRow(Base):
    __tablename__ = "import_runs"
    import_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(120))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSON)
    source_hash: Mapped[str | None] = mapped_column(String(64))


class ImportIssueRow(Base):
    __tablename__ = "import_issues"
    issue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_run_id: Mapped[str] = mapped_column(ForeignKey("import_runs.import_run_id", ondelete="CASCADE"), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(200))
    issue_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_record: Mapped[dict | None] = mapped_column(JSON)
    resolution_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unresolved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (Index("ix_import_issues_status", "resolution_status", "issue_type"),)


class QuoteSnapshotRow(Base):
    __tablename__ = "quote_snapshots"
    quote_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    currency: Mapped[str | None] = mapped_column(String(3))
    market_status: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness_state: Mapped[str] = mapped_column(String(24), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (Index("ix_quotes_instrument_retrieved", "instrument_id", "retrieved_at"),)


class ModelBuildRow(Base):
    __tablename__ = "model_builds"
    build_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    factor_config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    factor_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    universe_name: Mapped[str] = mapped_column(String(120), nullable=False)
    universe_version: Mapped[str] = mapped_column(String(120), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    attempted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    scored_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_data_version: Mapped[str | None] = mapped_column(String(160))
    validation_status: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("attempted_count >= 0", name="attempted_nonnegative"),
        CheckConstraint("scored_count >= 0", name="scored_nonnegative"),
        CheckConstraint("failed_count >= 0", name="failed_nonnegative"),
        Index("ix_model_builds_latest", "status", "built_at"),
    )


class ScoreSnapshotRow(Base):
    __tablename__ = "score_snapshots"
    score_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    build_id: Mapped[str] = mapped_column(ForeignKey("model_builds.build_id", ondelete="CASCADE"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    multibagger_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    investment_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    investability: Mapped[str] = mapped_column(String(80), nullable=False)
    positive_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    red_flag_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_quality: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    has_missing_data: Mapped[bool] = mapped_column(Boolean, nullable=False)
    technical_trend: Mapped[str | None] = mapped_column(String(40))
    main_positive_signal: Mapped[str | None] = mapped_column(Text)
    main_risk: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "build_id", "instrument_id", name="uq_score_snapshots_build_instrument"
        ),
        UniqueConstraint("build_id", "rank", name="uq_score_snapshots_build_rank"),
        CheckConstraint("rank > 0", name="rank_positive"),
        Index("ix_scores_build_multibagger", "build_id", "multibagger_score"),
        Index("ix_scores_build_trend", "build_id", "technical_trend"),
        Index("ix_scores_instrument_created", "instrument_id", "created_at"),
    )


class ScoreComponentRow(Base):
    __tablename__ = "score_components"
    component_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("score_snapshots.score_id", ondelete="CASCADE"), nullable=False)
    component_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    contribution: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "score_id", "component_name", name="uq_score_components_identity"
        ),
    )


class FreshnessRow(Base):
    __tablename__ = "data_freshness"
    freshness_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String(100), nullable=False)
    partition_key: Mapped[str] = mapped_column(String(160), nullable=False, default="global")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))
    import_run_id: Mapped[str | None] = mapped_column(ForeignKey("import_runs.import_run_id"))
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_version: Mapped[str | None] = mapped_column(String(160))
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    warning: Mapped[str | None] = mapped_column(Text)
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint(
            "dataset", "partition_key", name="uq_data_freshness_partition"
        ),
        Index("ix_freshness_state", "state", "normalized_at"),
    )


class FinancialDatasetBuildRow(Base):
    __tablename__ = "financial_dataset_builds"
    financial_dataset_build_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(24), nullable=False)
    metric_definition_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    companies_attempted: Mapped[int] = mapped_column(Integer, nullable=False)
    companies_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    companies_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    filings_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    facts_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    facts_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derived_metrics_calculated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    quality_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("ix_financial_builds_latest", "status", "built_at"),)


class FinancialFilingRow(Base):
    __tablename__ = "financial_filings"
    filing_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.instrument_id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    import_run_id: Mapped[str | None] = mapped_column(ForeignKey("import_runs.import_run_id"))
    source_filing_id: Mapped[str] = mapped_column(String(240), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(48), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date)
    publication_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audited_status: Mapped[str] = mapped_column(String(24), nullable=False)
    consolidation_basis: Mapped[str] = mapped_column(String(24), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    restates_filing_id: Mapped[str | None] = mapped_column(ForeignKey("financial_filings.filing_id"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    original_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    warning_state: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("source_id", "source_filing_id", "revision_number", name="uq_financial_filings_source_revision"),
        Index("ix_financial_filings_company_period", "company_id", "period_end", "consolidation_basis"),
        Index("ix_financial_filings_instrument_period", "instrument_id", "period_end"),
    )


class FinancialFactRow(Base):
    __tablename__ = "financial_facts"
    fact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filing_id: Mapped[str] = mapped_column(ForeignKey("financial_filings.filing_id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    metric_id: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_value: Mapped[Decimal] = mapped_column(Numeric(38, 8), nullable=False)
    original_value: Mapped[Decimal] = mapped_column(Numeric(38, 8), nullable=False)
    normalized_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    original_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    instant_date: Mapped[date | None] = mapped_column(Date)
    consolidation_basis: Mapped[str] = mapped_column(String(24), nullable=False)
    audited_status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_field: Mapped[str] = mapped_column(String(240), nullable=False)
    source_location: Mapped[str | None] = mapped_column(Text)
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (
        UniqueConstraint("filing_id", "metric_id", "period_end", "consolidation_basis", "source_field", name="uq_financial_facts_identity"),
        Index("ix_financial_facts_company_metric_period", "company_id", "metric_id", "period_end"),
    )


class FinancialMetricSnapshotRow(Base):
    __tablename__ = "financial_metric_snapshots"
    metric_snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_dataset_build_id: Mapped[str] = mapped_column(ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    metric_id: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 12), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    consolidation_basis: Mapped[str] = mapped_column(String(24), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    metric_definition_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_fact_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("financial_dataset_build_id", "instrument_id", "metric_id", name="uq_financial_metric_snapshots_identity"),
        Index("ix_financial_metrics_build_metric_value", "financial_dataset_build_id", "metric_id", "value"),
        Index("ix_financial_metrics_instrument_period", "instrument_id", "metric_id", "period_end"),
    )


class FinancialQualityIssueRow(Base):
    __tablename__ = "financial_quality_issues"
    issue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[str | None] = mapped_column(ForeignKey("financial_filings.filing_id", ondelete="CASCADE"))
    financial_dataset_build_id: Mapped[str | None] = mapped_column(ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE"))
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.instrument_id"))
    metric_id: Mapped[str | None] = mapped_column(String(80))
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (Index("ix_financial_issues_build_severity", "financial_dataset_build_id", "severity"),)


class OfficialFilingSourceRow(Base):
    __tablename__ = "official_filing_sources"
    source_record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_filing_id: Mapped[str] = mapped_column(String(240), nullable=False)
    canonical_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    nse_symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12))
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(48), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    publication_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    basis_hint: Mapped[str] = mapped_column(String(24), nullable=False)
    audited_status: Mapped[str] = mapped_column(String(24), nullable=False)
    revision_hint: Mapped[str] = mapped_column(String(24), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    raw_metadata_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_status: Mapped[str] = mapped_column(String(24), nullable=False, default="discovered")
    __table_args__ = (
        UniqueConstraint("source_id", "source_filing_id", "raw_metadata_hash", name="uq_official_sources_metadata_revision"),
        CheckConstraint("length(raw_metadata_hash) = 64", name="official_source_hash_length"),
        CheckConstraint("length(raw_response_hash) = 64", name="official_response_hash_length"),
        CheckConstraint("length(canonical_identity_hash) = 64", name="official_identity_hash_length"),
        Index("ix_official_sources_instrument_filed", "instrument_id", "publication_timestamp"),
        Index("ix_official_sources_identity", "canonical_identity_hash"),
        Index("ix_official_sources_source_filing", "source_id", "source_filing_id"),
    )


class OfficialFilingAttachmentRow(Base):
    __tablename__ = "official_filing_attachments"
    attachment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(ForeignKey("official_filing_sources.source_record_id", ondelete="CASCADE"), nullable=False)
    canonical_filing_id: Mapped[str | None] = mapped_column(ForeignKey("financial_filings.filing_id"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    declared_content_type: Mapped[str | None] = mapped_column(String(160))
    detected_content_type: Mapped[str | None] = mapped_column(String(160))
    attachment_format: Mapped[str] = mapped_column(String(32), nullable=False)
    content_length: Mapped[int | None] = mapped_column(Integer)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    etag: Mapped[str | None] = mapped_column(String(240))
    last_modified: Mapped[str | None] = mapped_column(String(120))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cache_state: Mapped[str] = mapped_column(String(24), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(24), nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(40))
    template_id: Mapped[str | None] = mapped_column(String(100))
    template_version: Mapped[str | None] = mapped_column(String(40))
    recognition_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    unsupported_reason: Mapped[str | None] = mapped_column(Text)
    quarantine_code: Mapped[str | None] = mapped_column(String(80))
    warning_summary: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("source_record_id", "sequence", name="uq_official_attachments_sequence"),
        CheckConstraint("sequence > 0", name="official_attachment_sequence_positive"),
        CheckConstraint("content_length IS NULL OR content_length >= 0", name="official_attachment_length_nonnegative"),
        Index("ix_official_attachments_checksum", "checksum_sha256"),
        Index("ix_official_attachments_parse_status", "parse_status", "attachment_format"),
    )


class FinancialFilingRelationshipRow(Base):
    __tablename__ = "financial_filing_relationships"
    relationship_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_filing_id: Mapped[str] = mapped_column(ForeignKey("financial_filings.filing_id", ondelete="CASCADE"), nullable=False)
    to_filing_id: Mapped[str] = mapped_column(ForeignKey("financial_filings.filing_id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("from_filing_id", "to_filing_id", "relationship_type", name="uq_financial_filing_relationship"),
        CheckConstraint("from_filing_id <> to_filing_id", name="financial_relationship_distinct_filings"),
        Index("ix_financial_relationships_target", "to_filing_id", "relationship_type"),
    )


class FinancialReconciliationRow(Base):
    __tablename__ = "financial_reconciliations"
    reconciliation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    financial_dataset_build_id: Mapped[str | None] = mapped_column(ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE"))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    metric_id: Mapped[str] = mapped_column(String(80), nullable=False)
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    consolidation_basis: Mapped[str] = mapped_column(String(24), nullable=False)
    official_fact_id: Mapped[str | None] = mapped_column(ForeignKey("financial_facts.fact_id"))
    official_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    compatibility_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    absolute_difference: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    percentage_difference: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    reconciliation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    selected_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    selected_source: Mapped[str | None] = mapped_column(String(80))
    selection_reason: Mapped[str] = mapped_column(Text, nullable=False)
    rejected_alternatives: Mapped[list] = mapped_column(JSON, nullable=False)
    reconciliation_rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    selection_rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("financial_dataset_build_id", "instrument_id", "metric_id", "period_end", "consolidation_basis", name="uq_financial_reconciliation_build_metric"),
        Index("ix_financial_reconciliations_status", "reconciliation_status", "metric_id"),
        Index("ix_financial_reconciliations_instrument_period", "instrument_id", "metric_id", "period_end"),
    )


class FinancialSourceSelectionRow(Base):
    __tablename__ = "financial_source_selections"
    selection_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    financial_dataset_build_id: Mapped[str] = mapped_column(ForeignKey("financial_dataset_builds.financial_dataset_build_id", ondelete="CASCADE"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.instrument_id"), nullable=False)
    metric_id: Mapped[str] = mapped_column(String(80), nullable=False)
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    consolidation_basis: Mapped[str] = mapped_column(String(24), nullable=False)
    selected_fact_id: Mapped[str | None] = mapped_column(ForeignKey("financial_facts.fact_id"))
    reconciliation_id: Mapped[str | None] = mapped_column(ForeignKey("financial_reconciliations.reconciliation_id"))
    selected_source: Mapped[str] = mapped_column(String(80), nullable=False)
    selected_value: Mapped[Decimal] = mapped_column(Numeric(38, 12), nullable=False)
    selection_rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    selection_reason: Mapped[str] = mapped_column(Text, nullable=False)
    rejected_alternatives: Mapped[list] = mapped_column(JSON, nullable=False)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("financial_dataset_build_id", "instrument_id", "metric_id", "period_end", "consolidation_basis", name="uq_financial_source_selection"),
        Index("ix_financial_selections_lookup", "financial_dataset_build_id", "metric_id", "instrument_id"),
    )
