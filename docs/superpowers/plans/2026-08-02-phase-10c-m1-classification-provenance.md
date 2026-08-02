# Phase 10C Milestone 1: Classification Provenance, Reconciliation & Coverage Reporting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Phase 10B ad hoc single-string classification backfill (`sector_source`/`industry_source`) with a versioned, multi-source classification model that records every source's claim, reconciles them via a documented priority rule that never silently overwrites an existing research-universe classification, flags conflicts, and reports measured coverage — without inferring anything from a company name and without changing the 250 research pages, the ranking/research universes, or any public hash.

**Architecture:** New module `mbe.search.classification` holds `ClassificationRecord` (one source's claim), `select_canonical()` (pure reconciliation function, no I/O), and `build_classification_coverage_report()`. `mbe.search.catalog.build_search_index` is changed to gather one `ClassificationRecord` per source per instrument (exchange-provided search-universe/BSE rows, research-universe rows) into a dict keyed by `instrument_id`, then calls `select_canonical` once per instrument in a final pass to populate `SearchIndexRecord`'s classification fields — replacing the two inline ad hoc backfill blocks. `SearchIndexRecord` (domain.py) gains additive `sub_industry`, `sub_industry_source`, `classification_version`, `classification_confidence`, `classification_review_status`, `classification_selection_reason`, `classification_conflict` fields (all optional/defaulted, so existing JSON consumers and hashes are unaffected). No DB migration: the static build path never touches SQLAlchemy models, and persisting multi-source provenance to `InstrumentRow` is deferred to the future static/dynamic-parity milestone, where a real need (or its absence) can be assessed against actual dynamic-mode requirements — see "Out of scope for this milestone" below.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Typer CLI (existing `src/mbe/cli.py` patterns).

**Out of scope for this milestone (tracked for later Phase 10C milestones, not dropped):** search-ranking policy v3 / prominence signals, lightweight-page v2, `/api/v1/search` and `/api/v1/search/meta` API extensions, frontend result rendering, BSE live-source hardening, static/dynamic parity fixtures, expanded search-quality evaluation set, performance work, accessibility tests, security hardening beyond what's already in place. Each will get its own plan, written fresh against the repository state once this milestone lands, per the "Scope Check" guidance in the writing-plans skill — a single 24-section spec spanning ~10 independent subsystems should not be planned in one document up front, since later tasks would drift from the actual code by the time they're reached.

---

## Verified current state (do not re-derive — read once, trust it)

- `src/mbe/search/domain.py:36-98` — `ExchangeListing`, `SearchIndexRecord` (has `sector`/`sector_source`/`industry`/`industry_source`, no `sub_industry`), `SearchCandidate`.
- `src/mbe/search/catalog.py` — `build_search_index()` (full file, 196 lines). Lines 22-23 define ad hoc `_CLASSIFICATION_SOURCE_EXCHANGE = "exchange_master"` / `_CLASSIFICATION_SOURCE_RESEARCH = "research_universe"` string constants. Lines 103-111 backfill BSE classification onto an existing record only when the field is currently falsy. Lines 151-154 and 181-184 set classification directly from `research`/`row` dicts inside `_merge_record`.
- `src/mbe/search/ranking.py`, `src/mbe/search/evaluation.py` — untouched by this milestone.
- `src/mbe/models/instrument.py:176-178` — `CanonicalInstrument.sector/industry/sub_industry` already exist as plain optional strings (Pydantic model for DB-facing identity, separate from the search-index-facing `SearchIndexRecord`). Not touched by this milestone.
- `src/mbe/db/models.py:31-47,81-82` — `SectorRow`/`IndustryRow` are lookup tables; `InstrumentRow.sector_id`/`industry_id` are single FKs with no provenance. Not touched by this milestone (no migration).
- `universes/nse-search-universe.json` (2,947 rows) — `sector`/`industry` keys exist but are `null` for every row (NSE's official `EQUITY_L.csv`/`SME_EQUITY_L.csv` archives carry no classification columns at all — verified, not assumed).
- `universes/bse-search-universe.json` (20 rows) — `industry` populated for all 20 (e.g. `"Refineries"`, `"IT Consulting & Software"`); no `sector` key.
- `site/api/v1/instruments.json` (250 research-universe rows) — `industry` populated for all 250 (curated during earlier research-universe work); `sector` is `null` for all 250. This confirms sector coverage is genuinely 0 everywhere in the repository, not an oversight — no source anywhere supplies a real sector value, so this milestone's coverage report will legitimately still show 0% sector coverage. That is itself the correct, honest output of a working coverage report, not a bug.
- `tests/test_search_catalog_bse.py` (full file read) — six existing tests assert exact classification-merge behavior that **must keep passing unmodified**: gap-filling from BSE (`test_bse_cross_listing_backfills_missing_industry_with_exchange_source`), first-source-wins on same-priority conflict (`test_bse_cross_listing_never_overwrites_an_existing_industry_classification`), and research always winning over a BSE cross-listing (`test_research_company_still_merges_its_bse_cross_listing`).
- `src/mbe/cli.py:548-574` — `search-quality-evaluate` command is the pattern to mirror for the new `classification-coverage-report` command: reads the same three JSON fixtures, builds the index, runs a report function, prints via `console.print_json`, exits nonzero on a defined failure condition.
- `scripts/verify_release.py` checks file counts, JSON parseability, and (if given a fixture) public score/financial hashes — it does not enumerate exact JSON key sets, so additive fields on `SearchIndexRecord` cannot break it.

---

## File structure

- Create: `src/mbe/search/classification.py` — models, policy, reconciliation, coverage report.
- Modify: `src/mbe/search/domain.py` — add 7 optional fields to `SearchIndexRecord`.
- Modify: `src/mbe/search/catalog.py` — replace ad hoc backfill with calls into `classification.py`.
- Modify: `src/mbe/cli.py` — add `classification-coverage-report` command.
- Create: `tests/test_classification_policy.py` — unit tests for `select_canonical` and the coverage report.
- Modify: `tests/test_search_catalog_bse.py` — no code changes required (existing tests must pass as-is); this file is verification-only in this plan.
- Create: `docs/classification-policy.md` — the classification-source and reconciliation policy document (Phase 10C section 20 deliverable).
- Modify: `docs/search-architecture.md` — update the "Sector/industry and business-description policy" section and the "Known limitations" bullet about sector/industry to point at the new policy doc and versioned coverage numbers.
- Modify: `docs/HANDOVER.md` — add a "Phase 10C Milestone 1" ledger row once verification passes.

---

### Task 1: `ClassificationRecord`, `ClassificationSource`, `ClassificationReviewStatus` models

**Files:**
- Create: `src/mbe/search/classification.py`
- Test: `tests/test_classification_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classification_policy.py
"""Phase 10C Milestone 1: classification provenance and reconciliation.

Every sector/industry/sub-industry value must trace to one of a small,
documented set of sources and must never be inferred from a company name,
ticker, or free text. These tests exercise the pure reconciliation function
in isolation from `mbe.search.catalog` (which is covered separately in
`tests/test_search_catalog_bse.py` for end-to-end merge behavior).
"""

from datetime import datetime, timedelta, timezone

from mbe.search.classification import (
    CLASSIFICATION_POLICY_VERSION,
    ClassificationRecord,
    ClassificationReviewStatus,
    ClassificationSource,
    select_canonical,
)

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _record(source, *, industry=None, sector=None, source_date=None):
    return ClassificationRecord(
        instrument_id="id-1", source=source, sector=sector, industry=industry,
        source_date=source_date, retrieved_at=NOW,
    )


def test_single_exchange_record_is_selected_when_no_research_claim_exists():
    records = [_record(ClassificationSource.EXCHANGE_MASTER, industry="Refineries")]
    result = select_canonical(records, now=NOW)
    selected = next(r for r in result if r.is_selected_canonical)
    assert selected.industry == "Refineries"
    assert selected.review_status == ClassificationReviewStatus.ACCEPTED
    assert selected.selection_reason == "highest_priority_available_source:exchange_master"
    assert selected.classification_version == CLASSIFICATION_POLICY_VERSION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classification_policy.py::test_single_exchange_record_is_selected_when_no_research_claim_exists -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.search.classification'`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/search/classification.py
"""Classification provenance, source-priority reconciliation, and coverage
reporting (Phase 10C section 3).

Every sector/industry/sub-industry value shown anywhere must trace back to
one of a small, documented set of sources — never inferred from a company
name, ticker, or free text. This module keeps every source's classification
claim for an instrument side by side (`ClassificationRecord`), picks exactly
one as canonical via a versioned rule (`select_canonical`), and measures
coverage instead of assuming it (`build_classification_coverage_report`).

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classification_policy.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/search/classification.py tests/test_classification_policy.py
git commit -m "feat(search): add classification provenance and reconciliation model"
```

---

### Task 2: Reconciliation edge cases — research preserved, missing, stale, conflict audit trail

**Files:**
- Modify: `tests/test_classification_policy.py`
- Modify: `src/mbe/search/classification.py` (no change expected if Task 1 is correct — this task is verification-by-test; only touch the implementation if a test genuinely fails)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classification_policy.py`:

```python
def test_research_claim_is_preserved_over_a_conflicting_exchange_claim():
    records = [
        _record(ClassificationSource.EXCHANGE_MASTER, industry="Refineries"),
        _record(ClassificationSource.RESEARCH_UNIVERSE, industry="Oil & Gas"),
    ]
    result = select_canonical(records, now=NOW)
    selected = next(r for r in result if r.is_selected_canonical)
    assert selected.source == ClassificationSource.RESEARCH_UNIVERSE
    assert selected.industry == "Oil & Gas"
    assert selected.review_status == ClassificationReviewStatus.CONFLICT
    assert selected.selection_reason == "research_universe_classification_preserved_over_other_sources"
    non_selected = next(r for r in result if not r.is_selected_canonical)
    assert non_selected.review_status == ClassificationReviewStatus.CONFLICT
    assert non_selected.industry == "Refineries"  # audit trail: the losing claim is kept, not dropped


def test_agreeing_sources_are_accepted_not_flagged_as_conflict():
    records = [
        _record(ClassificationSource.EXCHANGE_MASTER, industry="Refineries"),
        _record(ClassificationSource.RESEARCH_UNIVERSE, industry="Refineries"),
    ]
    result = select_canonical(records, now=NOW)
    selected = next(r for r in result if r.is_selected_canonical)
    assert selected.review_status == ClassificationReviewStatus.ACCEPTED


def test_no_classification_available_reports_missing_not_an_empty_string():
    records = [_record(ClassificationSource.EXCHANGE_MASTER, industry=None, sector=None)]
    result = select_canonical(records, now=NOW)
    assert all(r.review_status == ClassificationReviewStatus.MISSING for r in result)
    assert all(not r.is_selected_canonical for r in result)


def test_stale_source_date_is_flagged_when_no_conflict_exists():
    old_date = NOW - timedelta(days=800)
    records = [_record(ClassificationSource.EXCHANGE_MASTER, industry="Refineries", source_date=old_date)]
    result = select_canonical(records, now=NOW)
    selected = next(r for r in result if r.is_selected_canonical)
    assert selected.review_status == ClassificationReviewStatus.STALE


def test_classification_is_never_inferred_from_company_name_or_symbol():
    """`select_canonical` and `ClassificationRecord` must have no code path
    that reads a name/symbol field to derive a classification — this test
    documents the contract by asserting the function signature/behavior
    depends only on explicit sector/industry/sub_industry inputs."""
    records = [ClassificationRecord(
        instrument_id="id-2", source=ClassificationSource.EXCHANGE_MASTER,
        sector=None, industry=None, sub_industry=None, retrieved_at=NOW,
    )]
    # No display_name/symbol field exists on ClassificationRecord at all —
    # there is nothing for a future change to accidentally read.
    assert not hasattr(records[0], "display_name")
    assert not hasattr(records[0], "symbol")
    result = select_canonical(records, now=NOW)
    assert result[0].review_status == ClassificationReviewStatus.MISSING
```

- [ ] **Step 2: Run tests to verify they fail or pass against the Task 1 implementation**

Run: `python -m pytest tests/test_classification_policy.py -v`
Expected: All PASS if Task 1's implementation is correct (this task is a specification-by-test exercise). If `test_research_claim_is_preserved_over_a_conflicting_exchange_claim` fails, re-check the `research is not None` branch in `select_canonical`.

- [ ] **Step 3: (Only if a test failed) fix `src/mbe/search/classification.py`, then re-run Step 1's command until all pass.**

- [ ] **Step 4: Commit**

```bash
git add tests/test_classification_policy.py
git commit -m "test(search): cover classification reconciliation edge cases"
```

---

### Task 3: Extend `SearchIndexRecord` with classification provenance fields

**Files:**
- Modify: `src/mbe/search/domain.py`
- Test: `tests/test_search_ranking_v2.py` (existing `_record` helper — verify it still constructs successfully with defaults; no assertion changes needed since new fields are optional)

- [ ] **Step 1: Write the failing test**

Start `tests/test_classification_policy.py`'s domain-facing tests with:

```python
from mbe.search.domain import ExchangeListing, SearchIndexRecord, SearchResultType


def _index_record(instrument_id, *, industry=None, sector=None, industry_source=None,
                   is_sme=False, exchange="NSE", conflict=False):
    return SearchIndexRecord(
        instrument_id=instrument_id, display_name=instrument_id, symbol=instrument_id,
        exchange=exchange, primary_exchange=exchange, is_sme=is_sme,
        sector=sector, industry=industry, industry_source=industry_source,
        classification_conflict=conflict,
        listings=[ExchangeListing(exchange=exchange, symbol=instrument_id)],
        result_type=SearchResultType.KNOWN, report_url=f"/company/{instrument_id}.html",
    )


def test_search_index_record_carries_classification_provenance_fields_with_safe_defaults():
    record = _index_record("a")
    assert record.sub_industry is None
    assert record.sub_industry_source is None
    assert record.classification_version is None
    assert record.classification_confidence is None
    assert record.classification_review_status is None
    assert record.classification_selection_reason is None
    assert record.classification_conflict is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classification_policy.py::test_search_index_record_carries_classification_provenance_fields_with_safe_defaults -v`
Expected: FAIL — `_index_record` raises `pydantic.ValidationError` because `SearchIndexRecord` doesn't accept `classification_conflict` yet.

- [ ] **Step 3: Edit `src/mbe/search/domain.py`**

Use the Edit tool with this exact old/new pair:

old_string:
```
    industry: str | None = None
    industry_source: str | None = None
    listing_status: str = "active"
```

new_string:
```
    industry: str | None = None
    industry_source: str | None = None
    sub_industry: str | None = None
    sub_industry_source: str | None = None
    classification_version: str | None = None
    classification_confidence: float | None = None
    classification_review_status: str | None = None
    classification_selection_reason: str | None = None
    classification_conflict: bool = False
    listing_status: str = "active"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classification_policy.py tests/test_search_ranking_v2.py tests/test_search_ranking.py -v`
Expected: All PASS — the new fields are optional/defaulted so no existing `SearchIndexRecord(...)` construction call breaks.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/search/domain.py tests/test_classification_policy.py
git commit -m "feat(search): add classification provenance fields to SearchIndexRecord"
```

---

### Task 4: Coverage report

**Files:**
- Modify: `src/mbe/search/classification.py`
- Modify: `tests/test_classification_policy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_classification_policy.py` (after the Task 3 tests — `_index_record` is already defined above):

```python
from mbe.search.classification import build_classification_coverage_report


def test_coverage_report_measures_totals_by_exchange_board_and_source():
    index = [
        _index_record("a", industry="Refineries", industry_source="exchange_master", exchange="NSE"),
        _index_record("b", industry="Pharma", industry_source="research_universe", exchange="NSE", is_sme=True),
        _index_record("c", industry=None, exchange="BSE"),
        _index_record("d", industry="IT", industry_source="exchange_master", exchange="BSE", conflict=True),
    ]
    report = build_classification_coverage_report(index, now=NOW)
    assert report.total == 4
    assert report.sector_covered == 0
    assert report.industry_covered == 3
    assert report.industry_coverage == 0.75
    assert report.by_exchange["NSE"]["total"] == 2
    assert report.by_exchange["BSE"]["total"] == 2
    assert report.by_board["sme"]["total"] == 1
    assert report.by_board["main"]["total"] == 3
    assert report.source_distribution == {"exchange_master": 2, "research_universe": 1}
    assert report.conflict_count == 1
    assert report.missing_count == 1
    assert report.classification_version == CLASSIFICATION_POLICY_VERSION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classification_policy.py::test_coverage_report_measures_totals_by_exchange_board_and_source -v`
Expected: FAIL with `ImportError: cannot import name 'build_classification_coverage_report'`

- [ ] **Step 3: Append to `src/mbe/search/classification.py`**

First add one import at the top of the file, alongside the existing `from pydantic import BaseModel` line:

old_string:
```
from pydantic import BaseModel

CLASSIFICATION_POLICY_VERSION = "2026-08-02.10c.1"
```

new_string:
```
from pydantic import BaseModel

from mbe.search.domain import SearchIndexRecord

CLASSIFICATION_POLICY_VERSION = "2026-08-02.10c.1"
```

Then append at the end of the file:

```python
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
```

Note: `mbe/search/domain.py` must not import anything from `mbe.search.classification` — the dependency is one-directional (classification.py → domain.py) to avoid a cycle. Task 3 does not add any such import, so this holds.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_classification_policy.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/search/classification.py tests/test_classification_policy.py
git commit -m "feat(search): add classification coverage report"
```

---

### Task 5: Wire `catalog.py` to the new reconciliation engine

**Files:**
- Modify: `src/mbe/search/catalog.py`
- Test: `tests/test_search_catalog.py`, `tests/test_search_catalog_bse.py` (must pass unmodified), `tests/test_classification_policy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_classification_policy.py`:

```python
from mbe.search.catalog import build_search_index


def test_catalog_flags_conflict_when_bse_and_nse_rows_disagree_on_industry():
    nse_row = {
        "source_record_id": "INE000A01018", "company_name": "Alpha Ltd.", "symbol": "ALPHA",
        "exchange": "NSE", "exchange_segment": None, "series": "EQ", "isin": "INE000A01018",
        "bse_code": None, "industry": "Oil & Gas", "sector": None, "listing_status": "active",
        "listing_date": None, "delisting_date": None, "is_sme": False, "security_type": "equity",
        "provider_symbols": {"yahoo": "ALPHA.NS"}, "aliases": [],
    }
    bse_row = {
        "source_record_id": "INE000A01018", "company_name": "Alpha Ltd.", "symbol": "ALPHA",
        "exchange": "BSE", "exchange_segment": None, "series": "A", "isin": "INE000A01018",
        "bse_code": "500700", "industry": "Refineries", "sector": None, "listing_status": "active",
        "listing_date": None, "delisting_date": None, "is_sme": False, "security_type": "equity",
    }
    index = build_search_index([nse_row], [], [], bse_rows=[bse_row])
    assert len(index) == 1
    record = index[0]
    assert record.industry == "Oil & Gas"  # first-registered exchange_master source wins the tie
    assert record.classification_conflict is True
    assert record.classification_review_status == "conflict"
    assert record.classification_version == CLASSIFICATION_POLICY_VERSION


def test_catalog_reports_missing_when_no_source_supplies_a_classification():
    nse_row = {
        "source_record_id": "INE111A01011", "company_name": "Beta Ltd.", "symbol": "BETA",
        "exchange": "NSE", "exchange_segment": None, "series": "EQ", "isin": "INE111A01011",
        "bse_code": None, "industry": None, "sector": None, "listing_status": "active",
        "listing_date": None, "delisting_date": None, "is_sme": False, "security_type": "equity",
        "provider_symbols": {"yahoo": "BETA.NS"}, "aliases": [],
    }
    index = build_search_index([nse_row], [], [])
    record = index[0]
    assert record.industry is None
    assert record.classification_review_status == "missing"
    assert record.classification_conflict is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_classification_policy.py::test_catalog_flags_conflict_when_bse_and_nse_rows_disagree_on_industry -v`
Expected: FAIL — `classification_conflict` stays `False` because `catalog.py` doesn't populate it yet.

- [ ] **Step 3: Edit `src/mbe/search/catalog.py`**

Replace the module-level constants and docstring reference (old lines 18-23):

old_string:
```
# Classification-source priority (Phase 10B section 10): exchange-provided
# industry classification is preferred over the existing canonical research
# classification, which is preferred over "unavailable". Neither source is
# ever inferred from a company name.
_CLASSIFICATION_SOURCE_EXCHANGE = "exchange_master"
_CLASSIFICATION_SOURCE_RESEARCH = "research_universe"
```

new_string:
```
from mbe.search.classification import ClassificationRecord, ClassificationSource, select_canonical
```

(Move this new import line up next to the other `from mbe...` imports at the top of the file instead of leaving it mid-file — place it alongside the existing `from mbe.models.instrument import stable_instrument_id` line.)

Replace `_merge_record`'s classification assignment in the `research` branch (old):

old_string:
```
            sector=research.get("sector"),
            sector_source=_CLASSIFICATION_SOURCE_RESEARCH if research.get("sector") else None,
            industry=research.get("industry"),
            industry_source=_CLASSIFICATION_SOURCE_RESEARCH if research.get("industry") else None,
```

new_string:
```
            sector=None, sector_source=None, industry=None, industry_source=None,
```

Replace `_merge_record`'s classification assignment in the row-only branch (old):

old_string:
```
        sector=row.get("sector"),
        sector_source=_CLASSIFICATION_SOURCE_EXCHANGE if row.get("sector") else None,
        industry=row.get("industry"),
        industry_source=_CLASSIFICATION_SOURCE_EXCHANGE if row.get("industry") else None,
```

new_string:
```
        sector=None, sector_source=None, industry=None, industry_source=None,
```

Replace the BSE-cross-listing backfill block inside `build_search_index` (old):

old_string:
```
        existing = records.get(instrument_id)
        if existing:
            listing = _listing_from_row(row, is_primary=False)
            existing.listings = [*existing.listings, listing]
            if not existing.bse_code:
                existing.bse_code = row.get("bse_code")
            # Classification reconciliation (Phase 10B section 10): backfill
            # only when missing — never silently overwrite an existing
            # (e.g. NSE-sourced) classification with the BSE one.
            if not existing.sector and row.get("sector"):
                existing.sector = row["sector"]
                existing.sector_source = _CLASSIFICATION_SOURCE_EXCHANGE
            if not existing.industry and row.get("industry"):
                existing.industry = row["industry"]
                existing.industry_source = _CLASSIFICATION_SOURCE_EXCHANGE
            continue
        research = research_by_id.get(instrument_id)
        values = screener_by_id.get(instrument_id)
        records[instrument_id] = _merge_record(instrument_id, row, research, values)

    return list(records.values())
```

new_string:
```
        classification_inputs.setdefault(instrument_id, []).append(
            _classification_record(instrument_id, row, source=ClassificationSource.EXCHANGE_MASTER)
        )
        existing = records.get(instrument_id)
        if existing:
            listing = _listing_from_row(row, is_primary=False)
            existing.listings = [*existing.listings, listing]
            if not existing.bse_code:
                existing.bse_code = row.get("bse_code")
            continue
        research = research_by_id.get(instrument_id)
        values = screener_by_id.get(instrument_id)
        records[instrument_id] = _merge_record(instrument_id, row, research, values)

    for instrument_id, record in records.items():
        candidates = classification_inputs.get(instrument_id, [])
        reconciled = select_canonical(candidates) if candidates else []
        selected = next((r for r in reconciled if r.is_selected_canonical), None)
        record.sector = selected.sector if selected else None
        record.industry = selected.industry if selected else None
        record.sub_industry = selected.sub_industry if selected else None
        record.sector_source = selected.source.value if selected and selected.sector else None
        record.industry_source = selected.source.value if selected and selected.industry else None
        record.sub_industry_source = selected.source.value if selected and selected.sub_industry else None
        record.classification_version = selected.classification_version if selected else (
            reconciled[0].classification_version if reconciled else None
        )
        record.classification_confidence = selected.confidence if selected else None
        record.classification_review_status = (
            selected.review_status.value if selected
            else (reconciled[0].review_status.value if reconciled else None)
        )
        record.classification_selection_reason = selected.selection_reason if selected else (
            reconciled[0].selection_reason if reconciled else None
        )
        record.classification_conflict = any(
            r.review_status.value == "conflict" for r in reconciled
        )

    return list(records.values())
```

Now add the `_classification_record` helper and the `classification_inputs` dict initialization. Add the helper function right after `_listing_from_row`:

old_string:
```
def _listing_from_row(row: dict[str, Any], *, is_primary: bool) -> ExchangeListing:
    return ExchangeListing(
        exchange=row.get("exchange", "NSE"), symbol=row["symbol"],
        bse_code=row.get("bse_code"), isin=row.get("isin"),
        listing_status=row.get("listing_status") or "active",
        is_primary=is_primary, is_sme=row.get("is_sme"),
    )
```

new_string:
```
def _listing_from_row(row: dict[str, Any], *, is_primary: bool) -> ExchangeListing:
    return ExchangeListing(
        exchange=row.get("exchange", "NSE"), symbol=row["symbol"],
        bse_code=row.get("bse_code"), isin=row.get("isin"),
        listing_status=row.get("listing_status") or "active",
        is_primary=is_primary, is_sme=row.get("is_sme"),
    )


def _classification_record(
    instrument_id: str, data: dict[str, Any], *, source: ClassificationSource,
) -> ClassificationRecord:
    from datetime import datetime, timezone
    return ClassificationRecord(
        instrument_id=instrument_id, source=source,
        sector=data.get("sector"), industry=data.get("industry"),
        sub_industry=data.get("sub_industry"),
        source_record_id=data.get("source_record_id") or data.get("isin") or data.get("symbol"),
        retrieved_at=datetime.now(timezone.utc),
    )
```

Now update `build_search_index`'s opening to declare `classification_inputs` and register the two other sources (search-universe rows and research rows). Old:

old_string:
```
    research_by_id = {row["instrument_id"]: row for row in (research_instruments or [])}
    screener_by_id = {row["instrument_id"]: row["values"] for row in (screener_rows or [])}

    records: dict[str, SearchIndexRecord] = {}

    for row in search_universe_rows:
        instrument_id = _canonical_id(symbol=row["symbol"], isin=row.get("isin"), exchange=row.get("exchange", "NSE"))
        research = research_by_id.get(instrument_id)
        values = screener_by_id.get(instrument_id)
        records[instrument_id] = _merge_record(instrument_id, row, research, values)

    for instrument_id, research in research_by_id.items():
        if instrument_id in records:
            continue
        values = screener_by_id.get(instrument_id)
        records[instrument_id] = _merge_record(instrument_id, None, research, values)
```

new_string:
```
    research_by_id = {row["instrument_id"]: row for row in (research_instruments or [])}
    screener_by_id = {row["instrument_id"]: row["values"] for row in (screener_rows or [])}

    records: dict[str, SearchIndexRecord] = {}
    classification_inputs: dict[str, list[ClassificationRecord]] = {}

    for row in search_universe_rows:
        instrument_id = _canonical_id(symbol=row["symbol"], isin=row.get("isin"), exchange=row.get("exchange", "NSE"))
        research = research_by_id.get(instrument_id)
        values = screener_by_id.get(instrument_id)
        classification_inputs.setdefault(instrument_id, []).append(
            _classification_record(instrument_id, row, source=ClassificationSource.EXCHANGE_MASTER)
        )
        if research:
            classification_inputs[instrument_id].append(
                _classification_record(instrument_id, research, source=ClassificationSource.RESEARCH_UNIVERSE)
            )
        records[instrument_id] = _merge_record(instrument_id, row, research, values)

    for instrument_id, research in research_by_id.items():
        if instrument_id in records:
            continue
        classification_inputs.setdefault(instrument_id, []).append(
            _classification_record(instrument_id, research, source=ClassificationSource.RESEARCH_UNIVERSE)
        )
        values = screener_by_id.get(instrument_id)
        records[instrument_id] = _merge_record(instrument_id, None, research, values)
```

- [ ] **Step 4: Run tests to verify everything passes**

Run: `python -m pytest tests/test_classification_policy.py tests/test_search_catalog.py tests/test_search_catalog_bse.py -v`
Expected: All PASS, including the six pre-existing `test_search_catalog_bse.py` tests unmodified (this is the critical regression check — if `test_bse_cross_listing_never_overwrites_an_existing_industry_classification` fails, check that `search_universe_rows` are processed into `classification_inputs` before `bse_rows`, so `min()`'s stable tie-break picks the NSE-registered record first).

- [ ] **Step 5: Run the full existing Python test suite**

Run: `python -m pytest tests/ -q`
Expected: 615 + new tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/search/catalog.py tests/test_classification_policy.py
git commit -m "feat(search): reconcile classification through the versioned policy engine"
```

---

### Task 6: `classification-coverage-report` CLI command

**Files:**
- Modify: `src/mbe/cli.py`
- Test: manual CLI run (Typer commands in this codebase are not unit-tested individually elsewhere — follow the existing convention of a manual verification step, matching how `search-quality-evaluate` is verified)

- [ ] **Step 1: Add the command**

Insert after the existing `search_quality_evaluate` command (after line 574 in the current file) in `src/mbe/cli.py`:

old_string:
```
    report = evaluate_search_quality(index, ranker=rank_search_candidates)
    console.print_json(data=report)
    if report["top1_accuracy"] < 1.0 or report["false_positive_count"] > 0:
        raise typer.Exit(1)


@app.command("search-inspect")
```

new_string:
```
    report = evaluate_search_quality(index, ranker=rank_search_candidates)
    console.print_json(data=report)
    if report["top1_accuracy"] < 1.0 or report["false_positive_count"] > 0:
        raise typer.Exit(1)


@app.command("classification-coverage-report")
def classification_coverage_report(
    search_universe: Path = typer.Option(Path("universes/nse-search-universe.json")),
    bse_universe: Path = typer.Option(Path("universes/bse-search-universe.json")),
    instruments: Path = typer.Option(
        Path("site/api/v1/instruments.json"), help="Static research-universe snapshot, if built"
    ),
):
    """Report measured sector/industry/sub-industry coverage, by exchange
    and main-board/SME, plus source distribution and conflict/missing/stale
    counts (Phase 10C section 3). Fully offline; never claims coverage
    beyond what the merged search index actually has."""
    from mbe.search.catalog import build_search_index
    from mbe.search.classification import build_classification_coverage_report

    search_rows = json.loads(search_universe.read_text())["records"]
    bse_rows = json.loads(bse_universe.read_text())["records"] if bse_universe.exists() else []
    research = json.loads(instruments.read_text())["data"] if instruments.exists() else []
    index = build_search_index(search_rows, research, [], bse_rows=bse_rows)
    report = build_classification_coverage_report(index)
    console.print_json(data=report.model_dump(mode="json"))


@app.command("search-inspect")
```

- [ ] **Step 2: Verify the command runs against real fixtures**

Run: `uv run mbe classification-coverage-report`
Expected: JSON output with `"total": 2947`, `"industry_covered": 270`, `"sector_covered": 0`, `"industry_coverage": 0.0916` (rounded), a non-empty `source_distribution` (`{"research_universe": <=250, "exchange_master": <=20}` after accounting for any research/BSE overlap on the same instrument), and `"classification_version": "2026-08-02.10c.1"`. Exit code 0.

- [ ] **Step 3: Commit**

```bash
git add src/mbe/cli.py
git commit -m "feat(cli): add classification-coverage-report command"
```

---

### Task 7: Documentation

**Files:**
- Create: `docs/classification-policy.md`
- Modify: `docs/search-architecture.md`
- Modify: `docs/HANDOVER.md`

- [ ] **Step 1: Create `docs/classification-policy.md`**

```markdown
# Classification-source policy (Phase 10C Milestone 1)

Every sector/industry/sub-industry value shown anywhere in search results or
company pages traces to one of four documented sources, in this priority
order for filling an otherwise-unclaimed instrument:

1. Official exchange-provided classification (`exchange_master` — currently
   the curated BSE starter fixture's `Industry` column; NSE's official
   `EQUITY_L.csv`/`SME_EQUITY_L.csv` archives carry no classification
   columns at all, verified not assumed).
2. Official index-provider classification already available in the
   repository (`index_provider` — not currently populated by any source).
3. Existing research-universe classification (`research_universe` — the
   250 research-universe companies' curated `industry` values).
4. Documented stable public classification source (`documented_public` —
   not currently populated by any source).
5. Missing.

**No classification is ever inferred from a company name, ticker symbol, or
free text.** `mbe.search.classification.ClassificationRecord` has no
name/symbol field for a future change to accidentally read.

## The no-overwrite-research rule

A research-universe classification, once it exists for an instrument, is
always kept as canonical over every other source — this does not contradict
the priority order above, which governs which source wins when *nothing*
has been classified yet. Once a company has a published research page with
a curated industry label, a generic exchange-provided category label must
never silently replace it. The losing claim is still recorded (not
discarded) and the instrument is flagged `review_status: conflict` when the
two sources materially disagree, so the disagreement is visible rather than
hidden.

## Versioning

`CLASSIFICATION_POLICY_VERSION` (`src/mbe/search/classification.py`) is
stamped on every classification record and selection. Current version:
`2026-08-02.10c.1`. Bump this string whenever the priority order or
reconciliation rule changes.

## Measured coverage (as of this milestone)

Run `uv run mbe classification-coverage-report` for current numbers. As of
this milestone: industry 270/2,947 (9.16%) — 250 from `research_universe`,
20 from `exchange_master` (BSE curated fixture) with zero overlap after
reconciliation (BSE-cross-listed research companies keep their research
industry value); sector 0/2,947 (0%) — genuinely no source in this
repository supplies a sector value for any of the 2,947 search-universe
companies, including the 250 research-universe companies. This is measured,
not assumed; the coverage report recomputes it from the live merged index
every run rather than hard-coding a number.

## Known limitations

- Sub-industry is never populated by any current source.
- "Stale" detection compares a classification's `source_date` (when
  supplied) against a 730-day threshold, but no current source supplies a
  `source_date` distinct from the build's own retrieval timestamp — so
  `stale_count` is structurally implemented but will read 0 until source
  retrieval timestamps are persisted across builds (a dynamic-mode/DB
  concern, deferred to a future milestone).
- Reconciliation operates at the whole-record level (a source's
  sector+industry+sub_industry claim is accepted or rejected together), not
  per individual field, because no current source supplies a partial
  combination that would require field-level merging. This is documented
  here so a future source with partial-field coverage doesn't silently
  produce a wrong reconciliation.
- Adding a genuinely reliable sector source (an official exchange sectoral
  classification file, or a documented public GICS/ICB mapping) is out of
  scope for this milestone — no such source was verified reachable or
  license-clear from this repository's environment. Raising sector coverage
  requires acquiring and verifying such a source first, not inferring one.
```

- [ ] **Step 2: Update `docs/search-architecture.md`**

Replace the "Sector/industry and business-description policy" section's first paragraph:

old_string:
```
## Sector/industry and business-description policy

Neither the NSE nor the curated BSE source currently supplies a real
`sector` value (`sector_coverage: 0` outside the research universe, which
itself has none either — a pre-existing Phase 0/1 characteristic, not new
in this phase). `industry` is populated for the 250 research-universe
companies (source `"research_universe"`) plus the 20 BSE-cross-linked
companies whose curated fixture carries a real, well-known industry label
(source `"exchange_master"`) — 270 total. Sector/industry are never
inferred from a company name; when absent, the UI shows "Sector
unavailable" / "Industry unavailable" rather than guessing. No business
description exists anywhere outside the research universe — no LLM
generation, no company-website scraping, no competitor-description copying
was introduced; the lightweight page states this plainly rather than
inventing prose.
```

new_string:
```
## Sector/industry and business-description policy

As of Phase 10C Milestone 1, every classification is tracked with full
source provenance, versioned, and reconciled through a documented priority
rule rather than an inline backfill — see `docs/classification-policy.md`
for the full policy, the no-overwrite-research rule, and measured coverage
numbers (`uv run mbe classification-coverage-report`). In short: neither
the NSE nor the curated BSE source currently supplies a real `sector` value
(`sector_coverage: 0` outside the research universe, which itself has none
either — a pre-existing Phase 0/1 characteristic, not new in this phase).
`industry` is populated for the 250 research-universe companies (source
`"research_universe"`) plus the 20 BSE-cross-linked companies whose curated
fixture carries a real, well-known industry label (source
`"exchange_master"`) — 270 total. Sector/industry are never inferred from a
company name; when absent, the UI shows "Sector unavailable" / "Industry
unavailable" rather than guessing. No business description exists anywhere
outside the research universe — no LLM generation, no company-website
scraping, no competitor-description copying was introduced; the lightweight
page states this plainly rather than inventing prose.
```

Replace the "Known limitations" sector/industry bullet:

old_string:
```
- Neither NSE nor the curated BSE source supplies real `sector` values;
  `industry` coverage is 270/2,947 (250 research-universe + 20 BSE
  cross-linked). No sector/industry is ever inferred from a company name.
```

new_string:
```
- Neither NSE nor the curated BSE source supplies real `sector` values;
  `industry` coverage is 270/2,947 (250 research-universe + 20 BSE
  cross-linked). No sector/industry is ever inferred from a company name.
  Classification is now source-versioned and conflict-tracked — see
  `docs/classification-policy.md` (Phase 10C Milestone 1).
```

- [ ] **Step 3: Add a Phase 10C Milestone 1 row to `docs/HANDOVER.md`**

Insert after the existing Phase 10B row (matching the table's exact column format: Phase | Status | What shipped | Verification | Deployment/notes):

```markdown
| Phase 10C Milestone 1 — classification provenance, reconciliation and coverage reporting | Complete | Versioned classification-source policy (`mbe.search.classification`, `CLASSIFICATION_POLICY_VERSION`) replacing the Phase 10B ad hoc single-string backfill; every source's classification claim is kept side by side and reconciled through a documented priority rule (exchange-provided > index-provider > research-universe > documented-public for filling a gap; a research-universe claim, once present, is never silently overwritten); conflict/missing/stale review states; measured coverage report by exchange and main-board/SME with source distribution (`classification-coverage-report` CLI); `docs/classification-policy.md` | <N> Python tests (+<n>) passed; ESLint/type-check/compileall/`git diff --check` passed; static release verifier passed (unchanged file counts and hashes — additive `SearchIndexRecord` fields only); measured coverage unchanged in substance (industry 270/2,947, sector 0/2,947) but now versioned and conflict-tracked; no migration/canonical-ID/scoring/ranking/financial-value change | Working tree only; not committed/pushed/deployed; no DB persistence of multi-source provenance yet — deferred to the static/dynamic-parity milestone |
```

(Fill in `<N>`/`<n>` with the actual counts from Task 8's verification run before committing this doc change.)

- [ ] **Step 4: Commit**

```bash
git add docs/classification-policy.md docs/search-architecture.md docs/HANDOVER.md
git commit -m "docs: record Phase 10C Milestone 1 classification policy"
```

---

### Task 8: Full verification suite

**Files:** none (verification only)

- [ ] **Step 1: Full Python test suite**

Run: `python -m pytest tests/ -q`
Expected: 0 failures. Record the total count for Task 7 Step 3's doc row.

- [ ] **Step 2: Frontend tests**

Run: `node --test tests/frontend/*.test.js`
Expected: 0 failures (this milestone touches no frontend code, so this is a pure regression check).

- [ ] **Step 3: Lint and type checks**

Run: `npx eslint .`
Run: `python -m compileall src`
Expected: 0 errors for both. (Skip `tsc`/`npx tsc --noEmit` if no `.ts`/checked `.js` files changed — this milestone is Python-only plus one Python-generated JSON field addition.)

- [ ] **Step 4: Search-quality evaluation regression**

Run: `uv run mbe search-quality-evaluate`
Expected: `top1_accuracy: 1.0`, `false_positive_count: 0` — unchanged from the Phase 10B baseline, since ranking logic was not touched this milestone.

- [ ] **Step 5: Classification coverage report**

Run: `uv run mbe classification-coverage-report`
Expected: `industry_coverage` ≈ `0.0916`, `sector_coverage: 0.0`, `conflict_count: 0` (no known conflicting real-world instrument in the current fixtures), `missing_count` ≈ 2677.

- [ ] **Step 6: Static build and release verifier**

Run: `python scripts/build_site.py` (or the project's documented build entrypoint — confirm exact command in `docs/HANDOVER.md`'s "Deployment notes" section if this differs)
Run: `python scripts/verify_release.py`
Expected: file counts unchanged (279 HTML, 508 JSON, 250 company, 25 legacy, 253 sitemap/indexable), all checks pass, public score/financial hashes unchanged.

- [ ] **Step 7: `git diff --check`**

Run: `git diff --check`
Expected: no output (no whitespace errors).

- [ ] **Step 8: Inspect the diff for drift**

Run: `git diff --stat` and skim `git diff -- src/mbe/search/ src/mbe/cli.py`
Confirm: no changes to `universes/*.json`, no changes to `site/api/v1/instruments.json` content values (only regenerated `search-index.json` should differ, and only by gaining new optional keys), no canonical-ID changes, no score/financial value changes, no fabricated classification values (every new `industry`/`sector` value present in the diff must already have existed in `universes/bse-search-universe.json` or `site/api/v1/instruments.json` verbatim).

- [ ] **Step 9: Final commit if Step 6 regenerated `site/`**

```bash
git add site/
git commit -m "chore: rebuild static site for Phase 10C Milestone 1"
```

(Skip this step if the build output is gitignored or unchanged.)

---

## Definition of done for this milestone

- [ ] All 8 tasks' steps checked off.
- [ ] Full existing test suite (615 Python, 28 frontend) still passes, plus new classification tests.
- [ ] `classification-coverage-report` CLI command exists and runs offline against pinned fixtures.
- [ ] `docs/classification-policy.md` exists; `docs/search-architecture.md` and `docs/HANDOVER.md` updated.
- [ ] No canonical-ID, score, financial-value, research-universe, or ranking-universe change.
- [ ] No migration created.
- [ ] Release verifier passes with unchanged file counts and hashes.
- [ ] Recommended next milestone noted (Milestone 2: search-ranking policy v3 + defensible prominence signals, building on this milestone's `classification_review_status`/`classification_conflict` fields as one of several late tie-breakers — to be planned fresh once this lands).
