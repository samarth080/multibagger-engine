"""Stable public v1 response contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from mbe.data.market import NormalizedQuote
from mbe.models.instrument import Freshness

T = TypeVar("T")


class ApiError(BaseModel):
    code: str
    message: str
    field: str | None = None


class PageMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    sort: str


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    meta: dict[str, Any] | PageMeta = Field(default_factory=dict)
    errors: list[ApiError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    freshness: Freshness | None = None
    request_id: str


class HealthData(BaseModel):
    service_status: str
    database: str
    application_version: str
    current_timestamp: datetime


class StatusData(BaseModel):
    latest_instrument_import: dict[str, Any] | None
    instrument_counts: dict[str, int]
    latest_model_build: dict[str, Any] | None
    quote_providers: list[dict[str, Any]]
    datasets: list[dict[str, Any]]
    supported_markets: list[str]
    supported_exchanges: list[str]


class InstrumentData(BaseModel):
    instrument_id: str
    company_id: str | None = None
    legal_name: str | None = None
    display_name: str | None = None
    current_legal_name: str | None = None
    exchange: str
    symbol: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    isin: str | None = None
    exchange_segment: str | None = None
    exchange_series: str | None = None
    country: str
    currency: str
    timezone: str
    listing_status: str
    listing_date: date | None = None
    delisting_date: date | None = None
    primary_listing: bool
    is_sme: bool | None = None
    security_type: str
    sector: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    market_cap_category: str | None = None
    quality_status: str
    aliases: list[dict[str, str]] = Field(default_factory=list)
    provider_mappings: list[dict[str, str]] = Field(default_factory=list)


class LookupCandidate(BaseModel):
    instrument_id: str
    display_name: str | None = None
    symbol: str | None = None
    exchange: str | None = None
    score: float
    matched_by: str
    matched_value: str
    bse_code: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_category: str | None = None
    listing_status: str | None = None
    is_sme: bool | None = None


class RankingData(BaseModel):
    instrument_id: str
    rank: int
    symbol: str
    exchange: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    multibagger_score: float
    investment_score: float
    confidence: float
    risk_score: float
    investability: str
    positive_signal_count: int = 0
    red_flag_count: int = 0
    coverage_quality: float | None = None
    has_missing_data: bool
    technical_trend: str | None = None
    main_positive_signal: str | None = None
    main_risk: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)
    previous_rank: int | None = None
    rank_change: int | None = None


class RankingComponent(BaseModel):
    name: str
    score: float
    confidence: float
    evidence_count: int


class BuildData(BaseModel):
    build_id: str
    model_version: str
    factor_config_version: str
    factor_config_hash: str
    universe_name: str
    universe_version: str
    data_cutoff: datetime
    built_at: datetime
    status: str
    attempted_count: int
    scored_count: int
    failed_count: int
    provider_versions: dict[str, str]
    validation_status: str


class PreviousRanking(BaseModel):
    build_id: str
    rank: int
    multibagger_score: float


class RankingDetailData(BaseModel):
    instrument_id: str
    build_id: str
    rank: int
    multibagger_score: float
    investment_score: float
    confidence: float
    risk_score: float
    investability: str
    components: list[RankingComponent]
    build: BuildData
    previous: PreviousRanking | None = None


class QuoteBatchData(BaseModel):
    quotes: list[NormalizedQuote]


class MethodologyData(BaseModel):
    model_version: str
    components: dict[str, dict[str, float]]
    build_cadence: str
    validation_status: str
    data_categories: list[str]
    major_limitations: list[str]
    disclaimer: str


class ScreenerMatchedCondition(BaseModel):
    condition_id: str
    field_id: str
    operator: str
    actual_value: Any | None = None
    value: Any | None = None
    value_to: Any | None = None
    values: list[Any] | None = None


class ScreenerRowData(BaseModel):
    instrument_id: str
    values: dict[str, Any]
    report_url: str | None = None
    matched_conditions: list[ScreenerMatchedCondition]


class ScreenerPagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ScreenerResultData(BaseModel):
    rows: list[ScreenerRowData]
    pagination: ScreenerPagination
    applied_filters: list[dict[str, Any]]
    effective_sorting: list[dict[str, Any]]
    requested_columns: list[str]
    dataset: dict[str, Any]
    build: dict[str, Any]
    mode: str
    query_fingerprint: str
    financial_dataset_build: dict[str, Any] | None = None
