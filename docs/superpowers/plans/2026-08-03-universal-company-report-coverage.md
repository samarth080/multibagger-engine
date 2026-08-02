# Universal Company Report Coverage (Phase 11 Milestone 2A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every search-universe instrument resolves to `/company/{instrument_id}.html` with a report whose depth is one of four deterministic, versioned coverage levels (0 Identity, 1 Market, 2 Fundamentals, 3 Full Research), exposed through the page, search and the API — without changing the 250 existing Level-3 pages' data, hashes, or the deterministic offline build.

**Architecture:** A new `src/mbe/coverage/` package holds a pure, deterministic policy function (`assess_coverage`) that is the single source of truth for level assignment. It's called from three places that must never disagree: `mbe.search.catalog.build_search_index()` (embeds coverage fields directly into `SearchIndexRecord`, so `search-index.json` becomes the one bundled artifact every consumer reads), the `api/company.py` serverless fallback (renders Levels 0–2 on demand via a new `build_coverage_research()` composed on top of the existing, untouched `build_lightweight_research()`), and the FastAPI app (a new `/coverage` route plus additive fields on the existing `/summary` route). The 250 static Level-3 pages are unmodified in data/logic; they get one added, hardcoded coverage badge line in their template. A new offline stage aggregates the already-computed per-record levels into a small `research-coverage.json` reporting artifact.

**Tech Stack:** Python 3 / pydantic v2 (`mbe.coverage`, `mbe.research`, `mbe.search`, `mbe.api`), Jinja2 templates, vanilla JS frontend (`app.js`), pytest, `node --test`.

**Full design reference:** `docs/superpowers/specs/2026-08-03-universal-company-report-coverage-design.md`

---

## File structure

New:
- `src/mbe/coverage/__init__.py`
- `src/mbe/coverage/domain.py` — `CoverageLevel`, level→label/sections tables, `CoverageAssessment`
- `src/mbe/coverage/policy.py` — `RESEARCH_COVERAGE_POLICY_VERSION`, `assess_coverage()`
- `src/mbe/research/coverage.py` — `build_coverage_research()` (Levels 0–2 payload, composes `build_lightweight_research`)
- `src/mbe/frontend/templates/company_coverage.html` (renamed from `company_lightweight.html`, extended)
- `scripts/build_coverage_artifact.py`
- `tests/test_coverage_policy.py`
- `tests/test_research_coverage.py`
- `tests/test_publish_coverage.py` (renamed from `tests/test_publish_lightweight.py`, extended)
- `tests/test_coverage_artifact.py`
- `docs/coverage-architecture.md`

Modified:
- `src/mbe/search/domain.py` — additive `SearchIndexRecord` coverage fields
- `src/mbe/search/catalog.py` — `build_search_index()` calls `assess_coverage()` per record
- `src/mbe/publish.py` — `render_lightweight_company_page` → `render_coverage_company_page`
- `src/mbe/frontend/templates/company.html` — one added coverage badge line
- `src/mbe/builds/offline.py` — new `build_coverage_only()`
- `api/company.py` — computes coverage, calls the new builder/renderer
- `src/mbe/api/app.py` — new `/coverage` route, extended `/summary` route
- `src/mbe/api/schemas.py` — additive `CompanySummaryData`/new `CoverageData` fields
- `src/mbe/frontend/assets/app.js` — search result coverage badges
- `vercel.json` — bundle `search-index.json` into `api/v1.py`
- `tests/test_search_catalog.py`, `tests/test_company_fn.py`, `tests/test_api_v1.py`, `tests/test_deterministic_build.py`, `tests/test_release_readiness.py`, `tests/frontend/app.test.js` — extended
- `docs/HANDOVER.md`

Deleted:
- `tests/test_research_lightweight.py` content merges into `tests/test_research_coverage.py` (the base identity/quote assertions carry over unchanged; `build_lightweight_research` itself is NOT deleted — see Task 3)

---

### Task 1: Coverage domain types

**Files:**
- Create: `src/mbe/coverage/__init__.py`
- Create: `src/mbe/coverage/domain.py`
- Test: `tests/test_coverage_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage_policy.py (new file — this task only adds the domain-shape tests)
from mbe.coverage.domain import (
    ALL_SECTIONS, COVERAGE_LEVEL_LABELS, COVERAGE_LEVEL_SECTIONS, CoverageAssessment,
    CoverageLevel,
)


def test_coverage_level_values_are_ordered_0_to_3():
    assert [int(level) for level in CoverageLevel] == [0, 1, 2, 3]


def test_every_level_has_a_public_label():
    for level in CoverageLevel:
        assert COVERAGE_LEVEL_LABELS[level].startswith(f"Level {int(level)} — ")


def test_section_tables_are_nested_and_cover_all_sections():
    identity = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.IDENTITY])
    market = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.MARKET])
    fundamentals = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.FUNDAMENTALS])
    full = set(COVERAGE_LEVEL_SECTIONS[CoverageLevel.FULL_RESEARCH])
    assert identity <= market <= fundamentals <= full
    assert full == set(ALL_SECTIONS)
    assert "score" in full and "score" not in fundamentals


def test_coverage_assessment_round_trips_through_json():
    payload = CoverageAssessment(
        instrument_id="abc-123", company_id=None,
        research_coverage_level=1, coverage_label="Level 1 — Market Coverage",
        coverage_level_version="1.0", research_coverage_status="active",
        research_eligible=False, research_eligibility_reasons=["not_in_model_universe"],
        research_sections_available=["identity", "quote"],
        research_sections_missing=["financial_summary", "score"],
        research_universe=None, ranking_available=False, model_available=False,
        financial_available=False, quote_available=True,
        identity_completeness="complete", source_quality_summary="Identity and live market data.",
        evaluated_at="2026-08-03T00:00:00+00:00", coverage_policy_version="2026-08-03.11.2a.1",
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["research_coverage_level"] == 1
    assert CoverageAssessment.model_validate(dumped) == payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.coverage'`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/coverage/__init__.py
```
(empty — marks the package)

```python
# src/mbe/coverage/domain.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_coverage_policy.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/mbe/coverage tests/test_coverage_policy.py
git commit -m "feat(coverage): add coverage-level domain types"
```

---

### Task 2: Coverage policy — `assess_coverage()`

**Files:**
- Create: `src/mbe/coverage/policy.py`
- Test: `tests/test_coverage_policy.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coverage_policy.py (append)
from datetime import datetime, timezone

import pytest

from mbe.coverage.policy import RESEARCH_COVERAGE_POLICY_VERSION, assess_coverage

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

BASE_RECORD = {
    "instrument_id": "abc-123", "company_id": None, "isin": "INE002A01018",
    "bse_code": None, "legal_name": "Reliance Industries Limited",
    "listing_status": "active", "is_sme": False, "provider_symbol": None,
}


