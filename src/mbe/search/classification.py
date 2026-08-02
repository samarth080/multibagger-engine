"""Classification provenance, source-priority reconciliation, and coverage
reporting (Phase 10C section 3).

Every sector/industry/sub-industry value shown anywhere must trace back to
one of a small, documented set of sources — never inferred from a company
name, ticker, or free text. This module keeps every source's classification
claim for an instrument side by side (``ClassificationRecord``), picks
exactly one as canonical via a versioned rule (``select_canonical``), and
measures coverage instead of assuming it
(``build_classification_coverage_report``).

Reconciliation rule: priority for *filling an otherwise-unclaimed
instrument* is exchange-provided > index-provider > research-universe >
documented-public (section 3's priority list) — but a research-universe
claim, once it exists, is always kept as canonical over every other source.
This is not a contradiction of the priority list: the priority list governs
which source wins when nothing has been classified yet; the no-overwrite
rule is a stability guarantee once a company already has a published
research-page classification (see docs/classification-policy.md).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel

from mbe.search.domain import SearchIndexRecord

CLASSIFICATION_POLICY_VERSION = "2026-08-02.10c.1"

#: The platform's own pass-through labeling — sector/industry/sub_industry
#: strings are taken verbatim from a source's own label, never mapped to a
#: third-party taxonomy (GICS/ICB) since no such mapping is available in
#: this repository.
DEFAULT_CLASSIFICATION_SYSTEM = "mbe_verbatim_v1"

_STALE_AFTER_DAYS = 730


class ClassificationSource(StrEnum):
    EXCHANGE_MASTER = "exchange_master"
    INDEX_PROVIDER = "index_provider"
    RESEARCH_UNIVERSE = "research_universe"
    DOCUMENTED_PUBLIC = "documented_public"


#: Priority for filling an unclaimed instrument, highest first. Does not
#: apply once a RESEARCH_UNIVERSE claim exists — see module docstring.
_SOURCE_PRIORITY: dict[ClassificationSource, int] = {
    ClassificationSource.EXCHANGE_MASTER: 0,
    ClassificationSource.INDEX_PROVIDER: 1,
    ClassificationSource.RESEARCH_UNIVERSE: 2,
    ClassificationSource.DOCUMENTED_PUBLIC: 3,
}


class ClassificationReviewStatus(StrEnum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"
    STALE = "stale"
    MISSING = "missing"


class ClassificationRecord(BaseModel):
    """One source's classification claim for one instrument."""

    instrument_id: str
    classification_system: str = DEFAULT_CLASSIFICATION_SYSTEM
    sector: str | None = None
    industry: str | None = None
    sub_industry: str | None = None
    source: ClassificationSource
    source_record_id: str | None = None
    source_date: datetime | None = None
    retrieved_at: datetime
    classification_version: str = CLASSIFICATION_POLICY_VERSION
    confidence: float = 1.0
    review_status: ClassificationReviewStatus = ClassificationReviewStatus.MISSING
    is_selected_canonical: bool = False
    selection_reason: str | None = None

    def is_empty(self) -> bool:
        return not (self.sector or self.industry or self.sub_industry)


def _is_stale(record: ClassificationRecord, now: datetime) -> bool:
    if record.source_date is None:
        return False
    return (now - record.source_date).days > _STALE_AFTER_DAYS


