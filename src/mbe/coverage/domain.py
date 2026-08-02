"""Coverage-level domain types. A coverage level is a deterministic, versioned
statement of how much validated data exists for an instrument — not a
research verdict. See docs/coverage-architecture.md.
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field

COVERAGE_LEVEL_VERSION = "1.0"


class CoverageLevel(IntEnum):
    IDENTITY = 0
    MARKET = 1
    FUNDAMENTALS = 2
    FULL_RESEARCH = 3


COVERAGE_LEVEL_LABELS: dict[CoverageLevel, str] = {
    CoverageLevel.IDENTITY: "Level 0 — Identity Coverage",
    CoverageLevel.MARKET: "Level 1 — Market Coverage",
    CoverageLevel.FUNDAMENTALS: "Level 2 — Financial Coverage",
    CoverageLevel.FULL_RESEARCH: "Level 3 — Full Research",
}

# Each level's sections are a strict superset of the previous level's —
# enforced by test_section_tables_are_nested_and_cover_all_sections.
COVERAGE_LEVEL_SECTIONS: dict[CoverageLevel, tuple[str, ...]] = {
    CoverageLevel.IDENTITY: ("identity",),
    CoverageLevel.MARKET: ("identity", "quote"),
    CoverageLevel.FUNDAMENTALS: ("identity", "quote", "financial_summary"),
    CoverageLevel.FULL_RESEARCH: (
        "identity", "quote", "financial_summary", "score", "rank",
        "explanations", "strengths", "risks", "score_history", "peers",
        "technical", "news", "filings", "checklist",
    ),
}

ALL_SECTIONS: tuple[str, ...] = COVERAGE_LEVEL_SECTIONS[CoverageLevel.FULL_RESEARCH]

SOURCE_QUALITY_SUMMARIES: dict[CoverageLevel, str] = {
    CoverageLevel.IDENTITY: "Identity only — no market or financial data connected.",
    CoverageLevel.MARKET: "Identity and live market data; no financial or model data.",
    CoverageLevel.FUNDAMENTALS: "Identity, market data and a financial summary; not yet modeled.",
    CoverageLevel.FULL_RESEARCH: "Full research — identity, market, financial and model data.",
}


class CoverageAssessment(BaseModel):
    """The single typed statement of coverage for one instrument. Produced
    only by mbe.coverage.policy.assess_coverage — never constructed with
    hand-picked field values outside a test fixture."""

    instrument_id: str
    company_id: str | None = None
    research_coverage_level: int
    coverage_label: str
    coverage_level_version: str = COVERAGE_LEVEL_VERSION
    research_coverage_status: str
    research_eligible: bool
    research_eligibility_reasons: list[str] = Field(default_factory=list)
    research_sections_available: list[str] = Field(default_factory=list)
    research_sections_missing: list[str] = Field(default_factory=list)
    research_universe: str | None = None
    ranking_available: bool
    model_available: bool
    financial_available: bool
    quote_available: bool
    identity_completeness: str
    source_quality_summary: str
    evaluated_at: str
    coverage_policy_version: str