def test_level_0_when_no_quote_provider_mapping():
    result = assess_coverage(
        BASE_RECORD, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 0
    assert result.coverage_label == "Level 0 — Identity Coverage"
    assert result.research_eligible is False
    assert "no_quote_provider_mapping" in result.research_eligibility_reasons
    assert result.research_sections_available == ["identity"]
    assert "quote" in result.research_sections_missing


def test_level_1_when_quote_mapping_but_no_financials_or_model():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 1
    assert result.coverage_label == "Level 1 — Market Coverage"
    assert result.quote_available is True
    assert result.financial_available is False
    assert "no_financial_data" in result.research_eligibility_reasons


def test_level_2_when_financial_data_but_no_model_score():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=True, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 2
    assert result.coverage_label == "Level 2 — Financial Coverage"
    assert result.financial_available is True
    assert result.model_available is False
    assert "not_in_model_universe" in result.research_eligibility_reasons


def test_level_2_requires_quote_mapping_even_with_financial_data():
    """Financial data without a quote mapping doesn't happen today, but the
    policy encodes the real invariant rather than assuming it can't."""
    result = assess_coverage(
        BASE_RECORD, has_financial_data=True, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 0


def test_level_3_requires_both_model_score_and_full_research_payload():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=True, has_model_score=True,
        has_full_research_payload=True, now=NOW,
    )
    assert result.research_coverage_level == 3
    assert result.coverage_label == "Level 3 — Full Research"
    assert result.research_eligible is True
    assert result.research_eligibility_reasons == ["in_smallcap_research_universe"]
    assert result.research_universe == "Nifty Smallcap 250"
    assert "score" in result.research_sections_available
    assert result.research_sections_missing == []


def test_model_score_without_full_payload_does_not_promote_to_level_3():
    record = {**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}
    result = assess_coverage(
        record, has_financial_data=True, has_model_score=True,
        has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_level == 2


def test_invalid_identity_is_rejected():
    with pytest.raises(ValueError, match="instrument_id"):
        assess_coverage(
            {**BASE_RECORD, "instrument_id": ""}, has_financial_data=False,
            has_model_score=False, has_full_research_payload=False, now=NOW,
        )


def test_identity_completeness_reflects_isin_and_legal_name():
    complete = assess_coverage(
        BASE_RECORD, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert complete.identity_completeness == "complete"
    partial = assess_coverage(
        {**BASE_RECORD, "isin": None, "legal_name": None}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    assert partial.identity_completeness == "partial"


def test_inactive_listing_status_is_reflected_in_coverage_status():
    result = assess_coverage(
        {**BASE_RECORD, "listing_status": "delisted"}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    assert result.research_coverage_status == "inactive_listing"


def test_policy_version_is_stamped_on_every_assessment():
    result = assess_coverage(
        BASE_RECORD, has_financial_data=False, has_model_score=False,
        has_full_research_payload=False, now=NOW,
    )
    assert result.coverage_policy_version == RESEARCH_COVERAGE_POLICY_VERSION == "2026-08-03.11.2a.1"


def test_no_fake_score_fields_below_level_3():
    for level_kwargs in (
        {"has_financial_data": False, "has_model_score": False, "has_full_research_payload": False},
        {"has_financial_data": True, "has_model_score": False, "has_full_research_payload": False},
    ):
        result = assess_coverage({**BASE_RECORD, "provider_symbol": "RELIANCE.NS"}, now=NOW, **level_kwargs)
        assert result.research_coverage_level < 3
        assert "score" not in result.research_sections_available
        assert "rank" not in result.research_sections_available
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.coverage.policy'`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/coverage/policy.py
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

    if has_model_score and has_full_research_payload:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_coverage_policy.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/mbe/coverage/policy.py tests/test_coverage_policy.py
git commit -m "feat(coverage): add deterministic assess_coverage policy"
```

---

### Task 3: Coverage-aware research payload — `build_coverage_research()`

Composes the existing, untouched `build_lightweight_research()` rather than
replacing it, so its 13 existing tests in `tests/test_research_lightweight.py`
keep passing unmodified and keep exercising the shared identity/quote logic.

**Files:**
- Create: `src/mbe/research/coverage.py`
- Create: `tests/test_research_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_research_coverage.py
from datetime import datetime, timezone

import pytest

from mbe.coverage.policy import assess_coverage
from mbe.research.coverage import build_coverage_research

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

RECORD = {
    "instrument_id": "abc-123", "company_id": None,
    "display_name": "Reliance Industries Limited", "legal_name": "Reliance Industries Limited",
    "symbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018", "bse_code": None,
    "sector": None, "industry": None, "listing_status": "active", "is_sme": False,
    "market_cap_category": None, "aliases": [], "provider_symbol": "RELIANCE.NS",
    "result_type": "known", "research_available": False,
    "rank": None, "multibagger_score": None, "confidence": None, "risk_score": None,
    "report_url": "/company/abc-123.html",
}
QUOTE = {"price": 2945.5, "currency": "INR", "market_status": "open", "day_change_pct": 1.2,
         "week52_high": 3217.9, "week52_low": 2221.0}


def _coverage(**kwargs):
    defaults = {"has_financial_data": False, "has_model_score": False, "has_full_research_payload": False}
    return assess_coverage(RECORD, now=NOW, **{**defaults, **kwargs})


def test_level_1_payload_carries_identity_and_quote_but_no_financial_summary():
    payload = build_coverage_research(RECORD, QUOTE, _coverage(), now=NOW)
    assert payload["identity"]["display_name"] == "Reliance Industries Limited"
    assert payload["quote"]["price"] == 2945.5
    assert payload["financial_summary"] is None
    assert payload["coverage"]["research_coverage_level"] == 1


def test_level_2_payload_includes_the_financial_summary_when_given():
    coverage = _coverage(has_financial_data=True)
    summary = {"revenue_cagr_3y": 0.12, "roce_3y": 0.18, "source_label": "Yahoo compatibility fallback"}
    payload = build_coverage_research(RECORD, QUOTE, coverage, financial_summary=summary, now=NOW)
    assert payload["coverage"]["research_coverage_level"] == 2
    assert payload["financial_summary"] == summary


def test_level_0_payload_omits_financial_summary_even_if_one_is_passed():
    coverage = assess_coverage(
        {**RECORD, "provider_symbol": None}, has_financial_data=False,
        has_model_score=False, has_full_research_payload=False, now=NOW,
    )
    payload = build_coverage_research(
        {**RECORD, "provider_symbol": None}, None, coverage,
        financial_summary={"revenue_cagr_3y": 0.1}, now=NOW,
    )
    assert payload["financial_summary"] is None


def test_refuses_a_level_3_assessment():
    coverage = _coverage(has_financial_data=True, has_model_score=True, has_full_research_payload=True)
    with pytest.raises(ValueError, match="Level 3"):
        build_coverage_research(RECORD, QUOTE, coverage, now=NOW)


def test_never_fabricates_score_or_rank_fields():
    payload = build_coverage_research(RECORD, QUOTE, _coverage(), now=NOW)
    assert "score" not in payload
    assert "rank" not in payload
    assert "strengths" not in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.research.coverage'`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/research/coverage.py
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
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research_coverage.py tests/test_research_lightweight.py -v`
Expected: all passed (5 new + 13 existing untouched)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/research/coverage.py tests/test_research_coverage.py
git commit -m "feat(coverage): add build_coverage_research for Levels 0-2"
```

---

### Task 4: Coverage-aware template — `company_coverage.html`

Renames `company_lightweight.html` and adds a coverage banner plus a
Level-2 financial-summary section. `render_lightweight_company_page` is
renamed to `render_coverage_company_page` in the same task since the
template rename and the Python function that selects it must move together.

**Files:**
- Modify (git mv + edit): `src/mbe/frontend/templates/company_lightweight.html` → `src/mbe/frontend/templates/company_coverage.html`
- Modify: `src/mbe/publish.py:463-480`
- Modify (rename file): `tests/test_publish_lightweight.py` → `tests/test_publish_coverage.py`

- [ ] **Step 1: Rename the template and test files**

```bash
git mv src/mbe/frontend/templates/company_lightweight.html src/mbe/frontend/templates/company_coverage.html
git mv tests/test_publish_lightweight.py tests/test_publish_coverage.py
```

- [ ] **Step 2: Write the failing tests (rewrite the moved test file)**

```python
# tests/test_publish_coverage.py — full replacement
"""render_coverage_company_page: the Jinja page for a search-universe
company at coverage Level 0, 1 or 2 (Phase 11 Milestone 2A)."""

from datetime import datetime, timezone

from mbe.coverage.policy import assess_coverage
from mbe.publish import render_coverage_company_page

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)

RECORD = {
    "instrument_id": "abc-123", "company_id": None,
    "display_name": "Reliance Industries Limited", "legal_name": "Reliance Industries Limited",
    "symbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018", "bse_code": None,
    "sector": None, "industry": None, "listing_status": "active", "is_sme": False,
    "market_cap_category": None, "aliases": [], "provider_symbol": "RELIANCE.NS",
    "result_type": "known", "research_available": False,
    "rank": None, "multibagger_score": None, "confidence": None, "risk_score": None,
    "report_url": "/company/abc-123.html",
}
QUOTE = {"price": 2945.5, "currency": "INR", "market_status": "open", "day_change_pct": 1.2,
         "week52_high": 3217.9, "week52_low": 2221.0}


def _coverage(record=RECORD, **kwargs):
    defaults = {"has_financial_data": False, "has_model_score": False, "has_full_research_payload": False}
    return assess_coverage(record, now=NOW, **{**defaults, **kwargs})


def test_level_1_page_shows_identity_badge_quote_and_coverage_label():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert "Reliance Industries Limited" in html
    assert "RELIANCE" in html
    assert "Level 1 — Market Coverage" in html
    assert "2,945.50" in html
    assert "3,217.90" in html and "2,221.00" in html


def test_level_0_page_shows_identity_only_label_when_no_quote_mapping():
    no_symbol = {**RECORD, "provider_symbol": None}
    html = render_coverage_company_page(no_symbol, None, _coverage(no_symbol))
    assert "Level 0 — Identity Coverage" in html


def test_page_never_shows_a_fabricated_score_rank_or_explanations():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert "Multibagger Score</strong>" not in html
    assert "Strengths</h2>" not in html
    assert "Risks &amp; limitations</h2>" not in html
    assert "Research checklist</h2>" not in html
    assert "Score &amp; rank history</h2>" not in html


def test_page_handles_a_missing_quote_honestly():
    html = render_coverage_company_page(RECORD, None, _coverage())
    assert "Limited research available" in html
    assert "Unavailable" in html


def test_page_is_canonical():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert '/company/abc-123.html' in html


def test_level_2_page_shows_the_financial_summary_section():
    coverage = _coverage(has_financial_data=True)
    summary = {"revenue_cagr_3y": 0.123, "roce_3y": 0.184, "source_label": "Yahoo compatibility fallback"}
    html = render_coverage_company_page(RECORD, QUOTE, coverage, financial_summary=summary)
    assert "Level 2 — Financial Coverage" in html
    assert "Financial summary" in html
    assert "12.3%" in html
    assert "18.4%" in html
    assert "Yahoo compatibility fallback" in html


def test_level_1_page_does_not_render_an_empty_financial_summary_section():
    html = render_coverage_company_page(RECORD, QUOTE, _coverage())
    assert "Financial summary" not in html


CROSS_LISTED_RECORD = {
    **RECORD,
    "bse_code": "500325", "primary_exchange": "NSE",
    "sector": "Energy", "sector_source": "exchange_master",
    "industry": "Refineries", "industry_source": "exchange_master",
    "listings": [
        {"exchange": "NSE", "symbol": "RELIANCE", "bse_code": None, "isin": "INE002A01018",
         "listing_status": "active", "is_primary": True, "is_sme": False},
        {"exchange": "BSE", "symbol": "RELIANCE", "bse_code": "500325", "isin": "INE002A01018",
         "listing_status": "active", "is_primary": False, "is_sme": False},
    ],
}


def test_page_shows_bse_code_and_cross_listing_detail():
    html = render_coverage_company_page(CROSS_LISTED_RECORD, QUOTE, _coverage(CROSS_LISTED_RECORD))
    assert "BSE 500325" in html
    assert "Listed on NSE and BSE" in html
    assert "exchange master" in html


def test_page_shows_a_prominent_banner_for_a_delisted_company():
    delisted = {**RECORD, "listing_status": "delisted"}
    html = render_coverage_company_page(delisted, None, _coverage(delisted))
    assert "Not currently active" in html
    assert "Delisted" in html
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_coverage.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_coverage_company_page'`

- [ ] **Step 4: Update the template**

Edit `src/mbe/frontend/templates/company_coverage.html`: add a coverage
badge next to the existing `ranking_universe_badge` span, and add a
financial-summary section (rendered only when `company.financial_summary`
is present) after the existing quote section.

```html
<!-- inside <div class="company-identity"> in company_coverage.html, immediately
     after the existing `<span class="badge badge-warning" ...>{{ company.ranking_universe_badge }}</span>` line -->
      <span class="badge badge-info" role="status">{{ company.coverage.coverage_label }}</span>
```

```html
<!-- new section, inserted directly after the existing "quote-detail" </section> in the research-main div -->

      {% if company.financial_summary %}
      <section class="panel research-section" aria-labelledby="financial-summary">
        <div class="section-heading"><div><p class="eyebrow">Accepted public fields only</p><h2 id="financial-summary">Financial summary</h2></div></div>
        <dl class="metric-strip">
          <div><dt>Revenue CAGR (3y)</dt><dd>{{ '%.1f%%'|format(company.financial_summary.revenue_cagr_3y * 100) if company.financial_summary.revenue_cagr_3y is not none else 'Unavailable' }}</dd></div>
          <div><dt>ROCE (3y average)</dt><dd>{{ '%.1f%%'|format(company.financial_summary.roce_3y * 100) if company.financial_summary.roce_3y is not none else 'Unavailable' }}</dd></div>
          <div><dt>Public source</dt><dd>{{ company.financial_summary.source_label or 'Unavailable' }}</dd></div>
        </dl>
      </section>
      {% endif %}
```

- [ ] **Step 5: Rename the render function in `publish.py`**

Edit `src/mbe/publish.py:463-480` — replace:

```python
def render_lightweight_company_page(record: dict, quote: dict | None) -> str:
    """Canonical page for a search-universe company outside the research
    universe — identity and a live quote only, rendered on demand by the
    api/company.py serverless fallback (never part of the weekly static
    build: see docs/HANDOVER.md "Search, research and ranking universes")."""
    payload = build_lightweight_research(record, quote)
    identity = payload["identity"]
    canonical_path = payload["canonical_url"]
    context = _base_context(
        title=f"{identity['display_name']} ({identity['symbol']}) | Multibagger Engine",
        description=(
            f"Company identity and live quote for {identity['display_name']}. "
            f"{payload['ranking_universe_badge']}"
        ),
        path=canonical_path, active_route="rankings", asset_prefix="/assets", root_href="/",
    )
    context["canonical_url"] = f"{PUBLIC_SITE_URL}{canonical_path}"
    return _ENV.get_template("company_lightweight.html").render(**context, company=payload)
```

with:

```python
def render_coverage_company_page(
    record: dict, quote: dict | None, coverage: CoverageAssessment,
    financial_summary: dict | None = None,
) -> str:
    """Canonical page for a search-universe company at coverage Level 0, 1
    or 2 — rendered on demand by the api/company.py serverless fallback
    (never part of the weekly static build: see docs/HANDOVER.md "Search,
    research and ranking universes" and docs/coverage-architecture.md)."""
    payload = build_coverage_research(record, quote, coverage, financial_summary)
    identity = payload["identity"]
    canonical_path = payload["canonical_url"]
    context = _base_context(
        title=f"{identity['display_name']} ({identity['symbol']}) | Multibagger Engine",
        description=(
            f"Company identity and live quote for {identity['display_name']}. "
            f"{coverage.source_quality_summary}"
        ),
        path=canonical_path, active_route="rankings", asset_prefix="/assets", root_href="/",
    )
    context["canonical_url"] = f"{PUBLIC_SITE_URL}{canonical_path}"
    return _ENV.get_template("company_coverage.html").render(**context, company=payload)
```

Update the imports near the top of `src/mbe/publish.py` (find the existing
`from mbe.research.lightweight import build_lightweight_research` line and
replace it):

```python
from mbe.coverage.domain import CoverageAssessment
from mbe.research.coverage import build_coverage_research
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_coverage.py tests/test_publish_lightweight.py -v 2>&1 | head -30`
Expected: `tests/test_publish_coverage.py` all pass; `test_publish_lightweight.py` reports "no tests ran" or file-not-found (it was renamed) — confirm with `git status` that only the rename + new content is staged, not a duplicate.

- [ ] **Step 7: Commit**

```bash
git add src/mbe/frontend/templates/company_coverage.html src/mbe/publish.py tests/test_publish_coverage.py
git commit -m "feat(coverage): rename lightweight page to coverage-aware company_coverage.html"
```

---

### Task 5: Level-3 page gets a coverage badge

Purely additive, hardcoded template text — Level-3 pages are always Level 3
by construction (they only exist because the instrument is in the research
universe), so this does not need a `CoverageAssessment` object threaded
through `CompanyResearch`, and does not touch the hash-gated `financials`/
`ranking` JSON subsets.

**Files:**
- Modify: `src/mbe/frontend/templates/company.html:7`
- Modify: `tests/test_publish.py:79-133` (`test_render_site_writes_index_reports_and_data`)

`company.html` is only rendered through `render_site()`'s canonical
`company/{instrument_id}.html` output in this codebase's existing tests —
there's no standalone `_render_company_page` unit-fixture test to extend.
`tests/test_publish.py:79-133` (`test_render_site_writes_index_reports_and_data`)
already builds `canonical_path = tmp_path / "company" / f"{data['top'][0]['instrument_id']}.html"`
and asserts `canonical_path.exists()` (line ~124) — this task extends that
same test to also read and assert on its content.

- [ ] **Step 1: Write the failing test**

Edit `tests/test_publish.py`, in `test_render_site_writes_index_reports_and_data`
directly after the existing line `assert canonical_path.exists()`:

```python
    canonical_html = canonical_path.read_text()
    assert "Level 3 — Full Research" in canonical_html
    assert "Included in the Small-Cap research model." in canonical_html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -k test_render_site_writes_index_reports_and_data -v`
Expected: FAIL — assertion error, badge text not found

- [ ] **Step 3: Add the badge to the template**

Edit `src/mbe/frontend/templates/company.html:7`, immediately after the
existing `<p class="eyebrow">...</p>` line:

```html
      <span class="badge badge-positive" role="status">Level 3 — Full Research</span>
      <p class="coverage-disclosure">Included in the Small-Cap research model.</p>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish.py -k test_render_site_writes_index_reports_and_data -v`
Expected: 1 passed

- [ ] **Step 5: Confirm the hash-gated JSON is unaffected**

Run: `uv run pytest tests/test_release_readiness.py -v`
Expected: passed — this test hashes `screener.json`/`research/*.json`
subsets, not `company.html`, so a template-only change cannot fail it; this
step is a sanity confirmation of that boundary before moving on.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/frontend/templates/company.html tests/test_publish.py
git commit -m "feat(coverage): show the Level 3 coverage badge on full research pages"
```

---

### Task 6: `SearchIndexRecord` gets additive coverage fields

**Files:**
- Modify: `src/mbe/search/domain.py:51-101`
- Modify: `src/mbe/search/catalog.py:145-158`
- Modify: `tests/test_search_catalog.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_search_catalog.py` uses module-level constants
`SEARCH_UNIVERSE_ROWS`, `RESEARCH_INSTRUMENTS`, `SCREENER_ROWS` and
`SUNPHARMA_ID` (not pytest fixtures) — RELIANCE is the unmodeled record
(has a `provider_symbols.yahoo` mapping, no research/score) and Sun Pharma
(`SUNPHARMA_ID`) is the modeled one. Append, reusing these exact names:

```python
def test_modeled_instrument_gets_level_3_coverage():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    sunpharma = next(r for r in index if r.instrument_id == SUNPHARMA_ID)
    assert sunpharma.research_coverage_level == 3
    assert sunpharma.coverage_label == "Level 3 — Full Research"
    assert sunpharma.research_eligible is True
    assert sunpharma.coverage_policy_version == "2026-08-03.11.2a.1"


def test_unmodeled_instrument_with_provider_symbol_gets_level_1_coverage():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    reliance = next(r for r in index if r.symbol == "RELIANCE")
    assert reliance.research_coverage_level == 1
    assert reliance.coverage_label == "Level 1 — Market Coverage"
    assert reliance.research_eligible is False
    assert "not_in_model_universe" in reliance.research_eligibility_reasons


def test_coverage_fields_are_never_missing_on_any_record():
    index = build_search_index(SEARCH_UNIVERSE_ROWS, RESEARCH_INSTRUMENTS, SCREENER_ROWS)
    for record in index:
        assert record.research_coverage_level in (0, 1, 2, 3)
        assert record.coverage_label
        assert record.research_sections_available
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_search_catalog.py -k coverage -v`
Expected: FAIL — `AttributeError: 'SearchIndexRecord' object has no attribute 'research_coverage_level'`

- [ ] **Step 3: Add the fields to `SearchIndexRecord`**

Edit `src/mbe/search/domain.py`, inside the `SearchIndexRecord` class,
directly after the existing `report_url: str` line (end of the class body):

```python
    # Phase 11 Milestone 2A — coverage level, additive. See
    # mbe.coverage.policy.assess_coverage, the single source of this data.
    research_coverage_level: int = 0
    coverage_label: str = ""
    coverage_level_version: str = "1.0"
    research_coverage_status: str = "active"
    research_eligible: bool = False
    research_eligibility_reasons: list[str] = []
    research_sections_available: list[str] = []
    research_sections_missing: list[str] = []
    coverage_policy_version: str = ""
```

- [ ] **Step 4: Compute coverage inside `build_search_index()`**

Edit `src/mbe/search/catalog.py`. Add the import near the top:

```python
from mbe.coverage.policy import assess_coverage
```

In the final reconciliation loop (the `for instrument_id, record in
records.items():` loop, right before its closing lines and the trailing
`return list(records.values())`), append:

```python
        has_model_score = record.rank is not None and record.multibagger_score is not None
        assessment = assess_coverage(
            record.model_dump(mode="json"),
            has_financial_data=record.research_available,
            has_model_score=has_model_score,
            has_full_research_payload=record.research_available,
        )
        record.research_coverage_level = assessment.research_coverage_level
        record.coverage_label = assessment.coverage_label
        record.coverage_level_version = assessment.coverage_level_version
        record.research_coverage_status = assessment.research_coverage_status
        record.research_eligible = assessment.research_eligible
        record.research_eligibility_reasons = assessment.research_eligibility_reasons
        record.research_sections_available = assessment.research_sections_available
        record.research_sections_missing = assessment.research_sections_missing
        record.coverage_policy_version = assessment.coverage_policy_version
```

(`has_financial_data=record.research_available` and
`has_full_research_payload=record.research_available` are currently
identical because `scripts/build_financials.py` is scoped to exactly the
research-universe instrument set — see the design doc's "Known limitation."
When a future milestone adds financial data outside that set, this line is
where it changes, not the policy.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_search_catalog.py -v`
Expected: all passed (existing tests + 3 new)

- [ ] **Step 6: Commit**

```bash
git add src/mbe/search/domain.py src/mbe/search/catalog.py tests/test_search_catalog.py
git commit -m "feat(coverage): compute coverage level for every search-index record"
```

---

### Task 7: `api/company.py` renders the correct coverage level

**Files:**
- Modify: `api/company.py`
- Modify: `tests/test_company_fn.py`

- [ ] **Step 1: Add the missing `financial_available` field**

Task 6 added `research_coverage_level`/`coverage_label`/etc. to
`SearchIndexRecord` but not a raw `financial_available` boolean — this
function needs it directly to avoid re-deriving financial availability from
scratch. Edit `src/mbe/search/domain.py`, add one more field next to
`coverage_policy_version` (added in Task 6):

```python
    financial_available: bool = False
```

Edit `src/mbe/search/catalog.py`, in the same coverage-assignment block
added in Task 6 (`for instrument_id, record in records.items(): ...
record.coverage_policy_version = assessment.coverage_policy_version`), add
one more line:

```python
        record.financial_available = assessment.financial_available
```

- [ ] **Step 2: Write the failing tests**

`tests/test_company_fn.py` defines `RELIANCE` (unmodeled, `provider_symbol:
"RELIANCE.NS"`, `instrument_id: "reliance-id"`), `MODELED`, `INDEX = [RELIANCE, MODELED]`,
and a `_chart_payload()` helper for the quote fetcher — reuse them exactly.
Append:

```python
def test_level_1_instrument_renders_market_coverage_label():
    status, html = company_fn.render_company(
        "reliance-id", index=INDEX, quote_fetcher=lambda s: _chart_payload(),
    )
    assert status == 200
    assert "Level 1 — Market Coverage" in html


def test_level_0_instrument_renders_identity_only_label_without_fetching_a_quote():
    calls = []
    no_symbol_index = [{**RELIANCE, "provider_symbol": None}, MODELED]
    status, html = company_fn.render_company(
        "reliance-id", index=no_symbol_index, quote_fetcher=lambda s: calls.append(s),
    )
    assert status == 200
    assert "Level 0 — Identity Coverage" in html
    assert calls == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_company_fn.py -k "level_1 or level_0" -v`
Expected: FAIL — `AssertionError` (old flat lightweight page has neither label)

- [ ] **Step 4: Update `api/company.py`**

Replace the imports and the body of `render_company`:

```python
from mbe.coverage.policy import assess_coverage
from mbe.data.market import QuoteRequest, YahooChartQuoteProvider, normalize_yahoo_chart  # noqa: E402
from mbe.publish import render_coverage_company_page  # noqa: E402
```

```python
def render_company(
    instrument_id: str, *, index: list[dict] | None = None, quote_fetcher=None,
) -> tuple[int, str]:
    """Returns (http_status, html). Pure function — directly unit-testable
    with an injected index and quote fetcher, same shape as api/analyze.py."""
    if not instrument_id or not _ID_RE.match(instrument_id):
        return 400, "<h1>Invalid instrument ID</h1>"
    records = index if index is not None else _load_index()
    record = next((row for row in records if row.get("instrument_id") == instrument_id), None)
    if record is None:
        return 404, "<h1>No matching listed company.</h1>"
    if record.get("research_available"):
        # Static routing should have served the real research page already;
        # reaching here means the static build is out of sync. Fail honestly
        # rather than silently downgrading a modeled company's page.
        _log("company_fallback_hit_modeled_instrument", instrument_id=instrument_id)
        return 404, "<h1>This company's research page is temporarily unavailable. Please retry.</h1>"
    # research_available is already False here, so this instrument is by
    # construction never Level 3 — has_model_score/has_full_research_payload
    # are always False for anything this function renders.
    coverage = assess_coverage(
        record, has_financial_data=bool(record.get("financial_available")),
        has_model_score=False, has_full_research_payload=False,
    )
    quote = None
    if coverage.quote_available:
        fetcher = quote_fetcher or YahooChartQuoteProvider()._fetch
        quote = _fetch_quote(record.get("provider_symbol"), fetcher)
    html = render_coverage_company_page(record, quote, coverage)
    return 200, html
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_company_fn.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add api/company.py src/mbe/search/domain.py src/mbe/search/catalog.py tests/test_company_fn.py
git commit -m "feat(coverage): api/company.py renders the coverage-aware page"
```

---

### Task 8: Static coverage artifact — `research-coverage.json`

**Files:**
- Modify: `src/mbe/builds/offline.py`
- Create: `scripts/build_coverage_artifact.py`
- Create: `tests/test_coverage_artifact.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage_artifact.py
import json

from mbe.builds.offline import build_coverage_only, build_search_only

MANIFEST = "builds/manifests/phase11-m1-frozen-inputs.json"


def test_coverage_artifact_is_deterministic_across_repeated_builds(tmp_path):
    from pathlib import Path
    out1, out2 = tmp_path / "b1", tmp_path / "b2"
    build_search_only(Path(MANIFEST), out1, write_manifest=False)
    build_search_only(Path(MANIFEST), out2, write_manifest=False)
    build_coverage_only(Path(MANIFEST), out1)
    build_coverage_only(Path(MANIFEST), out2)
    payload1 = json.loads((out1 / "data/research-coverage.json").read_text())
    payload2 = json.loads((out2 / "data/research-coverage.json").read_text())
    assert payload1 == payload2


def test_coverage_artifact_has_required_fields(tmp_path):
    from pathlib import Path
    out = tmp_path / "b"
    build_search_only(Path(MANIFEST), out, write_manifest=False)
    build_coverage_only(Path(MANIFEST), out)
    payload = json.loads((out / "data/research-coverage.json").read_text())
    assert payload["schema_version"] == "1.0"
    assert payload["coverage_policy_version"] == "2026-08-03.11.2a.1"
    assert payload["financial_build_id"] == "34baaa1c-e2f6-508b-b2f0-389669739b2a"
    assert set(payload["level_counts"].keys()) == {"0", "1", "2", "3"}
    assert payload["level_counts"]["3"] == 250
    assert payload["instrument_count"] == sum(payload["level_counts"].values())
    assert "generated_at" in payload
    assert "source_hashes" in payload


def test_coverage_artifact_contains_no_raw_provider_payloads(tmp_path):
    from pathlib import Path
    out = tmp_path / "b"
    build_search_only(Path(MANIFEST), out, write_manifest=False)
    build_coverage_only(Path(MANIFEST), out)
    raw = (out / "data/research-coverage.json").read_text()
    assert "yahoo" not in raw.lower()
    assert "/Users/" not in raw and "/home/" not in raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage_artifact.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_coverage_only'`

- [ ] **Step 3: Implement `build_coverage_only()`**

Edit `src/mbe/builds/offline.py`. Add after `build_search_only` (which ends
around line 177):

```python
def build_coverage_only(
    manifest_path: Path, out: Path, *, write_manifest: bool = False,
) -> dict:
    """Aggregates the per-record coverage fields already written into
    api/v1/search-index.json (by build_search_only) into a small reporting
    artifact. Must run after build_search_only against the same `out` — it
    does not recompute assess_coverage itself, only tallies what's already
    there, so it can never disagree with the per-instrument data."""
    manifest, root = load_manifest(manifest_path)
    controlled_time = _controlled_time(manifest)
    search_path = out / "api/v1/search-index.json"
    rows = json.loads(search_path.read_text())["data"]
    level_counts = {"0": 0, "1": 0, "2": 0, "3": 0}
    reason_counts: dict[str, int] = {}
    for row in rows:
        level_counts[str(row["research_coverage_level"])] += 1
        for reason in row.get("research_eligibility_reasons", []):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    payload = {
        "schema_version": "1.0",
        "coverage_policy_version": rows[0]["coverage_policy_version"] if rows else "",
        "search_build_id": sha256_file(search_path),
        "financial_build_id": manifest.financial_build_id,
        "model_build_ids": [v for v in manifest.model_build_ids.values() if v],
        "instrument_count": len(rows),
        "level_counts": level_counts,
        "coverage_reasons": reason_counts,
        "generated_at": controlled_time.isoformat(),
        "source_hashes": {
            "search_index": sha256_file(search_path),
            "financial_build": manifest.financial_build_id,
            "model_build": next(iter(manifest.model_build_ids.values()), None),
        },
    }
    target = out / "data/research-coverage.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=1, sort_keys=True))
    return payload
```

- [ ] **Step 4: Wire the new script**

```python
# scripts/build_coverage_artifact.py
#!/usr/bin/env python3
"""Regenerate the static coverage-level reporting artifact. Must run after
build_search_assets.py against the same --out directory."""

import argparse
import json
from pathlib import Path

from mbe.builds.offline import build_coverage_only


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("builds/manifests/phase11-m1-frozen-inputs.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("site"))
    args = parser.parse_args()
    print(json.dumps(build_coverage_only(args.manifest, args.out), indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_coverage_artifact.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/mbe/builds/offline.py scripts/build_coverage_artifact.py tests/test_coverage_artifact.py
git commit -m "feat(coverage): add deterministic research-coverage.json build stage"
```

---

### Task 9: API — `/coverage` route and extended `/summary`

**Files:**
- Modify: `src/mbe/api/schemas.py`
- Modify: `src/mbe/api/app.py`
- Modify: `tests/test_api_v1_search.py` (has the DB-backed `api` fixture and the existing `/summary` tests — see its module docstring)
- Modify: `tests/test_api_v1.py` (has `test_methodology_is_machine_readable_and_database_absence_is_safe`, the existing DB-absent 503 pattern via `TestClient(create_app())`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_v1_search.py`, reusing its existing `api` fixture
(defined at line 47 — `ids["GOOD.NS"]` is modeled/scored,
`ids["RELIANCE.NS"]` is imported but unmodeled, exactly matching the
existing `/summary` tests right above):

```python
def test_coverage_route_returns_level_3_for_a_modeled_instrument(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['GOOD.NS']}/coverage")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_coverage_level"] == 3
    assert data["research_eligible"] is True
    assert "score" not in data


def test_coverage_route_returns_level_1_for_an_unmodeled_instrument(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['RELIANCE.NS']}/coverage")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_coverage_level"] == 1
    assert data["research_eligible"] is False
    assert "not_in_model_universe" in data["research_eligibility_reasons"]


def test_coverage_route_unknown_instrument_is_404(api):
    client, _, _ = api
    response = client.get("/api/v1/company/not-a-real-id/coverage")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "company_not_found"


def test_summary_route_gains_additive_coverage_fields(api):
    client, ids, _ = api
    response = client.get(f"/api/v1/company/{ids['RELIANCE.NS']}/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_coverage_level"] == 1
    assert data["coverage_label"] == "Level 1 — Market Coverage"
    assert data["research_eligible"] is False
```

Append to `tests/test_api_v1.py`, next to the existing
`test_methodology_is_machine_readable_and_database_absence_is_safe`:

```python
def test_coverage_route_returns_bounded_503_without_configured_database():
    client = TestClient(create_app())
    response = client.get("/api/v1/company/some-id/coverage")
    assert response.status_code == 503
    assert response.json()["errors"][0]["code"] == "database_not_configured"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_v1_search.py tests/test_api_v1.py -k coverage -v`
Expected: FAIL — 404 (route doesn't exist yet) / `KeyError` for the new fields

- [ ] **Step 3: Add `CoverageData` schema**

Edit `src/mbe/api/schemas.py`, add near `CompanySummaryData`:

```python
class CoverageData(BaseModel):
    instrument_id: str
    company_id: str | None = None
    research_coverage_level: int
    coverage_label: str
    coverage_level_version: str
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
```

Extend `CompanySummaryData` (add these fields at the end of the existing
class body in `src/mbe/api/schemas.py:146-171`):

```python
    research_coverage_level: int = 0
    coverage_label: str = ""
    research_eligible: bool = False
    research_sections_available: list[str] = Field(default_factory=list)
    research_sections_missing: list[str] = Field(default_factory=list)
    coverage_policy_version: str = ""
```

- [ ] **Step 4: Add the route and extend `company_summary_route`**

Edit `src/mbe/api/app.py`. Add the import:

```python
from mbe.coverage.policy import assess_coverage
from mbe.db.models import FinancialMetricSnapshotRow
from mbe.financials.repository import latest_build as latest_financial_build
```

Add a small shared helper near `_current_scores` (`src/mbe/api/app.py:289`):

```python
    def _has_financial_data(session: Session, instrument_id: str) -> bool:
        build = latest_financial_build(session)
        if not build:
            return False
        count = session.scalar(select(func.count()).select_from(FinancialMetricSnapshotRow).where(
            FinancialMetricSnapshotRow.financial_dataset_build_id == build.financial_dataset_build_id,
            FinancialMetricSnapshotRow.instrument_id == instrument_id,
        ))
        return bool(count)

    def _assess(session: Session, instrument_id: str, row: dict, score) -> CoverageAssessment:
        return assess_coverage(
            {
                "instrument_id": instrument_id, "company_id": row.get("company_id"),
                "isin": row.get("isin"), "bse_code": row.get("bse_code"),
                "legal_name": row.get("legal_name"), "listing_status": row.get("listing_status"),
                "is_sme": row.get("is_sme"),
                "provider_symbol": next(
                    (m["provider_symbol"] for m in row.get("provider_mappings", []) if m["provider"] == "yahoo"),
                    None,
                ),
            },
            has_financial_data=_has_financial_data(session, instrument_id),
            has_model_score=score is not None,
            has_full_research_payload=score is not None,
        )
```

Add the import for `CoverageAssessment` alongside the other coverage import:

```python
from mbe.coverage.domain import CoverageAssessment
```

Add the new route directly after `company_summary_route`
(`src/mbe/api/app.py`, after its closing `))` around line 470):

```python
    @app.get("/api/v1/company/{instrument_id}/coverage", response_model=Envelope[CoverageData])
    def company_coverage_route(
        request: Request, instrument_id: str, session: Session = Depends(get_session),
    ):
        """Always-available coverage assessment — the same policy call the
        static search index and api/company.py use. See
        docs/coverage-architecture.md."""
        row = PlatformRepository(session).instrument(instrument_id)
        if not row:
            raise HTTPException(404, {"code": "company_not_found", "message": "No matching listed company."})
        score = _current_scores(session, [instrument_id]).get(instrument_id)
        assessment = _assess(session, instrument_id, row, score)
        return _envelope(request, CoverageData(**assessment.model_dump(mode="json")))
```

Extend `company_summary_route`'s return (`src/mbe/api/app.py:450-470`) by
computing the same assessment and spreading its fields into the response:

```python
        assessment = _assess(session, instrument_id, row, score)
        return _envelope(request, CompanySummaryData(
            instrument_id=instrument_id, display_name=row.get("display_name"),
            legal_name=row.get("legal_name"), symbol=row.get("symbol"), exchange=row.get("exchange"),
            primary_exchange=row.get("exchange"), isin=row.get("isin"), bse_code=bse_code,
            sector=row.get("sector"),
            sector_source="canonical_platform" if row.get("sector") else None,
            industry=row.get("industry"),
            industry_source="canonical_platform" if row.get("industry") else None,
            listing_status=row.get("listing_status"), is_sme=row.get("is_sme"),
            listings=listings,
            result_type="modeled" if research_available else "known",
            research_available=research_available,
            rank=score.rank if score else None,
            multibagger_score=float(score.multibagger_score) if score else None,
            confidence=float(score.confidence) if score else None,
            risk_score=float(score.risk_score) if score else None,
            report_url=canonical_company_url(instrument_id),
            quote=quote,
            ranking_universe_badge=None if research_available else RANKING_UNIVERSE_BADGE,
            scoring_disclosure=None if research_available else SCORING_DISCLOSURE,
            research_coverage_level=assessment.research_coverage_level,
            coverage_label=assessment.coverage_label,
            research_eligible=assessment.research_eligible,
            research_sections_available=assessment.research_sections_available,
            research_sections_missing=assessment.research_sections_missing,
            coverage_policy_version=assessment.coverage_policy_version,
        ))
```

(This replaces only the `return _envelope(...)` statement at the end of the
existing function — everything above it in `company_summary_route` is
unchanged.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_v1_search.py tests/test_api_v1.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/mbe/api/schemas.py src/mbe/api/app.py tests/test_api_v1_search.py tests/test_api_v1.py
git commit -m "feat(coverage): add GET /api/v1/company/{id}/coverage and extend /summary"
```

---

### Task 10: Bundle `search-index.json` into the `api/v1.py` function

**Files:**
- Modify: `vercel.json`

- [ ] **Step 1: Edit `vercel.json`**

Change the `api/v1.py` function's `includeFiles`:

```json
    "api/v1.py": { "includeFiles": "{site/data.json,site/api/v1/search-index.json,src/mbe/**,migrations/**,alembic.ini}" },
```

- [ ] **Step 2: Verify JSON validity**

Run: `python3 -c "import json; json.load(open('vercel.json'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add vercel.json
git commit -m "chore(coverage): bundle search-index.json into the api/v1 function"
```

---

### Task 11: Frontend search coverage badges

`researchBadge(item)` (`src/mbe/frontend/assets/app.js:505-511`) is a
closure private to `initSearch()`, not exported — it can't be unit-tested
directly. Following this file's own existing convention (pure logic
functions are extracted into the exported `pure` object at line 435 —
`normalizeText`, `staticSearch`, etc. — and unit-tested via
`require("../../src/mbe/frontend/assets/app.js")` in `app.test.js`), this
task extracts the level→label mapping into a new pure, exported
`researchBadgeText(level)` function and has `researchBadge` call it. It
also extends the existing `searchIndex` fixture/test (`tests/frontend/app.test.js:43-56,99-106`)
that already asserts `staticSearch` carries `result_type`/`research_available`
through, to also assert the two new fields pass through unchanged.

**Files:**
- Modify: `src/mbe/frontend/assets/app.js`
- Modify: `tests/frontend/app.test.js`

- [ ] **Step 1: Write the failing tests**

Edit `tests/frontend/app.test.js`: extend the `searchIndex` fixture
(lines 43-56) with the two new fields on both records, and extend the
existing test at line 99, then add a new test for the pure function:

```js
// tests/frontend/app.test.js — replace the searchIndex fixture (lines 43-56) with:
const searchIndex = [
  {
    instrument_id: "id-modeled", display_name: "Modeled Motors Limited", symbol: "MODELED",
    exchange: "NSE", isin: "INE000C01019", listing_status: "active", aliases: [],
    result_type: "modeled", research_available: true, rank: 4, multibagger_score: 71.2,
    confidence: 0.8, risk_score: 20, report_url: "/company/id-modeled.html",
    research_coverage_level: 3, coverage_label: "Level 3 — Full Research",
  },
  {
    instrument_id: "id-unmodeled", display_name: "Unmodeled Industries Limited", symbol: "UNMODELED",
    exchange: "NSE", isin: "INE000D01010", listing_status: "active", aliases: [],
    result_type: "known", research_available: false, rank: null, multibagger_score: null,
    confidence: null, risk_score: null, report_url: "/company/id-unmodeled.html",
    research_coverage_level: 1, coverage_label: "Level 1 — Market Coverage",
  },
];
```

```js
// tests/frontend/app.test.js — replace the body of the existing test at line 99 with:
test("static search carries research/ranking status through so the UI can badge results honestly", () => {
  const modeled = app.staticSearch(searchIndex, "Modeled Motors")[0];
  assert.equal(modeled.result_type, "modeled");
  assert.equal(modeled.research_available, true);
  assert.equal(modeled.rank, 4);
  assert.equal(modeled.multibagger_score, 71.2);
  assert.equal(modeled.report_url, "/company/id-modeled.html");
  assert.equal(modeled.research_coverage_level, 3);
  assert.equal(modeled.coverage_label, "Level 3 — Full Research");

  const unmodeled = app.staticSearch(searchIndex, "Unmodeled Industries")[0];
  assert.equal(unmodeled.result_type, "known");
  assert.equal(unmodeled.research_available, false);
  assert.equal(unmodeled.rank, null);
  assert.equal(unmodeled.multibagger_score, null);
  assert.equal(unmodeled.report_url, "/company/id-unmodeled.html");
  assert.equal(unmodeled.research_coverage_level, 1);
  assert.equal(unmodeled.coverage_label, "Level 1 — Market Coverage");
});

test("researchBadgeText maps each coverage level to its public label", () => {
  assert.equal(app.researchBadgeText(3), "Full Research");
  assert.equal(app.researchBadgeText(2), "Financial Coverage");
  assert.equal(app.researchBadgeText(1), "Market Coverage");
  assert.equal(app.researchBadgeText(0), "Identity Only");
  assert.equal(app.researchBadgeText(undefined), "Identity Only");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- tests/frontend/app.test.js 2>&1 | tail -30`
Expected: FAIL — `research_coverage_level`/`coverage_label` are `undefined`
(not yet threaded through `staticSearch`), and `app.researchBadgeText` is
`undefined` (not yet exported).

- [ ] **Step 3: Thread the fields through `staticSearch` and export `researchBadgeText`**

Edit `src/mbe/frontend/assets/app.js`. In the `matches.push({...})` object
construction inside `staticSearch` (around line 193-227), add two lines
next to the existing `research_available: Boolean(item.research_available),`:

```js
        research_coverage_level: item.research_coverage_level == null ? 0 : Number(item.research_coverage_level),
        coverage_label: item.coverage_label || null,
```

Add the pure function near the top-level function definitions (anywhere
before the `pure` object literal, matching the style of the other small
pure helpers in this file):

```js
  function researchBadgeText(level) {
    const labels = { 3: "Full Research", 2: "Financial Coverage", 1: "Market Coverage", 0: "Identity Only" };
    const key = Number.isInteger(level) ? level : 0;
    return labels[key] || "Identity Only";
  }
```

Add it to the exported `pure` object (`src/mbe/frontend/assets/app.js:435`):

```js
  const pure = { normalizeText, similarity, staticSearch, parseExchangeHint, parseRankingState, stateToSearch, rankingRow, normalizeRankingEnvelope, stableFilterSort, summaryFor, csvFor, buildCompatible, apiQuery, reportDestination, researchBadgeText };
```

Replace `researchBadge` (`src/mbe/frontend/assets/app.js:505-511`) to use it:

```js
    const researchBadge = item => {
      const level = item.research_coverage_level == null ? 0 : Number(item.research_coverage_level);
      if (level === 3) {
        const bits = [Number.isFinite(item.rank) && `Rank #${item.rank}`, Number.isFinite(item.multibagger_score) && `Score ${Math.round(item.multibagger_score)}`].filter(Boolean);
        return create("span", "badge badge-positive", bits.length ? bits.join(" · ") : researchBadgeText(level));
      }
      return create("span", `badge ${level === 2 ? "badge-positive" : "badge-info"}`, researchBadgeText(level));
    };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- tests/frontend/app.test.js 2>&1 | tail -30`
Expected: all passed

- [ ] **Step 5: Lint and typecheck**

Run: `npm run lint && npm run typecheck`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/mbe/frontend/assets/app.js tests/frontend/app.test.js
git commit -m "feat(coverage): show coverage-level badges in search results"
```

