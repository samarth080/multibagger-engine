"""Coverage-level-aware company payload for Levels 0-2 (identity, market,
financial-summary). Composes mbe.research.lightweight.build_lightweight_research
rather than duplicating its identity/quote logic. Level 3 (full research) is
built by mbe.research.builder.build_company_research and never routed
through this module — see mbe.coverage.policy for the level boundary.
"""

from __future__ import annotations

from datetime import datetime

from mbe.coverage.domain import CoverageAssessment
from mbe.research.lightweight import build_lightweight_research


def build_coverage_research(
    record: dict,
    quote: dict | None,
    coverage: CoverageAssessment,
    financial_summary: dict | None = None,
    *,
    universal: dict | None = None,
    now: datetime | None = None,
) -> dict:
    if coverage.research_coverage_level >= 3:
        raise ValueError(
            "build_coverage_research refuses a Level 3 assessment — that "
            "company must use mbe.research.builder.build_company_research instead."
        )
    payload = build_lightweight_research(record, quote, now=now)
    payload["coverage"] = coverage.model_dump(mode="json")
    payload["financial_summary"] = (
        financial_summary if coverage.research_coverage_level >= 2 else None
    )
    payload["universal"] = universal
    return payload