def select_canonical(
    records: list[ClassificationRecord], *, now: datetime | None = None,
) -> list[ClassificationRecord]:
    """Pick exactly one of ``records`` (all claims for the same instrument)
    as canonical. Returns a new list, same length and order as ``records``,
    with ``is_selected_canonical``/``review_status``/``selection_reason``
    populated on every entry — the full audit trail, not just the winner.

    Each current source supplies at most one non-empty
    sector/industry/sub_industry combination per instrument, so canonical
    selection operates at the whole-record level rather than merging
    individual fields across sources. If a future source supplies partial
    fields requiring field-level merging, this function will need revisiting
    (see docs/classification-policy.md "Known limitations").
    """
    now = now or datetime.now(timezone.utc)
    non_empty = [r for r in records if not r.is_empty()]
    if not non_empty:
        return [
            r.model_copy(update={
                "is_selected_canonical": False,
                "review_status": ClassificationReviewStatus.MISSING,
                "selection_reason": "no_classification_available",
            })
            for r in records
        ]

    research = next(
        (r for r in non_empty if r.source == ClassificationSource.RESEARCH_UNIVERSE), None,
    )
    if research is not None:
        selected = research
        reason = "research_universe_classification_preserved_over_other_sources"
    else:
        selected = min(non_empty, key=lambda r: _SOURCE_PRIORITY[r.source])
        reason = f"highest_priority_available_source:{selected.source.value}"

    selected_triple = (selected.sector, selected.industry, selected.sub_industry)
    conflicting = {
        r.source
        for r in non_empty
        if r is not selected and (r.sector, r.industry, r.sub_industry) != selected_triple
    }
    conflict = bool(conflicting)
    status = (
        ClassificationReviewStatus.CONFLICT if conflict
        else ClassificationReviewStatus.STALE if _is_stale(selected, now)
        else ClassificationReviewStatus.ACCEPTED
    )

    result = []
    for record in records:
        is_selected = record is selected
        if is_selected:
            entry_status, entry_reason = status, reason
        elif record in non_empty and conflict:
            entry_status, entry_reason = ClassificationReviewStatus.CONFLICT, "not_selected_canonical"
        elif record in non_empty:
            entry_status, entry_reason = ClassificationReviewStatus.ACCEPTED, "not_selected_canonical"
        else:
            entry_status, entry_reason = ClassificationReviewStatus.MISSING, "source_supplied_no_value"
        result.append(record.model_copy(update={
            "is_selected_canonical": is_selected,
            "review_status": entry_status,
            "selection_reason": entry_reason,
        }))
    return result


class ClassificationCoverageReport(BaseModel):
    total: int
    sector_covered: int
    industry_covered: int
    sub_industry_covered: int
    sector_coverage: float
    industry_coverage: float
    sub_industry_coverage: float
    by_exchange: dict[str, dict[str, int]]
    by_board: dict[str, dict[str, int]]
    source_distribution: dict[str, int]
    conflict_count: int
    missing_count: int
    stale_count: int
    classification_version: str = CLASSIFICATION_POLICY_VERSION
    generated_at: datetime


def build_classification_coverage_report(
    index: list[SearchIndexRecord], *, now: datetime | None = None,
) -> ClassificationCoverageReport:
    now = now or datetime.now(timezone.utc)
    total = len(index)
    sector_covered = sum(1 for r in index if r.sector)
    industry_covered = sum(1 for r in index if r.industry)
    sub_industry_covered = sum(1 for r in index if r.sub_industry)
    by_exchange: dict[str, dict[str, int]] = {}
    by_board: dict[str, dict[str, int]] = {
        "main": {"total": 0, "industry_covered": 0},
        "sme": {"total": 0, "industry_covered": 0},
    }
    source_distribution: dict[str, int] = {}
    conflict_count = 0
    missing_count = 0
    stale_count = 0
    for record in index:
        exch = record.primary_exchange or "UNKNOWN"
        bucket = by_exchange.setdefault(exch, {"total": 0, "industry_covered": 0, "sector_covered": 0})
        bucket["total"] += 1
        if record.industry:
            bucket["industry_covered"] += 1
        if record.sector:
            bucket["sector_covered"] += 1
        board_key = "sme" if record.is_sme else "main"
        by_board[board_key]["total"] += 1
        if record.industry:
            by_board[board_key]["industry_covered"] += 1
        if record.industry_source:
            source_distribution[record.industry_source] = source_distribution.get(record.industry_source, 0) + 1
        if record.classification_conflict:
            conflict_count += 1
        if not record.industry and not record.sector and not record.sub_industry:
            missing_count += 1
        if record.classification_review_status == ClassificationReviewStatus.STALE.value:
            stale_count += 1
    return ClassificationCoverageReport(
        total=total,
        sector_covered=sector_covered, industry_covered=industry_covered,
        sub_industry_covered=sub_industry_covered,
        sector_coverage=round(sector_covered / total, 4) if total else 0.0,
        industry_coverage=round(industry_covered / total, 4) if total else 0.0,
        sub_industry_coverage=round(sub_industry_covered / total, 4) if total else 0.0,
        by_exchange=by_exchange, by_board=by_board, source_distribution=source_distribution,
        conflict_count=conflict_count, missing_count=missing_count, stale_count=stale_count,
        generated_at=now,
    )