---

### Task 12: Hash-preservation and canonical-routing guard tests

**Files:**
- Modify: `tests/test_deterministic_build.py`
- Modify: `tests/test_release_readiness.py`
- Modify: `tests/test_company_fn.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_deterministic_build.py` (match its existing
`public_value_hashes`/`VALUE_FIXTURE` import pattern — read the top of the
file first):

```python
def test_coverage_artifact_does_not_change_the_preserved_public_hashes(tmp_path):
    """The score/financial hash gates only cover screener.json and
    research/*.json — adding research-coverage.json must not perturb them."""
    from mbe.builds.offline import build_coverage_only, render_site_from_manifest
    from scripts.verify_release import public_value_hashes
    out = tmp_path / "site"
    render_site_from_manifest(FROZEN_MANIFEST, out)  # use this file's existing manifest path constant
    before = public_value_hashes(out)
    build_coverage_only(FROZEN_MANIFEST, out)
    after = public_value_hashes(out)
    assert before == after == VALUE_FIXTURE
```

(`FROZEN_MANIFEST`/`VALUE_FIXTURE` should reference whatever names this
file's existing determinism tests already use — e.g.
`Path("builds/manifests/phase11-m1-frozen-inputs.json")` and the loaded
`tests/fixtures/phase8-public-value-hashes.json` — check the top of the
file with `grep -n "^FROZEN\|^VALUE_FIXTURE\|public_value_hashes" tests/test_deterministic_build.py`.)

