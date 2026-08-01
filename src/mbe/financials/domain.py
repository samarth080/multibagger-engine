"""Typed financial lineage contracts shared by imports, API and snapshots."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FINANCIAL_SCHEMA_VERSION = "1.0"


class PeriodType(StrEnum):
    ANNUAL = "annual"
    QUARTER = "quarter"
    YEAR_TO_DATE = "year_to_date"
    TTM = "ttm"
    INSTANT = "instant"


class ConsolidationBasis(StrEnum):
    CONSOLIDATED = "consolidated"
    STANDALONE = "standalone"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class QualityState(StrEnum):
    VALID = "valid"
    VALID_WITH_WARNING = "valid_with_warning"
    DERIVED = "derived"
    INCOMPLETE = "incomplete"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    MISSING = "missing"


class FinancialPeriod(BaseModel):
    model_config = ConfigDict(frozen=True)
    period_type: PeriodType
    fiscal_year: int = Field(ge=1900, le=2200)
    fiscal_quarter: int | None = Field(default=None, ge=1, le=4)
    period_start: date | None = None
    period_end: date
    instant_date: date | None = None
    duration_days: int | None = Field(default=None, ge=0, le=740)
    source_label: str | None = None

    @model_validator(mode="after")
    def validate_semantics(self):
        if self.period_start and self.period_start > self.period_end:
            raise ValueError("period start must not follow period end")
        if self.period_type == PeriodType.QUARTER and self.fiscal_quarter is None:
            raise ValueError("quarter periods require fiscal_quarter")
        if self.period_type == PeriodType.INSTANT and self.instant_date is None:
            raise ValueError("instant periods require instant_date")
        return self


class SourceFact(BaseModel):
    """One untrusted provider fact before persistence."""

    source_field: str
    metric_id: str
    value: Decimal | None
    unit: str
    currency: str | None = None
    period: FinancialPeriod
    basis: ConsolidationBasis = ConsolidationBasis.UNKNOWN
    source_location: str | None = None
    is_derived: bool = False
    source_fact_ids: tuple[str, ...] = ()


class FilingInput(BaseModel):
    source_code: str
    source_filing_id: str
    company_id: str
    instrument_id: str | None = None
    filing_type: str
    period: FinancialPeriod
    basis: ConsolidationBasis
    currency: str
    original_unit: str
    filing_date: date | None = None
    publication_timestamp: datetime | None = None
    audited_status: str = "unknown"
    revision_number: int = Field(default=1, ge=1)
    restates_source_filing_id: str | None = None
    retrieved_at: datetime
    raw_payload_hash: str
    source_url: str | None = None
    facts: list[SourceFact]

    @field_validator("source_url")
    @classmethod
    def safe_source_url(cls, value):
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("source_url must use http or https")
        return value


class ImportSummary(BaseModel):
    companies_attempted: int = 0
    companies_imported: int = 0
    companies_skipped: int = 0
    filings_discovered: int = 0
    filings_created: int = 0
    filings_unchanged: int = 0
    filings_revised: int = 0
    facts_read: int = 0
    facts_normalized: int = 0
    facts_unchanged: int = 0
    facts_rejected: int = 0
    unknown_source_fields: int = 0
    unit_anomalies: int = 0
    period_anomalies: int = 0
    basis_ambiguities: int = 0
    restatements_detected: int = 0
    errors: list[str] = []
