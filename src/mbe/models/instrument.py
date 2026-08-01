"""Canonical security identity and lineage models.

Provider tickers are mutable lookup keys.  ``instrument_id`` is the permanent
application identity and is never derived again after a record is persisted.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

IDENTITY_NAMESPACE = uuid.UUID("4f0cf2a8-2257-4a68-9ebd-835e86ba5b84")


class ListingStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELISTED = "delisted"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


class SecurityType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    REIT = "reit"
    INVIT = "invit"
    PREFERENCE = "preference"
    OTHER = "other"
    UNKNOWN = "unknown"


class AliasType(StrEnum):
    LEGAL_NAME = "legal_name"
    FORMER_NAME = "former_name"
    COMMON_NAME = "common_name"
    ABBREVIATION = "abbreviation"
    BRAND = "brand"
    FORMER_SYMBOL = "former_symbol"


class QualityStatus(StrEnum):
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"
    REVIEW = "review"
    UNKNOWN = "unknown"


class FreshnessState(StrEnum):
    FRESH = "fresh"
    DELAYED = "delayed"
    STALE = "stale"
    MISSING = "missing"
    FAILED = "failed"
    UNKNOWN = "unknown"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_symbol(value: str) -> str:
    """Normalize an exchange/provider symbol without erasing meaningful ``&``."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).upper()


_COMPANY_SUFFIXES = {
    "limited", "ltd", "ltd.", "private", "pvt", "inc", "inc.",
    "corporation", "corp", "company", "co", "plc",
}


def normalize_name(value: str, *, strip_suffixes: bool = False) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"[^\w\s&]", " ", text)
    tokens = [token for token in text.split() if token]
    if strip_suffixes:
        while tokens and tokens[-1] in _COMPANY_SUFFIXES:
            tokens.pop()
    return " ".join(tokens)


def stable_instrument_id(
    *, exchange_code: str, symbol: str, isin: str | None = None,
    source_record_id: str | None = None,
) -> str:
    """Create a deterministic *initial* ID for idempotent bootstrap imports.

    Persisted IDs are immutable.  ISIN/source identity takes precedence so a
    symbol change resolves to the same bootstrap ID when the source supplies it.
    """
    # Source record IDs are provenance, not identity: different loaders often
    # assign different record keys to the same listing.  A supplied ISIN is the
    # cross-source anchor; otherwise the initial exchange listing is used.
    identity = isin or f"{exchange_code}:{normalize_symbol(symbol)}"
    return str(uuid.uuid5(IDENTITY_NAMESPACE, f"instrument:{identity.upper()}"))


def stable_company_id(*, country: str, isin: str | None, name: str | None, fallback: str) -> str:
    identity = isin or (normalize_name(name or "", strip_suffixes=True) or fallback)
    return str(uuid.uuid5(IDENTITY_NAMESPACE, f"company:{country.upper()}:{identity}"))


class ExchangeRef(BaseModel):
    code: str
    name: str
    mic: str | None = None
    country: str = "IN"
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"


class InstrumentAlias(BaseModel):
    value: str
    alias_type: AliasType
    normalized_value: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    source: str | None = None

    @model_validator(mode="after")
    def populate_normalized(self):
        if not self.normalized_value:
            self.normalized_value = normalize_name(self.value)
        return self


class ProviderSymbolMapping(BaseModel):
    provider: str
    provider_symbol: str
    provider_instrument_id: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool = True
    source: str | None = None

    @field_validator("provider", "provider_symbol")
    @classmethod
    def nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class CanonicalInstrument(BaseModel):
    instrument_id: str
    company_id: str | None = None
    legal_name: str | None = None
    display_name: str | None = None
    current_legal_name: str | None = None
    exchange: ExchangeRef
    exchange_segment: str | None = None
    exchange_series: str | None = None
    nse_symbol: str | None = None
    bse_code: str | None = None
    isin: str | None = None
    country: str = "IN"
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    listing_status: ListingStatus = ListingStatus.UNKNOWN
    listing_date: date | None = None
    delisting_date: date | None = None
    primary_listing: bool = True
    is_sme: bool | None = None
    security_type: SecurityType = SecurityType.EQUITY
    sector: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    market_cap_category: str | None = None
    aliases: list[InstrumentAlias] = Field(default_factory=list)
    provider_mappings: list[ProviderSymbolMapping] = Field(default_factory=list)
    source: str | None = None
    source_record_id: str | None = None
    source_timestamp: datetime | None = None
    retrieved_at: datetime | None = None
    quality_status: QualityStatus = QualityStatus.UNKNOWN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("nse_symbol")
    @classmethod
    def normalize_nse(cls, value: str | None) -> str | None:
        return normalize_symbol(value.removesuffix(".NS")) if value else None

    @field_validator("isin")
    @classmethod
    def validate_isin(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = normalize_symbol(value)
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", value):
            raise ValueError("invalid ISIN format")
        return value

    @field_validator("bse_code")
    @classmethod
    def validate_bse(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not re.fullmatch(r"\d{6}", value):
            raise ValueError("BSE code must contain six digits")
        return value

    @property
    def legacy_ticker(self) -> str | None:
        if self.nse_symbol:
            return f"{self.nse_symbol}.NS"
        mapping = next(
            (m for m in self.provider_mappings if m.provider.casefold() == "yahoo" and m.is_primary),
            None,
        )
        return mapping.provider_symbol if mapping else None


class BuildManifest(BaseModel):
    build_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model_version: str
    factor_config_version: str
    factor_config_hash: str
    universe_name: str
    universe_version: str
    data_cutoff: datetime
    built_at: datetime = Field(default_factory=utc_now)
    provider_versions: dict[str, str] = Field(default_factory=dict)
    validation_status: str
    status: str = "running"
    duration_seconds: float | None = None
    attempted_count: int = 0
    scored_count: int = 0
    failed_count: int = 0
    source_data_version: str | None = None
    notes: str | None = None
    error_summary: str | None = None

    @staticmethod
    def configuration_hash(config: dict[str, Any]) -> str:
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def create(
        cls, *, model_version: str, factor_config_version: str,
        factor_config: dict[str, Any], universe_name: str, universe_version: str,
        data_cutoff: datetime, provider_versions: dict[str, str],
        validation_status: str, **kwargs: Any,
    ) -> "BuildManifest":
        return cls(
            model_version=model_version,
            factor_config_version=factor_config_version,
            factor_config_hash=cls.configuration_hash(factor_config),
            universe_name=universe_name,
            universe_version=universe_version,
            data_cutoff=data_cutoff,
            provider_versions=dict(sorted(provider_versions.items())),
            validation_status=validation_status,
            **kwargs,
        )


class Freshness(BaseModel):
    state: FreshnessState
    source: str | None = None
    source_timestamp: datetime | None = None
    retrieved_at: datetime | None = None
    normalized_at: datetime | None = None
    delay_minutes: int | None = Field(default=None, ge=0)
    reason: str | None = None
    quality_status: QualityStatus = QualityStatus.UNKNOWN
