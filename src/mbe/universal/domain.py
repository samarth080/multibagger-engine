"""Universal Research Score domain types. A score that can be computed for
any searchable company with sufficient data — distinct from and never
mixed with mbe.models.scoring.ScoreCard (the validated Nifty Smallcap 250
Multibagger/Investment score). See docs/coverage-architecture.md for the
separate concept of *coverage level* (how much data exists); this module
is about the *score* computed from that data.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from mbe.models.scoring import Evidence


class CompanyType(str, Enum):
    GENERAL_CORPORATE = "general_corporate"
    BANK = "bank"
    NBFC = "nbfc"
    INSURANCE = "insurance"
    ASSET_MANAGEMENT = "asset_management"
    OTHER_FINANCIAL = "other_financial"
    UNKNOWN_LIMITED_DATA = "unknown_limited_data"


class ReportState(str, Enum):
    FULL = "full_evaluated_report"
    PARTIAL = "partial_evaluated_report"
    TECHNICAL_ONLY = "technical_only_evaluated_report"
    INSUFFICIENT = "insufficient_data_for_scoring"


class UniversalFactorScore(BaseModel):
    name: str
    score: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    eligible_weight: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []
    excluded_metrics: list[str] = []


class UniversalScoreCard(BaseModel):
    instrument_id: str | None = None
    ticker: str
    company_type: CompanyType
    overall_score: float | None = Field(default=None, ge=0, le=100)
    confidence: str  # "Low" | "Medium" | "High"
    confidence_score: float = Field(ge=0, le=1)
    data_coverage_pct: float = Field(ge=0, le=100)
    report_state: ReportState
    factors: list[UniversalFactorScore] = []
    policy_version: str
    excluded_factor_notes: list[str] = []
