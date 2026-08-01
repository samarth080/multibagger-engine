"""Provider- and template-independent public company-research contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RESEARCH_SCHEMA_VERSION = "1.0"
EXPLANATION_POLICY_VERSION = "2026-08-01.1"
PEER_POLICY_VERSION = "2026-08-01.1"
COMPATIBILITY_POLICY_VERSION = "2026-08-01.1"


class ResearchIdentity(BaseModel):
    instrument_id: str
    company_id: str | None = None
    display_name: str
    legal_name: str | None = None
    symbol: str
    exchange: str
    bse_code: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_category: str | None = None
    index_membership: str = "Nifty Smallcap 250"
    is_sme: bool | None = None
    listing_status: str = "active"
    canonical_url: str
    legacy_url: str | None = None


class ResearchQuote(BaseModel):
    price: float | None = None
    absolute_change: float | None = None
    percentage_change: float | None = None
    currency: str = "INR"
    market_status: str = "unavailable"
    timestamp: str | None = None
    delay_minutes: int | None = None
    stale: bool = True
    state: Literal["build_close", "live", "delayed", "stale", "unavailable"] = "unavailable"
    message: str


class ScoreComponentResearch(BaseModel):
    name: str
    score: float
    confidence: float | None = None
    evidence_count: int = 0


class RankingResearch(BaseModel):
    rank: int
    previous_rank: int | None = None
    rank_change: int | None = None
    multibagger_score: float
    previous_score: float | None = None
    score_change: float | None = None
    investment_score: float
    confidence: float
    risk_score: float
    investability: str
    technical_trend: str
    momentum_rank: int | None = None
    coverage_quality: float | None = None
    has_missing_data: bool = False
    positive_signal_count: int = 0
    red_flag_count: int = 0
    model_version: str | None = None
    model_build_id: str | None = None
    build_timestamp: str | None = None
    data_cutoff: str | None = None
    validation_status: str | None = None
    components: list[ScoreComponentResearch] = Field(default_factory=list)


class ResearchExplanation(BaseModel):
    code: str
    label: str
    text: str
    classification: Literal["positive", "neutral", "warning", "risk"]
    source_field_ids: list[str]
    current_value: float | str | None = None
    comparison_value: float | str | None = None
    period: str | None = None
    source: str | None = None
    freshness: str | None = None
    methodology_href: str = "/methodology.html"
    version: str = EXPLANATION_POLICY_VERSION


class ScoreHistoryPoint(BaseModel):
    build_id: str
    built_at: str
    rank: int
    multibagger_score: float
    confidence: float | None = None
    risk_score: float | None = None
    investment_score: float | None = None
    components: list[ScoreComponentResearch] = Field(default_factory=list)


class ScoreHistoryResearch(BaseModel):
    points: list[ScoreHistoryPoint] = Field(default_factory=list)
    summary: str
    is_continuous: bool = False
    max_points: int = 26


class FinancialFactResearch(BaseModel):
    metric_id: str
    label: str
    value: float
    fiscal_year: int | None = None
    unit: str


class FinancialResearch(BaseModel):
    revenue_cagr_3y: float | None = None
    roce_3y: float | None = None
    recent_facts: list[FinancialFactResearch] = Field(default_factory=list)
    selected_source: str = "unavailable"
    source_label: str = "Unavailable"
    source_quality_tier: str | None = None
    fallback: bool = False
    basis: str = "unknown"
    basis_warning: str | None = None
    latest_period: str | None = None
    data_cutoff: str | None = None
    source_date: str | None = None
    freshness: str = "unknown"
    quality_status: str = "unavailable"
    quality_warnings: list[str] = Field(default_factory=list)
    official_tier_a_status: str = "unavailable"
    reconciliation_status: str = "not_reconciled"
    financial_build_id: str | None = None
    metric_definition_version: str | None = None
    source_selection_policy_version: str | None = None
    source_selection_reason: str | None = None


class TechnicalResearch(BaseModel):
    trend: str = "unknown"
    momentum_rank: int | None = None
    momentum_group: str | None = None
    momentum_score: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_12m: float | None = None
    relative_strength_3m: float | None = None
    message: str | None = None


class PeerResearch(BaseModel):
    instrument_id: str
    canonical_url: str
    display_name: str
    symbol: str
    rank: int
    multibagger_score: float
    confidence: float
    risk_score: float
    revenue_cagr_3y: float | None = None
    roce_3y: float | None = None
    technical_trend: str
    market_cap_category: str | None = None
    source_quality_tier: str | None = None
    selection_score: float
    selection_reasons: list[str]


class FilingResearch(BaseModel):
    filing_id: str
    filing_date: str | None = None
    category: str
    subject: str
    period_type: str
    basis: str
    revision_state: str
    parsing_status: str
    acceptance_status: str
    source_url: str | None = None


class NewsResearch(BaseModel):
    title: str
    link: str
    source: str | None = None
    published: str | None = None
    relevance_score: float
    match_confidence: Literal["high", "medium"]
    match_reasons: list[str]
    category: str = "company"
    deduplication_cluster: str | None = None


class ChecklistItem(BaseModel):
    code: str
    label: str


class ResearchLineage(BaseModel):
    model_build_id: str | None = None
    financial_build_id: str | None = None
    model_version: str | None = None
    financial_metric_definition_version: str | None = None
    explanation_policy_version: str = EXPLANATION_POLICY_VERSION
    peer_policy_version: str = PEER_POLICY_VERSION
    compatibility_policy_version: str = COMPATIBILITY_POLICY_VERSION
    source_selection_policy_version: str | None = None
    data_cutoff: str | None = None
    quote_timestamp: str | None = None
    news_cutoff: str | None = None
    generated_at: str
    data_mode: Literal["static", "dynamic"]
    financial_source: str
    financial_source_quality_tier: str | None = None
    official_tier_a_status: str = "unavailable"
    known_limitations: list[str] = Field(default_factory=list)


class CompanyResearch(BaseModel):
    schema_version: str = RESEARCH_SCHEMA_VERSION
    identity: ResearchIdentity
    quote: ResearchQuote
    ranking: RankingResearch
    research_summary: list[str]
    explanations: list[ResearchExplanation]
    strengths: list[ResearchExplanation]
    risks: list[ResearchExplanation]
    history: ScoreHistoryResearch
    financials: FinancialResearch
    technical: TechnicalResearch
    peers: list[PeerResearch] = Field(default_factory=list)
    peer_policy_version: str = PEER_POLICY_VERSION
    filings: list[FilingResearch] = Field(default_factory=list)
    filings_state: str
    news: list[NewsResearch] = Field(default_factory=list)
    news_state: str
    checklist: list[ChecklistItem]
    lineage: ResearchLineage
    warnings: list[str] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    methodology_links: dict[str, str] = Field(default_factory=dict)
    compatibility: dict[str, Any] = Field(default_factory=dict)