Append to `tests/test_company_fn.py` — a canonical-routing parity check
across all four levels using a small fixture index that includes one
instrument at each level:

```python
def test_every_coverage_level_resolves_without_a_404():
    index = [
        {**RECORD, "instrument_id": "id-l0", "provider_symbol": None, "research_available": False},
        {**RECORD, "instrument_id": "id-l1", "provider_symbol": "L1.NS", "research_available": False},
    ]
    for row in index:
        status, _html = render_company(row["instrument_id"], index=index, quote_fetcher=lambda s: None)
        assert status == 200
    # Level 3 is verified separately: it is served as a static file by
    # Vercel before this function ever runs (see api/company.py's docstring
    # and mbe.publish.render_site), so a 200-from-static-file check belongs
    # with the existing render_site tests, not here.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deterministic_build.py tests/test_company_fn.py -k "coverage or every_coverage_level" -v`
Expected: FAIL until Task 8/Task 7 code exists — if those tasks are already done by this point in the plan, this should mostly pass already; treat any failure as a real regression to fix, not an expected red step.

- [ ] **Step 3: Fix any regression found**

If `before != after` in the hash test, the bug is in `build_coverage_only`
writing under `out/api/v1/` or `out/data/` incorrectly, or in a stray write
touching `out/api/v1/research/` or `out/api/v1/screener.json` — trace with
`git diff` on the two builds' output trees inside the test (temporarily
`print(out)` and inspect) rather than guessing.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deterministic_build.py tests/test_company_fn.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_deterministic_build.py tests/test_company_fn.py
git commit -m "test(coverage): guard score/financial hash preservation and routing parity"
```

---

### Task 13: Documentation

**Files:**
- Create: `docs/coverage-architecture.md`
- Modify: `docs/HANDOVER.md`

- [ ] **Step 1: Write `docs/coverage-architecture.md`**

Follow the structure/tone of `docs/company-research-architecture.md` and
`docs/search-architecture.md` (both already read during planning). Cover,
in this order: route and compatibility decision (reuse of the existing
static/serverless split — cite `docs/company-research-architecture.md`'s
"Route and compatibility decision" section rather than duplicating it);
the four coverage levels and their section tables; the policy module and
version `2026-08-03.11.2a.1`; the static-vs-serverless decision with the
actual measured numbers from Task 14; the `/coverage` API contract; the
`research-coverage.json` schema; and the known Level-2-has-zero-members
limitation with the Milestone 2B recommendation — copy this content
directly from `docs/superpowers/specs/2026-08-03-universal-company-report-coverage-design.md`'s
matching sections, adapted to include the real measured numbers once
Task 14 has them.

- [ ] **Step 2: Update `docs/HANDOVER.md`**

Add a new phase-ledger entry following the existing style (see the "Phase
11 Milestone 1" entry for the exact format), placed after that entry:
"Phase 11 Milestone 2A — universal company report coverage architecture."
Summarize: the four levels, the policy version, that the 250 pages are
unchanged, the static/serverless decision, the new artifact/API/search
fields, and the Level 2 known limitation. Also add one sentence to the
existing "Search, research and ranking universes" section (around line 159)
cross-referencing the new formal coverage levels.

- [ ] **Step 3: Commit**

```bash
git add docs/coverage-architecture.md docs/HANDOVER.md
git commit -m "docs(coverage): document the universal company report coverage architecture"
```

---

### Task 14: Measurement — static-size, build-duration, route counts

**Files:**
- No source changes — this task produces the numbers Task 13 and the final
  completion report need.

- [ ] **Step 1: Run the full offline build and capture timing**

```bash
time uv run python scripts/build_model.py --help >/dev/null  # confirm CLI still resolves before the real run
time uv run scripts/render_all_stages.sh 2>&1 | tee /tmp/build-log.txt || true
```

(If there is no single `render_all_stages.sh`, run the documented sequence
from `docs/phase11-m1-deterministic-build.md` — `build_model.py` →
`build_financials.py` → `build_research_payloads.py` → `build_site.py` →
`build_search_assets.py` → `scripts/build_coverage_artifact.py` — each
timed with `time`.)

- [ ] **Step 2: Measure output size and record counts**

```bash
du -sh site/
du -sh site/company/
python3 -c "
import json
d = json.load(open('site/api/v1/search-index.json'))
from collections import Counter
c = Counter(r['research_coverage_level'] for r in d['data'])
print('level counts:', dict(c))
print('total:', len(d['data']))
"
du -h site/data/research-coverage.json
python3 -c "
import json
sizes = [len(json.dumps(r)) for r in json.load(open('site/api/v1/search-index.json'))['data']]
print('avg record bytes:', sum(sizes)/len(sizes), 'max:', max(sizes))
"
```

- [ ] **Step 3: Record the numbers**

Write the measured values (build duration, `site/` total size, per-level
counts, `research-coverage.json` size, average/max search-index record
size) into `docs/coverage-architecture.md`'s "static coverage" section
(Task 13) and keep them handy for the final completion report — do not
guess or estimate any of these numbers in the report; use exactly what was
measured here.

- [ ] **Step 4: Commit**

```bash
git add docs/coverage-architecture.md
git commit -m "docs(coverage): record measured build-size and duration numbers"
```

---

### Task 15: Full verification pass

**Files:**
- No source changes — verification only. Fix forward if anything fails; do
  not skip or weaken a check to make it pass.

- [ ] **Step 1: Full Python test suite**

Run: `uv run pytest -v 2>&1 | tail -60`
Expected: at least 659 + (count added across Tasks 1-2-3-4-5-6-7-8-9-12)
passed, 0 failed.

- [ ] **Step 2: Full frontend suite**

Run: `npm run check`
Expected: lint, typecheck and `node --test` (at least 35 + 4 from Task 11)
all pass.

- [ ] **Step 3: Release verifier**

Run: `uv run python scripts/verify_release.py site . tests/fixtures/phase8-public-value-hashes.json`
Expected: no errors — confirms `scores_sha256`/`financials_sha256` are
still `12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19` /
`3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`.

- [ ] **Step 4: Membership hash**

Run: `sha256sum universes/nifty-smallcap250.json`
Expected: `531631685ed9785daf390f3799144277ef3e31287cd6e6f20d1d9ad706752af5` (unchanged file, so this is a no-op confirmation).

- [ ] **Step 5: Deterministic-build verifier**

Run: `uv run python scripts/verify_deterministic_build.py --manifest builds/manifests/phase11-m1-frozen-inputs.json 2>&1 | tail -40`
Expected: reports byte-identical repeated builds, no network attempted.

- [ ] **Step 6: Python compilation**

Run: `uv run python -m py_compile $(git diff --name-only main... -- '*.py') 2>&1 || uv run python -m compileall src/mbe scripts api -q`
Expected: no syntax errors.

- [ ] **Step 7: `git diff --check`**

Run: `git diff --check main...HEAD`
Expected: no whitespace errors.

- [ ] **Step 8: If everything passes, this milestone is done — do not push**

No commit needed for this task (verification only). Report the completion
summary per the milestone's "Definition of done" list, using the exact
counts/hashes observed in Steps 1-5 and the measurements from Task 14 — not
estimates.
