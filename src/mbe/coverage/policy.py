"""Deterministic coverage-level assignment. The only place level logic
lives — mbe.search.catalog, api/company.py and mbe.api.app all call this
same function so they cannot disagree. See docs/coverage-architecture.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mbe.coverage.domain import (
    ALL_SECTIONS, COVERAGE_LEVEL_LABELS, COVERAGE_LEVEL_SECTIONS,
    SOURCE_QUALITY_SUMMARIES, CoverageAssessment, CoverageLevel,
)

RESEARCH_COVERAGE_POLICY_VERSION = "2026-08-03.11.2a.1"

_ACTIVE_LISTING_STATUSES = {"active", "unknown"}


def assess_coverage(
    record: dict,
    *,
    has_financial_data: bool,
    has_model_score: bool,
    has_full_research_payload: bool,
    now: datetime | None = None,
) -> CoverageAssessment:
    """``record`` carries identity fields (instrument_id, company_id, isin,
    bse_code, legal_name, listing_status, is_sme, provider_symbol) — the
    same shape mbe.search.domain.SearchIndexRecord and
    mbe.research.lightweight already use. Assumes a valid, already-resolved
    identity: callers 404 before reaching this function for an unknown
    instrument."""
    instrument_id = record.get("instrument_id")
    if not instrument_id:
        raise ValueError("assess_coverage requires a valid instrument_id")
    now = now or datetime.now(timezone.utc)
    has_provider_symbol = bool(record.get("provider_symbol"))

    if has_model_score and has_full_research_payload and has_financial_data and has_provider_symbol:
        level = CoverageLevel.FULL_RESEARCH
    elif has_financial_data and has_provider_symbol:
        level = CoverageLevel.FUNDAMENTALS
    elif has_provider_symbol:
        level = CoverageLevel.MARKET
    else:
        level = CoverageLevel.IDENTITY

    reasons: list[str] = []
    eligible = level == CoverageLevel.FULL_RESEARCH
    if eligible:
        reasons.append("in_smallcap_research_universe")
    else:
        if not has_provider_symbol:
            reasons.append("no_quote_provider_mapping")
        if not has_financial_data:
            reasons.append("no_financial_data")
        if not has_model_score:
            reasons.append("not_in_model_universe")

    sections_available = list(COVERAGE_LEVEL_SECTIONS[level])
    sections_missing = [s for s in ALL_SECTIONS if s not in sections_available]

    listing_status = record.get("listing_status") or "active"
    coverage_status = (
        "active" if listing_status in _ACTIVE_LISTING_STATUSES else "inactive_listing"
    )
    identity_completeness = (
        "complete" if record.get("isin") and record.get("legal_name") else "partial"
    )

    return CoverageAssessment(
        instrument_id=instrument_id,
        company_id=record.get("company_id"),
        research_coverage_level=int(level),
        coverage_label=COVERAGE_LEVEL_LABELS[level],
        research_coverage_status=coverage_status,
        research_eligible=eligible,
        research_eligibility_reasons=reasons,
        research_sections_available=sections_available,
        research_sections_missing=sections_missing,
        research_universe="Nifty Smallcap 250" if eligible else None,
        ranking_available=has_model_score,
        model_available=has_model_score,
        financial_available=has_financial_data,
        quote_available=has_provider_symbol,
        identity_completeness=identity_completeness,
        source_quality_summary=SOURCE_QUALITY_SUMMARIES[level],
        evaluated_at=now.isoformat(),
        coverage_policy_version=RESEARCH_COVERAGE_POLICY_VERSION,
    )
