"""Typed contracts for bounded official financial-filing ingestion."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mbe.financials.domain import ConsolidationBasis, FinancialPeriod, SourceFact


OFFICIAL_INGESTION_SCHEMA_VERSION = "1.0"
NSE_DISCOVERY_ADAPTER_VERSION = "2026-08-01.1"
NSE_XBRL_PARSER_VERSION = "2026-08-01.1"
RECONCILIATION_RULE_VERSION = "2026-08-01.1"
SOURCE_SELECTION_RULE_VERSION = "2026-08-01.2"


class AttachmentFormat(StrEnum):
    JSON = "json"
    XBRL_XML = "xbrl_xml"
    CSV = "csv"
    XLS = "xls"
    XLSX = "xlsx"
    HTML = "html"
    TEXT_PDF = "text_pdf"
    IMAGE_PDF = "image_pdf"
    ZIP = "zip"
    OTHER = "other"


class ParseStatus(StrEnum):
    METADATA_ONLY = "metadata_only"
    RECOGNIZED = "recognized"
    PARSED = "parsed"
    UNSUPPORTED = "unsupported"
    QUARANTINED = "quarantined"
    CORRUPT = "corrupt"


class FilingRelationshipType(StrEnum):
    REVISES = "revises"
    REPLACES = "replaces"
    SUPPLEMENTS = "supplements"
    RESTATES_COMPARATIVE_FROM = "restates_comparative_from"
    DUPLICATE_OF = "duplicate_of"


class ReconciliationStatus(StrEnum):
    EXACT_MATCH = "exact_match"
    WITHIN_ROUNDING = "within_rounding_tolerance"
    MATERIAL_DIFFERENCE = "material_difference"
    PERIOD_MISMATCH = "period_mismatch"
    BASIS_MISMATCH = "basis_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    OFFICIAL_ONLY = "official_only"
    COMPATIBILITY_ONLY = "compatibility_only"
    BOTH_MISSING = "both_missing"
    UNRESOLVED = "unresolved"


class DiscoveredAttachment(BaseModel):
    sequence: int = Field(default=1, ge=1, le=20)
    source_url: str
    filename: str
    declared_content_type: str | None = None
    format_hint: AttachmentFormat = AttachmentFormat.OTHER

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("official attachment URL must use https")
        return value


class DiscoveredOfficialFiling(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_code: str = "nse_financial_results"
    source_filing_id: str
    company_name: str
    nse_symbol: str
    isin: str | None = None
    subject: str
    category: str
    filing_type: str
    filing_date: date
    publication_timestamp: datetime
    source_timestamp: datetime
    retrieved_at: datetime
    period: FinancialPeriod
    basis_hint: ConsolidationBasis
    audited_status: str
    revision_hint: str = "original"
    source_url: str
    raw_metadata_hash: str = Field(min_length=64, max_length=64)
    raw_response_hash: str = Field(min_length=64, max_length=64)
    canonical_identity_hash: str = Field(min_length=64, max_length=64)
    attachments: tuple[DiscoveredAttachment, ...] = ()
    raw_metadata: dict = Field(default_factory=dict, exclude=True)


class FetchedDocument(BaseModel):
    source_url: str
    filename: str
    detected_content_type: str
    attachment_format: AttachmentFormat
    content_length: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    retrieved_at: datetime
    cache_hit: bool
    etag: str | None = None
    last_modified: str | None = None
    content: bytes = Field(exclude=True)


class ParserRecognition(BaseModel):
    template_id: str | None = None
    template_version: str | None = None
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    required_fields_present: bool = False
    unsupported_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class XbrlFactEvidence(BaseModel):
    canonical_metric_id: str
    selected_value: Decimal
    original_value: str
    normalized_value: Decimal
    unit: str
    unit_ref: str | None = None
    concept: str
    namespace: str | None = None
    context_id: str
    decimals: str | None = None
    precision: str | None = None
    scale: int = 0
    mapping_version: str
    mapping_status: str
    candidate_count: int = Field(ge=1)
    selection_reason: str
    duplicate_equivalent: bool = False
    duplicate_conflict: bool = False
    quality_warnings: list[str] = Field(default_factory=list)


class ParsedOfficialFiling(BaseModel):
    parser_version: str
    recognition: ParserRecognition
    period: FinancialPeriod
    basis: ConsolidationBasis
    audited_status: str
    currency: str
    original_unit: str
    facts: list[SourceFact]
    taxonomy_namespace: str | None = None
    taxonomy_version: str | None = None
    taxonomy_status: str = "unsupported"
    fact_evidence: list[XbrlFactEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReconciliationResult(BaseModel):
    instrument_id: str
    metric_id: str
    period: FinancialPeriod
    basis: ConsolidationBasis
    official_fact_id: str | None = None
    official_value: Decimal | None = None
    compatibility_value: Decimal | None = None
    unit: str
    absolute_difference: Decimal | None = None
    percentage_difference: Decimal | None = None
    status: ReconciliationStatus
    selected_value: Decimal | None = None
    selected_source: str | None = None
    selection_reason: str
    rejected_alternatives: list[dict] = Field(default_factory=list)
    rule_version: str = RECONCILIATION_RULE_VERSION
    selection_rule_version: str = SOURCE_SELECTION_RULE_VERSION


class OfficialImportSummary(BaseModel):
    instruments_attempted: int = 0
    instruments_with_filings: int = 0
    filings_discovered: int = 0
    source_records_created: int = 0
    source_records_unchanged: int = 0
    revised_filings: int = 0
    attachments_downloaded: int = 0
    attachments_reused: int = 0
    attachments_unsupported: int = 0
    attachments_corrupt: int = 0
    templates_recognized: int = 0
    templates_unrecognized: int = 0
    facts_parsed: int = 0
    facts_accepted: int = 0
    facts_warned: int = 0
    facts_rejected: int = 0
    consolidated_filings: int = 0
    standalone_filings: int = 0
    unknown_basis_filings: int = 0
    conflicting_basis_filings: int = 0
    reconciliation_matches: int = 0
    material_conflicts: int = 0
    official_only_facts: int = 0
    compatibility_only_facts: int = 0
    public_selected_facts: int = 0
    request_count: int = 0
    retry_count: int = 0
    bytes_downloaded: int = 0
    throttle_seconds: Decimal = Decimal("0")
    errors: list[str] = Field(default_factory=list)
