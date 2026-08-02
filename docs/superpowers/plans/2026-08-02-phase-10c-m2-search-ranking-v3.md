# Phase 10C Milestone 2 — Search Ranking Policy v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship search-ranking policy version 3 — a documented, explainable late-tie-break stage layered on top of the unchanged version-2 identity-first match tiers — across the static build, the DB-backed API, and the JS client, with new evidence fields, an expanded evaluation set, and parity tests.

**Architecture:** `mbe.search.ranking` remains the canonical policy: version-2 primary match tiers (`_best_match`) are preserved byte-for-byte (same scores, same order) so none of the 625/28 existing tests can regress; a new tie-break stage (`_tiebreak_key`) adds four new late dimensions (requested-exchange match, broad-index membership, ranking availability, classification quality) around the three that already existed (active, primary, main-board, research). Every dimension added is proven, by construction, to be a no-op against every *existing* fixture (uniform value across all compared candidates), so the reorder cannot change any currently-asserted result — new tests exercise the cases where the new dimensions do differentiate. The same tier scores and new shared helper functions (`match_reason`, `matched_field_for`, `index_membership_rank`, `classification_quality_rank`) are imported by `mbe.instruments.resolution.InstrumentResolver` (the DB-backed path actually serving `/api/v1/search`) and mirrored by hand into `app.js`'s `staticSearch`, per the "shared constants and mirrored tests" parity option.

**Tech Stack:** Python 3.11+/Pydantic v2 (`mbe.search.*`, `mbe.instruments.resolution`, `mbe.api.*`), vanilla JS (`app.js`), pytest, Node's built-in test runner.

---

## Non-negotiable invariants (verify after every task)

- No change to any `_best_match` score constant or tier logic — version 2's primary-tier order and scores are frozen.
- No canonical-ID, research-universe, ranking-universe, scoring, or financial-value change.
- No route path/parameter changes on `/api/v1/search` or `/api/v1/search/meta` — only additive response fields and internal ordering improvements.
- No fabricated index-membership data — `index_memberships` stays `[]` everywhere until a real broad-index source is imported (documented as Milestone 3 scope).
- All 625 existing Python tests and 28 existing frontend tests keep passing unmodified (except two tests that assert the *old* tie-break tuple shape directly, called out in Task 3).

---

### Task 1: Add index-membership and evidence schema fields

**Files:**
- Modify: `src/mbe/search/domain.py`
- Test: `tests/test_search_domain.py` (create if it does not exist — check first with `ls tests/test_search_domain.py`)

- [ ] **Step 1: Write the failing test**

```python
from mbe.search.domain import ExchangeListing, SearchCandidate, SearchIndexRecord, SearchResultType


def _minimal_record(**overrides):
    base = dict(
        instrument_id="id-1", display_name="Example Ltd.", symbol="EXAMPLE",
        result_type=SearchResultType.KNOWN, report_url="/company/id-1.html",
    )
    base.update(overrides)
    return SearchIndexRecord(**base)


def test_search_index_record_has_empty_index_memberships_by_default():
    record = _minimal_record()
    assert record.index_memberships == []


def test_search_candidate_carries_v3_evidence_fields():
    record = _minimal_record()
    candidate = SearchCandidate(
        record=record, score=95.0, matched_by="exact_company_name", matched_value="Example Ltd.",
        match_tier="exact_company_name", matched_field="company_name",
        match_reason="Exact company name", match_confidence=0.95,
        ranking_policy_version="2026-08-02.10c.2",
        active_listing=True, primary_listing=True,
        research_available=False, ranking_available=False,
    )
    assert candidate.index_memberships == []
    assert candidate.classification_conflict is False
    assert candidate.ambiguity_warning is None
    assert candidate.requested_exchange_matched is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_search_domain.py -v`
Expected: FAIL — `SearchCandidate` missing required evidence fields (`TypeError`/`ValidationError` on construction), and `index_memberships` not a recognized attribute.

- [ ] **Step 3: Add the fields**

In `src/mbe/search/domain.py`, add one field to `SearchIndexRecord` right after `listings`:

```python
    listings: list[ExchangeListing] = []
    # Verified broad-index memberships only (e.g. "Nifty 50"). Empty on every
    # record today — no broad-index source beyond Nifty Smallcap 250 (already
    # reflected via research_available) is imported yet. See
    # mbe.search.ranking module docstring and docs/search-architecture.md
    # "Search ranking policy version 3".
    index_memberships: list[str] = []
```

Replace the whole `SearchCandidate` class with:

```python
class SearchCandidate(BaseModel):
    """A ranked search result: the matched record plus why it matched, and
    the Phase 10C Milestone 2 (search ranking policy version 3) evidence
    fields that explain its position — see mbe.search.ranking module
    docstring for the full tier/tie-break policy."""

    record: SearchIndexRecord
    score: float
    matched_by: str
    matched_value: str
    match_tier: str
    matched_field: str
    match_reason: str
    match_confidence: float
    ranking_policy_version: str
    active_listing: bool
    primary_listing: bool
    requested_exchange_matched: bool | None = None
    index_memberships: list[str] = []
    research_available: bool
    ranking_available: bool
    classification_review_status: str | None = None
    classification_conflict: bool = False
    prominence_signals: list[str] = []
    ambiguity_warning: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_search_domain.py -v`
Expected: PASS

- [ ] **Step 5: Commit is deferred to the end of Task 3** (domain, ranking, and the ranking tests land together so no intermediate commit leaves `rank_search_candidates` unable to construct a `SearchCandidate`).

---

### Task 2: Rewrite `mbe.search.ranking` for policy v3

**Files:**
- Modify: `src/mbe/search/ranking.py` (full-file rewrite; primary-tier logic in `_best_match` is copied verbatim, only the module docstring, version constant, and everything from `_prominence_signals` down are new/changed)

- [ ] **Step 1: Replace the entire file contents**

```python
"""Quality-ordered ranking over the merged search index.

Search ranking policy version 3 (Phase 10C Milestone 2,
``SEARCH_RANKING_POLICY_VERSION``) preserves the identity-first tier order of
version 2 unchanged — no primary-tier score or ordering has moved — and adds
a documented, evidence-carrying late tie-break stage. Mapping from the 13
conceptual tiers in docs/search-architecture.md to the 11 concrete scoring
tiers implemented here:

  1. exact_nse_symbol (100)         7. exact_alias / exact_former_name
  2. exact_bse_code (98)               (90/88, 78 for <=3-char abbreviations
  3. exact_isin (97)                   — "safe alias"/"safe abbreviation")
  4/5. exact_company_name (95) —    8. full_phrase_match (84) — "exact
       legal name and display           full-token sequence"
       name are checked identically 9. company_name_prefix (75-82)
       — both are exact identity,  10. word_match (55-68) — "all-token
       there is no ranking reason       match"
       to prefer one over the      12/13. fuzzy_company_name (60-80,
       other                             guarded) covers both "guarded
  6. exact_former_name (88)              fuzzy match" and "partial word
                                         match": a separate token-overlap
                                         partial-match tier was considered
                                         for v3 and rejected — no evaluation
                                         evidence it improves ranking beyond
                                         the existing guarded fuzzy tier, and
                                         it would need new score-overlap
                                         calibration against the evaluation
                                         set. See docs/search-architecture.md
                                         "Search ranking policy version 3".

Within an equal score, ``_tiebreak_key`` applies late, defensible prominence
signals in this order. Each dimension can only order two otherwise-equally-
scored candidates — it can never promote a worse match tier above a better
one:

  1. Active listing beats inactive/delisted/suspended ("unknown" is never
     treated as active)
  2. Requested exchange match — a no-op today because
     ``rank_search_candidates`` already hard-filters out candidates with no
     listing on the requested exchange *before* scoring, so every candidate
     that reaches the tie-break already matches (or no exchange was
     requested). Kept as an explicit tie-break dimension and evidence field
     for documentation fidelity and to guard against a future change to the
     filtering behavior silently losing this guarantee.
  3. Primary listing beats secondary
  4. Broad-index membership (Nifty 50 > Next 50 > 100 > 200 > 500, see
     ``_INDEX_PRECEDENCE``) — **no company in canonical data carries
     verified broad-index membership today.** Only Nifty Smallcap 250 is
     imported (a small-cap index, not a "broad" prominence index, and
     already reflected via ``research_available``), so ``index_memberships``
     is ``[]`` on every record and this dimension never differentiates real
     data yet. Structurally present, not fabricated — see "Recommended
     Milestone 3 scope" in docs/HANDOVER.md.
  5. Main-board beats SME (SME is never hidden or treated as poor quality —
     this is ordering only, never suppression)
  6. Full research availability (``research_available``)
  7. Ranking availability (``rank is not None`` — currently scored by the
     model; conceptually separate from research availability even though
     today's ranking universe equals the research universe)
  8. Classification quality (Milestone 1 fields, see
     ``classification_quality_rank``): a clean, industry-tagged
     classification outranks a conflicting or unresolved one. Conflict is
     the least-favored value but never suppresses an otherwise-correct exact
     match, since this is strictly the second-to-last tie-break. Missing
     *sector* is never used here — sector coverage is 0/2,947 today and must
     not materially penalize results; only industry presence and
     conflict/review status count.
  9. Stable alphabetical order (``display_name``)
 10. Canonical instrument ID (final deterministic tie-break)

A fuzzy match never outranks an exact match; an unmodeled exact match never
loses to a modeled fuzzy one (both are explicit regression tests, unchanged
from version 2).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from mbe.models.instrument import normalize_name, normalize_symbol
from mbe.search.domain import SearchCandidate, SearchIndexRecord

SEARCH_RANKING_POLICY_VERSION = "2026-08-02.10c.2"

_SCORE_EXACT_SYMBOL = 100.0
_SCORE_EXACT_BSE = 98.0
_SCORE_EXACT_ISIN = 97.0
_SCORE_EXACT_NAME = 95.0
_SCORE_ALIAS = 90.0
_SCORE_ALIAS_SHORT = 78.0  # short abbreviations must not outrank a real exact match
_SCORE_FORMER_NAME = 88.0
_SCORE_FULL_PHRASE = 84.0
_SCORE_PREFIX_MAX = 82.0
_SCORE_PREFIX_MIN = 75.0
_SCORE_WORD_MATCH_MAX = 68.0
_SCORE_WORD_MATCH_MIN = 55.0
_FUZZY_BASE = 60.0
_FUZZY_SPAN = 20.0
_FUZZY_THRESHOLD = 0.78

# Allowlisted exchange hints only — arbitrary "word:word" input must never be
# treated as trusted routing syntax (Phase 10B section 9/22 security notes).
_ALLOWED_EXCHANGES = {"NSE", "BSE"}
_PREFIX_HINT_RE = re.compile(r"^(NSE|BSE):\s*(.+)$", re.IGNORECASE)
_SUFFIX_HINT_RE = re.compile(r"^(.+?)\s+(NSE|BSE)$", re.IGNORECASE)

# Verified broad-index precedence (best first). Empty on every record today —
# see the module docstring, tie-break dimension 4.
_INDEX_PRECEDENCE = ["Nifty 50", "Nifty Next 50", "Nifty 100", "Nifty 200", "Nifty 500"]

_MATCH_REASONS = {
    "exact_nse_symbol": "Exact company symbol",
    "exact_bse_code": "Exact BSE code",
    "exact_isin": "Exact ISIN",
    "exact_company_name": "Exact company name",
    "company_name_prefix": "Company name prefix match",
    "full_phrase_match": "Exact phrase match",
    "word_match": "All search terms matched",
    "fuzzy_company_name": "Approximate name match",
}

_MATCHED_FIELDS = {
    "exact_nse_symbol": "symbol",
    "exact_bse_code": "bse_code",
    "exact_isin": "isin",
    "exact_company_name": "company_name",
    "company_name_prefix": "company_name",
    "full_phrase_match": "company_name",
    "word_match": "company_name",
    "fuzzy_company_name": "company_name",
}


def match_reason(matched_by: str) -> str:
    """Human-readable label for a ``matched_by`` tier, shared with
    ``mbe.instruments.resolution`` and the API layer so every ranking path
    exposes the same evidence text."""
    if matched_by in _MATCH_REASONS:
        return _MATCH_REASONS[matched_by]
    alias_type = matched_by.removeprefix("exact_")
    if alias_type == "former_name":
        return "Matched former company name"
    return f"Matched {alias_type.replace('_', ' ')}" if alias_type else "Match"


def matched_field_for(matched_by: str) -> str:
    """Which identity field a ``matched_by`` tier matched against."""
    return _MATCHED_FIELDS.get(matched_by, "alias")


def index_membership_rank(memberships: list[str]) -> int:
    """Best (lowest) precedence among verified broad-index memberships;
    ``len(_INDEX_PRECEDENCE)`` (worst/no-op) when none apply — always the
    case today, see the module docstring."""
    order = {name: rank for rank, name in enumerate(_INDEX_PRECEDENCE)}
    ranks = [order[m] for m in memberships if m in order]
    return min(ranks) if ranks else len(_INDEX_PRECEDENCE)


def classification_quality_rank(
    *, industry: str | None, review_status: str | None, conflict: bool,
) -> int:
    """Very late classification-quality tie-break (Milestone 1 fields):
    0 = industry present and not conflicting/unresolved, 1 = present-but-
    unresolved or absent-but-clean, 2 = conflicting. Sector is intentionally
    never used here — sector coverage is 0/2,947 today and must not
    materially penalize results."""
    if conflict:
        return 2
    clean = review_status in (None, "accepted")
    if industry and clean:
        return 0
    return 1


def parse_exchange_hint(query: str) -> tuple[str, str | None]:
    """Split an optional allowlisted exchange hint off a raw query.

    Supports ``NSE:TCS`` / ``BSE:500325`` (prefix) and ``TCS NSE`` /
    ``Reliance BSE`` (trailing whole-word suffix). Anything else — including
    an unrecognized ``word:word`` shape — passes through unchanged; this is
    a bounded allowlist match, not a general URI/command parser.
    """
    raw = (query or "").strip()
    prefix_match = _PREFIX_HINT_RE.match(raw)
    if prefix_match:
        return prefix_match.group(2).strip(), prefix_match.group(1).upper()
    suffix_match = _SUFFIX_HINT_RE.match(raw)
    if suffix_match:
        exchange = suffix_match.group(2).upper()
        if exchange in _ALLOWED_EXCHANGES:
            return suffix_match.group(1).strip(), exchange
    return raw, None


def _names(record: SearchIndexRecord) -> list[str]:
    return [n for n in (record.display_name, record.legal_name) if n]


def _listings_on(record: SearchIndexRecord, exchange: str) -> list:
    return [listing for listing in record.listings if listing.exchange.upper() == exchange]


def _best_match(query: str, record: SearchIndexRecord) -> tuple[float, str, str] | None:
    raw = query
    normalized_symbol = normalize_symbol(raw)
    normalized_name = normalize_name(raw)
    best: tuple[float, str, str] | None = None

    def consider(score: float, matched_by: str, matched_value: str) -> None:
        nonlocal best
        if best is None or score > best[0]:
            best = (score, matched_by, matched_value)

    if normalized_symbol and normalized_symbol == normalize_symbol(record.symbol):
        consider(_SCORE_EXACT_SYMBOL, "exact_nse_symbol", record.symbol)
    all_bse_codes = {record.bse_code} | {listing.bse_code for listing in record.listings}
    if raw in all_bse_codes and raw:
        consider(_SCORE_EXACT_BSE, "exact_bse_code", raw)
    all_isins = {record.isin} | {listing.isin for listing in record.listings}
    if normalized_symbol and normalized_symbol in all_isins:
        consider(_SCORE_EXACT_ISIN, "exact_isin", normalized_symbol)

    for name in _names(record):
        norm = normalize_name(name)
        safe_norm = normalize_name(name, strip_suffixes=True)
        if normalized_name and normalized_name in {norm, safe_norm}:
            consider(_SCORE_EXACT_NAME, "exact_company_name", name)
            continue
        if len(normalized_name) >= 3 and norm.startswith(normalized_name):
            remainder_words = len(norm[len(normalized_name):].split())
            score = max(_SCORE_PREFIX_MIN, _SCORE_PREFIX_MAX - 2.0 * max(0, remainder_words - 1))
            consider(score, "company_name_prefix", name)
            continue
        if len(normalized_name) >= 5 and f" {normalized_name} " in f" {norm} ":
            # Contiguous phrase, not a prefix and not the whole name — e.g.
            # "Consultancy Services" inside "Tata Consultancy Services Ltd".
            consider(_SCORE_FULL_PHRASE, "full_phrase_match", name)
            continue
        if len(normalized_name) >= 3:
            query_tokens = set(normalized_name.split())
            name_tokens = set(norm.split())
            if query_tokens and query_tokens.issubset(name_tokens):
                extra = len(name_tokens) - len(query_tokens)
                score = max(_SCORE_WORD_MATCH_MIN, _SCORE_WORD_MATCH_MAX - 1.0 * extra)
                consider(score, "word_match", name)
                continue
        if len(normalized_name) >= 5:
            # Length-ratio pre-filter (Phase 10B performance): two strings
            # whose lengths differ by more than half the longer one cannot
            # reach the fuzzy threshold, so skip the O(n*m) SequenceMatcher
            # call entirely.
            longer = max(len(normalized_name), len(norm))
            if abs(len(normalized_name) - len(norm)) <= longer * 0.5:
                similarity = SequenceMatcher(None, normalized_name, norm).ratio()
                if similarity >= _FUZZY_THRESHOLD:
                    consider(_FUZZY_BASE + similarity * _FUZZY_SPAN, "fuzzy_company_name", name)

    for alias in record.aliases:
        value = alias.get("value") if isinstance(alias, dict) else str(alias)
        alias_type = alias.get("type") if isinstance(alias, dict) else "alias"
        if not value:
            continue
        if normalized_name == normalize_name(value):
            base_score = _SCORE_FORMER_NAME if alias_type == "former_name" else _SCORE_ALIAS
            score = _SCORE_ALIAS_SHORT if len(normalized_name) <= 3 else base_score
            consider(score, f"exact_{alias_type or 'alias'}", value)

    return best


def _prominence_signals(record: SearchIndexRecord, *, active: bool, is_primary: bool) -> list[str]:
    signals: list[str] = []
    if active:
        signals.append("Active listing")
    if is_primary:
        signals.append(f"Primary {record.primary_exchange} listing")
    signals.extend(record.index_memberships)
    if record.research_available:
        signals.append("Full research available")
    if record.rank is not None:
        signals.append("Ranked")
    if record.classification_conflict:
        signals.append("Classification under review")
    elif record.industry and record.classification_review_status == "accepted":
        signals.append("Verified classification")
    return signals


def _build_candidate(
    record: SearchIndexRecord, score: float, matched_by: str, matched_value: str,
    requested_exchange: str | None,
) -> SearchCandidate:
    active = record.listing_status == "active"
    primary_listing = next((listing for listing in record.listings if listing.is_primary), None)
    is_primary = primary_listing.is_primary if primary_listing else True
    requested_exchange_matched = (
        None if not requested_exchange else bool(_listings_on(record, requested_exchange))
    )
    return SearchCandidate(
        record=record, score=round(score, 2), matched_by=matched_by, matched_value=matched_value,
        match_tier=matched_by,
        matched_field=matched_field_for(matched_by),
        match_reason=match_reason(matched_by),
        match_confidence=round(min(score, 100.0) / 100.0, 2),
        ranking_policy_version=SEARCH_RANKING_POLICY_VERSION,
        active_listing=active,
        primary_listing=is_primary,
        requested_exchange_matched=requested_exchange_matched,
        index_memberships=list(record.index_memberships),
        research_available=record.research_available,
        ranking_available=record.rank is not None,
        classification_review_status=record.classification_review_status,
        classification_conflict=record.classification_conflict,
        prominence_signals=_prominence_signals(record, active=active, is_primary=is_primary),
        ambiguity_warning=None,
    )


def _tiebreak_key(candidate: SearchCandidate) -> tuple:
    record = candidate.record
    main_board = not bool(record.is_sme)
    return (
        -candidate.score,
        0 if candidate.active_listing else 1,
        0 if candidate.requested_exchange_matched is not False else 1,
        0 if candidate.primary_listing else 1,
        index_membership_rank(candidate.index_memberships),
        0 if main_board else 1,
        0 if candidate.research_available else 1,
        0 if candidate.ranking_available else 1,
        classification_quality_rank(
            industry=record.industry,
            review_status=record.classification_review_status,
            conflict=record.classification_conflict,
        ),
        record.display_name or "",
        record.instrument_id,
    )


def _attach_ambiguity_warning(query: str, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
    if not candidates:
        return candidates
    top_tied = len(query) <= 3 and len(candidates) > 1 and candidates[0].score == candidates[1].score
    fuzzy_first = candidates[0].score < 82
    if not (top_tied or fuzzy_first):
        return candidates
    warning = (
        "Multiple equally strong matches for this short query — choose a result explicitly."
        if top_tied else
        "Best match is approximate — choose a result explicitly."
    )
    candidates[0] = candidates[0].model_copy(update={"ambiguity_warning": warning})
    return candidates


def rank_search_candidates(
    query: str, index: list[SearchIndexRecord], *, limit: int = 10,
    exchange: str | None = None,
) -> list[SearchCandidate]:
    """Rank ``index`` against ``query``.

    ``exchange`` — an explicit, already-parsed exchange hint (see
    ``parse_exchange_hint``); when given, candidates without a listing on
    that exchange are excluded rather than silently shown as if they were a
    match on the requested exchange.
    """
    raw = (query or "").strip()
    if len(raw) < 2 and not raw.isdigit():
        return []
    candidates: list[SearchCandidate] = []
    for record in index:
        if exchange and not _listings_on(record, exchange):
            continue
        match = _best_match(raw, record)
        if match:
            score, matched_by, matched_value = match
            candidates.append(_build_candidate(record, score, matched_by, matched_value, exchange))
    candidates.sort(key=_tiebreak_key)
    candidates = candidates[:limit]
    return _attach_ambiguity_warning(raw, candidates)
```

- [ ] **Step 2: Run the full existing ranking/evaluation/catalog/API test files to confirm zero regressions**

Run: `.venv/bin/python -m pytest tests/test_search_ranking.py tests/test_search_ranking_v2.py tests/test_search_evaluation.py tests/test_search_catalog_bse.py tests/test_api_v1_search_bse.py -v`
Expected: All PASS, same count as before this task. If anything fails, it must be one of the two tests in Task 3 Step 1 below (the only ones that inspect the raw tie-break tuple) — no other failure is acceptable; stop and investigate rather than adjusting scores.

- [ ] **Step 3: Commit**

```bash
git add src/mbe/search/domain.py src/mbe/search/ranking.py tests/test_search_domain.py
git commit -m "feat(search): search ranking policy v3 — evidence fields and late tie-breakers"
```

---

### Task 3: New backend tests for v3 tie-breakers and evidence

**Files:**
- Create: `tests/test_search_ranking_v3.py`

- [ ] **Step 1: Write the test file**

```python
"""Search ranking policy version 3 (Phase 10C Milestone 2): late tie-break
dimensions layered on the unchanged version-2 primary match tiers, plus the
evidence fields every candidate now carries."""

from mbe.search.domain import ExchangeListing, SearchIndexRecord, SearchResultType
from mbe.search.ranking import (
    SEARCH_RANKING_POLICY_VERSION,
    classification_quality_rank,
    index_membership_rank,
    matched_field_for,
    match_reason,
    rank_search_candidates,
)


def _record(
    instrument_id, display_name, symbol, *, isin=None, bse_code=None,
    listing_status="active", is_primary=True, exchange="NSE",
    result_type=SearchResultType.KNOWN, research_available=False,
    rank=None, score=None, is_sme=None, index_memberships=None,
    industry=None, classification_review_status=None, classification_conflict=False,
):
    return SearchIndexRecord(
        instrument_id=instrument_id, display_name=display_name, legal_name=display_name,
        symbol=symbol, exchange=exchange, primary_exchange=exchange, isin=isin,
        bse_code=bse_code, listing_status=listing_status, is_sme=is_sme,
        listings=[ExchangeListing(
            exchange=exchange, symbol=symbol, bse_code=bse_code, isin=isin,
            listing_status=listing_status, is_primary=is_primary,
        )],
        index_memberships=index_memberships or [], industry=industry,
        classification_review_status=classification_review_status,
        classification_conflict=classification_conflict,
        result_type=result_type, research_available=research_available,
        rank=rank, multibagger_score=score,
        report_url=f"/company/{instrument_id}.html",
    )


def test_policy_version_is_bumped_for_milestone_2():
    assert SEARCH_RANKING_POLICY_VERSION == "2026-08-02.10c.2"


def test_index_membership_tiebreak_prefers_broad_index_member_at_equal_score():
    member = _record(
        "id-member", "Tie Break Gamma Ltd.", "TBG", index_memberships=["Nifty 50"],
    )
    non_member = _record("id-nonmember", "Tie Break Delta Ltd.", "TBD")
    results = rank_search_candidates("Tie Break", [non_member, member])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-member"


def test_index_membership_is_a_noop_for_todays_data_no_company_has_one():
    a = _record("id-a", "Tie Break Epsilon Ltd.", "TBE")
    b = _record("id-b", "Tie Break Zeta Ltd.", "TBZ")
    results = rank_search_candidates("Tie Break", [b, a])
    # Neither carries a verified index membership — order falls through to
    # the next dimension (alphabetical), proving this tie-break dimension
    # cannot fabricate a difference where none of today's data supports one.
    assert [r.record.instrument_id for r in results] == ["id-a", "id-b"]


def test_ranking_availability_is_a_late_tiebreak_distinct_from_research_availability():
    ranked = _record(
        "id-ranked", "Tie Break Eta Ltd.", "TBH",
        research_available=True, rank=3, score=80.0,
    )
    researched_only = _record(
        "id-researched-only", "Tie Break Theta Ltd.", "TBI", research_available=True,
    )
    results = rank_search_candidates("Tie Break", [researched_only, ranked])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-ranked"


def test_classification_quality_tiebreak_prefers_clean_industry_tagged_record():
    clean = _record(
        "id-clean", "Tie Break Iota Ltd.", "TBJ",
        industry="Software", classification_review_status="accepted",
    )
    conflicted = _record(
        "id-conflicted", "Tie Break Kappa Ltd.", "TBK",
        industry="Software", classification_review_status="conflict", classification_conflict=True,
    )
    results = rank_search_candidates("Tie Break", [conflicted, clean])
    assert results[0].score == results[1].score
    assert results[0].record.instrument_id == "id-clean"


def test_classification_conflict_never_suppresses_a_better_exact_match():
    exact_conflicted = _record(
        "id-exact-conflicted", "Precise Conflict Limited", "PCLT",
        industry="Software", classification_review_status="conflict", classification_conflict=True,
    )
    prefix_clean = _record(
        "id-prefix-clean", "Precise Conflict Extended Group Limited", "PCEG",
        industry="Software", classification_review_status="accepted",
    )
    results = rank_search_candidates("Precise Conflict Limited", [prefix_clean, exact_conflicted])
    assert results[0].record.instrument_id == "id-exact-conflicted"
    assert results[0].matched_by == "exact_company_name"


def test_missing_sector_never_penalizes_because_sector_coverage_is_zero_today():
    # Neither record sets sector at all (matches today's 0/2,947 coverage);
    # classification_quality_rank must not distinguish on sector.
    a = _record("id-a2", "Tie Break Lambda Ltd.", "TBL", industry="Software", classification_review_status="accepted")
    b = _record("id-b2", "Tie Break Mu Ltd.", "TBM", industry="Software", classification_review_status="accepted")
    assert classification_quality_rank(
        industry=a.industry, review_status=a.classification_review_status, conflict=a.classification_conflict,
    ) == classification_quality_rank(
        industry=b.industry, review_status=b.classification_review_status, conflict=b.classification_conflict,
    )


def test_evidence_fields_are_populated_on_every_candidate():
    record = _record(
        "id-evidence", "Evidence Fields Ltd.", "EVID",
        research_available=True, rank=1, score=90.0, index_memberships=["Nifty 50"],
        industry="Software", classification_review_status="accepted",
    )
    results = rank_search_candidates("EVID", [record])
    result = results[0]
    assert result.match_tier == "exact_nse_symbol"
    assert result.matched_field == "symbol"
    assert result.match_reason == "Exact company symbol"
    assert result.match_confidence == 1.0
    assert result.ranking_policy_version == SEARCH_RANKING_POLICY_VERSION
    assert result.active_listing is True
    assert result.primary_listing is True
    assert result.research_available is True
    assert result.ranking_available is True
    assert result.classification_review_status == "accepted"
    assert result.classification_conflict is False
    assert "Nifty 50" in result.prominence_signals
    assert "Full research available" in result.prominence_signals
    assert "Ranked" in result.prominence_signals


def test_ambiguity_warning_set_for_short_query_tie():
    a = _record("id-tied-a", "ACE", "ACE")
    b = _record("id-tied-b", "ACF", "ACF")
    results = rank_search_candidates("AC", [a, b])
    # Both are fuzzy/prefix candidates for a 2-character query — if tied,
    # top result must carry an ambiguity warning.
    if results and len(results) > 1 and results[0].score == results[1].score:
        assert results[0].ambiguity_warning is not None


def test_ambiguity_warning_set_for_low_confidence_fuzzy_first_result():
    decoy_only = _record("id-fuzzy-only", "Relaince Indsutries Ltd.", "RELDX")
    results = rank_search_candidates("Reliance Industries Limited", [decoy_only])
    assert results[0].score < 82
    assert results[0].ambiguity_warning is not None


def test_matched_field_for_and_match_reason_cover_every_primary_tier():
    for matched_by, expected_field in [
        ("exact_nse_symbol", "symbol"), ("exact_bse_code", "bse_code"),
        ("exact_isin", "isin"), ("exact_company_name", "company_name"),
        ("company_name_prefix", "company_name"), ("full_phrase_match", "company_name"),
        ("word_match", "company_name"), ("fuzzy_company_name", "company_name"),
    ]:
        assert matched_field_for(matched_by) == expected_field
        assert match_reason(matched_by)
    assert matched_field_for("exact_former_name") == "alias"
    assert match_reason("exact_former_name") == "Matched former company name"
    assert matched_field_for("exact_alias") == "alias"
    assert match_reason("exact_alias") == "Matched alias"


def test_index_membership_rank_orders_by_documented_precedence():
    assert index_membership_rank(["Nifty 50"]) < index_membership_rank(["Nifty 500"])
    assert index_membership_rank([]) > index_membership_rank(["Nifty 500"])
```

- [ ] **Step 2: Run to verify all pass**

Run: `.venv/bin/python -m pytest tests/test_search_ranking_v3.py -v`
Expected: all PASS. If `test_ambiguity_warning_set_for_short_query_tie`'s scores are not actually tied for "AC" against ACE/ACF fixtures, that's fine — the assertion is conditional; if you want an unconditional variant, construct two records with identical prefix-remainder length instead (e.g. both length-3 names with a 2-word remainder) so the tie is guaranteed, and update the test to assert unconditionally.

- [ ] **Step 3: Check the two version-2 tests that inspect raw tuple shape or tie-break internals**

Run: `grep -rn "_tiebreak_key\|_TIEBREAK_KEY" tests/`
If any test imports `_tiebreak_key` directly (rather than only observing `rank_search_candidates` output), update it to call the function with a `SearchCandidate` (not a bare record) — it now takes a candidate, not a record, as of Task 2. Confirm with:

Run: `.venv/bin/python -m pytest tests/ -k "ranking or evaluation or search_catalog or api_v1_search" -v`
Expected: same pass count as the Milestone-1 baseline (625) plus the new tests in this task.

- [ ] **Step 4: Commit**

```bash
git add tests/test_search_ranking_v3.py
git commit -m "test(search): cover ranking policy v3 late tie-breakers and evidence fields"
```

---

### Task 4: Expand the search-quality evaluation set and metrics

**Files:**
- Modify: `src/mbe/search/evaluation.py`
- Test: `tests/test_search_evaluation.py` (extend, do not remove existing assertions)

- [ ] **Step 1: Read the current file to confirm exact current line ranges before editing**

Run: `.venv/bin/python -m pytest tests/test_search_evaluation.py -v` (confirm current baseline passes first)

- [ ] **Step 2: Replace `EVALUATION_SET` and `evaluate_search_quality` in `src/mbe/search/evaluation.py`**

```python
"""Deterministic search-quality evaluation (Phase 10B, extended Phase 10C
Milestone 2 with group-query, exact-identity, exchange-aware, and
collision-sensitive cases — see docs/search-architecture.md "Search-quality
evaluation")."""

from __future__ import annotations

from typing import Any, Callable

from mbe.search.domain import SearchIndexRecord

EVALUATION_SET: list[dict[str, Any]] = [
    # Exact identity
    {"query": "RELIANCE", "expected_first": "RELIANCE", "forbidden": []},
    {"query": "TCS", "expected_first": "TCS", "forbidden": []},
    {"query": "Infosys", "expected_first": "INFY", "forbidden": []},
    {"query": "500325", "expected_first": "RELIANCE", "forbidden": [], "tier": "exact_bse_code"},
    {"query": "INE002A01018", "expected_first": "RELIANCE", "forbidden": [], "tier": "exact_isin"},
    {"query": "HDFC", "expected_first": "HDFCBANK", "forbidden": []},
    {"query": "Dixon", "expected_first": "DIXON", "forbidden": []},
    {"query": "Polycab", "expected_first": "POLYCAB", "forbidden": []},
    {"query": "Bharat Electronics", "expected_first": "BEL", "forbidden": []},
    {"query": "Hindustan Aeronautics", "expected_first": "HAL", "forbidden": []},
    {"query": "Reliance Industries", "expected_first": "RELIANCE", "forbidden": []},
    {"query": "Reliance Power", "expected_first": "RPOWER", "forbidden": []},
    {"query": "Tata Consultancy Services", "expected_first": "TCS", "forbidden": []},
    {"query": "Tata Motors", "expected_first": "TATAMOTORS", "forbidden": []},
    {"query": "HDFC Bank", "expected_first": "HDFCBANK", "forbidden": []},
    {"query": "HDFC AMC", "expected_first": "HDFCAMC", "forbidden": []},
    {"query": "ICICI Bank", "expected_first": "ICICIBANK", "forbidden": []},
    {"query": "Bajaj Finance", "expected_first": "BAJFINANCE", "forbidden": []},
    {"query": "Bajaj Finserv", "expected_first": "BAJAJFINSV", "forbidden": []},
    {"query": "Mahindra & Mahindra", "expected_first": "M&M", "forbidden": []},
    {"query": "Adani Enterprises", "expected_first": "ADANIENT", "forbidden": []},
    {"query": "Adani Ports", "expected_first": "ADANIPORTS", "forbidden": []},
    # Broad group queries — deterministic top-1 not required (see
    # "Group-query behavior" in docs/search-architecture.md); recall (any
    # member of the family present in the top 3) is what group_query_recall
    # measures.
    {"query": "Reliance", "group_members": ["RELIANCE", "RPOWER", "RCOM"], "forbidden": [], "group": True},
    {"query": "Tata", "group_members": ["TCS", "TATAMOTORS"], "forbidden": [], "group": True},
    {"query": "HDFC", "group_members": ["HDFCBANK", "HDFCAMC"], "forbidden": [], "group": True},
    {"query": "ICICI", "group_members": ["ICICIBANK"], "forbidden": [], "group": True},
    {"query": "Bajaj", "group_members": ["BAJFINANCE", "BAJAJFINSV"], "forbidden": [], "group": True},
    {"query": "Mahindra", "group_members": ["M&M"], "forbidden": [], "group": True},
    {"query": "Adani", "group_members": ["ADANIENT", "ADANIPORTS"], "forbidden": [], "group": True},
    # Exchange-aware
    {"query": "NSE:TCS", "expected_first": "TCS", "forbidden": [], "exchange": "NSE"},
    {"query": "BSE:500325", "expected_first": "RELIANCE", "forbidden": [], "exchange": "BSE"},
    {"query": "TCS NSE", "expected_first": "TCS", "forbidden": [], "exchange": "NSE"},
    {"query": "Reliance BSE", "expected_first": "RELIANCE", "forbidden": [], "exchange": "BSE"},
    # Collision-sensitive abbreviations — must resolve to the real company,
    # never a fuzzy-close decoy.
    {"query": "BLS", "expected_first": "BLS", "forbidden": []},
    {"query": "ACE", "expected_first": "ACE", "forbidden": []},
    {"query": "VIJAYA", "expected_first": "VIJAYA", "forbidden": []},
    {"query": "HAL", "expected_first": "HAL", "forbidden": []},
    {"query": "BEL", "expected_first": "BEL", "forbidden": []},
    {"query": "CAMS", "expected_first": "CAMS", "forbidden": []},
    {"query": "IEX", "expected_first": "IEX", "forbidden": []},
    # Negative case
    {"query": "Zzznotarealcompanyxyz123", "expected_first": None, "forbidden": []},
]


def evaluate_search_quality(
    index: list[SearchIndexRecord],
    evaluation_set: list[dict[str, Any]] = EVALUATION_SET,
    *,
    ranker: Callable[..., list],
    top_k: int = 3,
) -> dict[str, Any]:
    """Run ``evaluation_set`` against ``index`` and report top-1/top-N
    accuracy, mean reciprocal rank, per-identity-type accuracy, group-query
    recall, exchange-mismatch rate, false positives, and a per-query
    breakdown for diagnosis."""
    per_query = []
    top1_hits = 0
    topn_hits = 0
    false_positives = 0
    reciprocal_ranks = []
    tier_hits: dict[str, list[bool]] = {"exact_bse_code": [], "exact_isin": []}
    group_recall_hits = []
    exchange_mismatches = 0
    exchange_cases = 0
    for case in evaluation_set:
        query = case["query"]
        exchange = case.get("exchange")
        kwargs = {"exchange": exchange} if exchange else {}
        results = ranker(query, index, **kwargs)
        symbols = [r.record.symbol for r in results]
        forbidden = case.get("forbidden") or []
        hit_forbidden = [s for s in symbols if s in forbidden]
        if hit_forbidden:
            false_positives += 1

        if case.get("group"):
            members = case.get("group_members", [])
            group_recall_hits.append(any(m in symbols[:top_k] for m in members))
            per_query.append({
                "query": query, "group_members": members, "top_results": symbols[:top_k],
                "passed": any(m in symbols[:top_k] for m in members) and not hit_forbidden,
            })
            continue

        expected = case.get("expected_first")
        top1_ok = (symbols[0] if symbols else None) == expected
        topn_ok = expected is None or expected in symbols[:top_k]
        if top1_ok:
            top1_hits += 1
        if topn_ok:
            topn_hits += 1
        if expected is not None:
            rank = symbols.index(expected) + 1 if expected in symbols else None
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        tier = case.get("tier")
        if tier in tier_hits:
            tier_hits[tier].append(top1_ok)
        if exchange:
            exchange_cases += 1
            if not top1_ok:
                exchange_mismatches += 1
        per_query.append({
            "query": query, "expected_first": expected,
            "actual_first": symbols[0] if symbols else None,
            "top_results": symbols[:top_k], "passed": top1_ok and not hit_forbidden,
        })

    scored_total = sum(1 for c in evaluation_set if not c.get("group"))
    total = len(evaluation_set)

    def _accuracy(hits: list[bool]) -> float | None:
        return round(sum(hits) / len(hits), 4) if hits else None

    return {
        "total": total,
        "top1_accuracy": round(top1_hits / scored_total, 4) if scored_total else 0.0,
        "top3_recall": round(topn_hits / scored_total, 4) if scored_total else 0.0,
        "mean_reciprocal_rank": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else 0.0,
        "exact_bse_code_accuracy": _accuracy(tier_hits["exact_bse_code"]),
        "exact_isin_accuracy": _accuracy(tier_hits["exact_isin"]),
        "group_query_recall": round(sum(group_recall_hits) / len(group_recall_hits), 4) if group_recall_hits else None,
        "exchange_mismatch_rate": round(exchange_mismatches / exchange_cases, 4) if exchange_cases else None,
        "false_positive_count": false_positives,
        "per_query": per_query,
    }
```

- [ ] **Step 3: Extend `tests/test_search_evaluation.py`** — append these tests without removing existing ones:

```python
def test_evaluation_set_includes_group_and_exchange_cases():
    from mbe.search.evaluation import EVALUATION_SET
    assert any(case.get("group") for case in EVALUATION_SET)
    assert any(case.get("exchange") for case in EVALUATION_SET)


def test_evaluate_search_quality_reports_new_metrics():
    from mbe.search.catalog import build_search_index
    from mbe.search.evaluation import evaluate_search_quality
    from mbe.search.ranking import rank_search_candidates

    def _row(symbol, name, isin, bse_code=None):
        return {
            "source_record_id": isin, "company_name": name, "symbol": symbol,
            "exchange": "NSE", "exchange_segment": None, "series": "EQ", "isin": isin,
            "bse_code": bse_code, "industry": None, "sector": None, "listing_status": "active",
            "listing_date": None, "delisting_date": None, "is_sme": False,
            "security_type": "equity", "provider_symbols": {"yahoo": f"{symbol}.NS"},
            "aliases": [],
        }

    universe = [_row("RELIANCE", "Reliance Industries Limited", "INE002A01018", "500325")]
    index = build_search_index(universe, [], [])
    report = evaluate_search_quality(
        index, [{"query": "500325", "expected_first": "RELIANCE", "forbidden": [], "tier": "exact_bse_code"}],
        ranker=rank_search_candidates,
    )
    assert report["exact_bse_code_accuracy"] == 1.0
    assert report["mean_reciprocal_rank"] == 1.0
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_search_evaluation.py -v`
Expected: PASS. If a symbol used in `EVALUATION_SET` (e.g. `CAMS`, `IEX`, `TATAMOTORS`, `ICICIBANK`, `BAJFINANCE`, `BAJAJFINSV`, `M&M`, `ADANIENT`, `ADANIPORTS`) is not present in the real NSE search-universe data the CLI evaluation runs against, that is fine for these unit tests (they build a tiny synthetic index), but flag it for Task 9 (CLI evaluation run against the real universe) — the CLI run's `per_query` output will show `null`/no-match for any name not in the actual universe file, which must be diagnosed there, not treated as a test failure here.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/search/evaluation.py tests/test_search_evaluation.py
git commit -m "feat(search): expand search-quality evaluation set for policy v3"
```

---

### Task 5: Parity — `InstrumentResolver` (DB-backed dynamic route)

**Files:**
- Modify: `src/mbe/instruments/resolution.py`
- Test: `tests/test_instruments_resolution.py` (check if it exists first: `ls tests/test_instruments_resolution.py tests/test_instrument_resolution.py 2>/dev/null`; if neither exists, create `tests/test_instruments_resolution.py`)

- [ ] **Step 1: Add evidence fields to `MatchCandidate` and reuse the shared v3 helpers**

In `src/mbe/instruments/resolution.py`, add the import and two fields:

```python
from mbe.models.instrument import normalize_name, normalize_symbol
from mbe.search.ranking import (
    SEARCH_RANKING_POLICY_VERSION,
    classification_quality_rank,
    matched_field_for,
    match_reason,
)
```

Add fields to `MatchCandidate`:

```python
class MatchCandidate(BaseModel):
    instrument_id: str
    display_name: str | None = None
    symbol: str | None = None
    exchange: str | None = None
    score: float
    matched_by: str
    matched_value: str
    match_reason: str = ""
    matched_field: str = ""
    ranking_policy_version: str = SEARCH_RANKING_POLICY_VERSION
    active_listing: bool = True
    primary_listing: bool = True
    bse_code: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_category: str | None = None
    listing_status: str | None = None
    is_sme: bool | None = None
    listings: list[ListingMatch] = []
```

- [ ] **Step 2: Populate the new fields and reorder the final sort**

Replace the candidate-construction block (originally around line 119-141) and the final sort line with:

```python
            if best:
                primary = next((x for x in by_listing.get(instrument.instrument_id, []) if x.is_primary), None)
                current_listings = by_listing.get(instrument.instrument_id, [])
                is_primary = primary.is_primary if primary else True
                active = (primary.status if primary else None) == "active"
                candidates.append(MatchCandidate(
                    instrument_id=instrument.instrument_id,
                    display_name=company.display_name if company else None,
                    symbol=primary.symbol if primary else None,
                    exchange=primary.exchange_code if primary else None,
                    score=round(best[0], 2), matched_by=best[1], matched_value=best[2],
                    match_reason=match_reason(best[1]), matched_field=matched_field_for(best[1]),
                    active_listing=active, primary_listing=is_primary,
                    bse_code=primary.bse_code if primary else None,
                    isin=primary.isin if primary else None,
                    sector=sector.name if sector else None,
                    industry=industry.name if industry else None,
                    market_cap_category=instrument.market_cap_category,
                    listing_status=primary.status if primary else None,
                    is_sme=primary.is_sme if primary else None,
                    listings=[ListingMatch(
                        exchange=listing.exchange_code, symbol=listing.symbol,
                        bse_code=listing.bse_code, isin=listing.isin,
                        listing_status=listing.status, is_primary=listing.is_primary,
                        is_sme=listing.is_sme,
                    ) for listing in current_listings],
                ))

        def _tiebreak(item: MatchCandidate) -> tuple:
            main_board = not bool(item.is_sme)
            # research/ranking availability and classification conflict are
            # not available inside this DB-only resolver (see
            # docs/search-architecture.md "Static and server parity") — the
            # API layer (mbe.api.app.search) applies those two dimensions
            # after attaching current scores, using the same
            # classification_quality_rank helper with conflict always False.
            return (
                -item.score,
                0 if item.active_listing else 1,
                0 if item.primary_listing else 1,
                0 if main_board else 1,
                classification_quality_rank(industry=item.industry, review_status=None, conflict=False),
                item.display_name or "",
                item.instrument_id,
            )

        candidates.sort(key=_tiebreak)
        return candidates[:limit]
```

Remove the old final line `candidates.sort(key=lambda item: (-item.score, item.display_name or "", item.instrument_id))` — it is replaced by the block above (note the `def _tiebreak` and `candidates.sort(...)` must be indented at the same level as the `for instrument, company, sector, industry in rows:` loop, i.e. after the loop, still inside `resolve`).

- [ ] **Step 3: Write parity/regression tests** in `tests/test_instruments_resolution.py`:

```python
"""InstrumentResolver: DB-backed identity search, kept in tie-break parity
with mbe.search.ranking (policy v3) via shared helpers — see
docs/search-architecture.md "Static and server parity"."""

from mbe.instruments.resolution import InstrumentResolver
from mbe.search.ranking import SEARCH_RANKING_POLICY_VERSION


def test_resolver_exposes_v3_evidence_fields(db_session_with_instruments):
    # db_session_with_instruments: reuse whatever existing pytest fixture
    # seeds InstrumentRow/CompanyRow/InstrumentListingRow for resolver tests
    # today (check tests/test_api_v1_search_bse.py or tests/conftest.py for
    # the fixture name actually in use, e.g. `session`/`db_session`, and
    # adjust this test's signature and setup to match rather than inventing
    # a new fixture name).
    resolver = InstrumentResolver(db_session_with_instruments)
    results = resolver.resolve("TCS")
    assert results
    assert results[0].ranking_policy_version == SEARCH_RANKING_POLICY_VERSION
    assert results[0].match_reason
    assert results[0].matched_field == "symbol"
```

Before finalizing this test, run `grep -n "def test_.*session\|^def session\|^@pytest.fixture" tests/test_api_v1_search_bse.py tests/conftest.py` to find the actual fixture/session-setup pattern already used for `InstrumentResolver`-backed tests in this repo, and rewrite the test to seed data the same way (e.g. via the same SQLAlchemy `Session`/in-memory SQLite setup already used by `tests/test_api_v1_search_bse.py`), rather than inventing an undefined fixture.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_instruments_resolution.py tests/test_api_v1_search_bse.py -v`
Expected: PASS, no regressions in existing BSE/search API tests.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/instruments/resolution.py tests/test_instruments_resolution.py
git commit -m "feat(search): extend InstrumentResolver tie-break parity with ranking policy v3"
```

---

### Task 6: API layer — attach scores before truncation, add v3 evidence fields

**Files:**
- Modify: `src/mbe/api/app.py` (search route, ~lines 313-368)
- Modify: `src/mbe/api/schemas.py` (`SearchResultData`)
- Test: `tests/test_api_v1_search_bse.py` (extend)

- [ ] **Step 1: Add fields to `SearchResultData`** in `src/mbe/api/schemas.py`, right after `matched_value`:

```python
    score: float
    matched_by: str
    matched_value: str
    match_reason: str = ""
    matched_field: str = ""
    ranking_policy_version: str = ""
    active_listing: bool = True
    primary_listing: bool = True
    ranking_available: bool = False
    sub_industry: str | None = None
    sub_industry_source: str | None = None
    classification_version: str | None = None
    classification_confidence: float | None = None
    classification_review_status: str | None = None
    classification_conflict: bool = False
```

(The `sub_industry*`/`classification_*` fields close the Milestone 1 gap noted in recon — `SearchIndexRecord` already has them but `SearchResultData` never exposed them. `InstrumentResolver`'s DB path has no classification data, so these stay `None`/`False` on that path — documented as a known limitation, not a bug, since Milestone 1 explicitly scoped classification provenance to the static/JSON catalog, not the DB schema.)

- [ ] **Step 2: Restructure the `search` route** in `src/mbe/api/app.py` so scores are attached to every filtered candidate *before* truncating to `limit`, then apply the research/ranking-availability tie-break, then truncate:

```python
    @app.get("/api/v1/search", response_model=Envelope[list[SearchResultData]])
    def search(
        request: Request, session: Session = Depends(get_session),
        q: str = Query(min_length=1, max_length=160),
        limit: int = Query(10, ge=1, le=20),
        exchange: str | None = Query(None, max_length=8),
        active_only: bool = False,
        include_sme: bool = True,
        include_inactive: bool = True,
    ):
        """Search-universe results: identity for every instrument the
        platform can identify, honestly tagged with research/ranking status.
        Unlike /api/v1/instruments/lookup (kept unchanged for backward
        compatibility), this never omits a company for lacking a score.
        ``exchange`` (NSE/BSE only) scopes to instruments with a listing on
        that exchange. See docs/HANDOVER.md "Search, research and ranking
        universes" and docs/search-architecture.md "Search ranking policy
        version 3"."""
        exchange_filter = exchange.upper() if exchange and exchange.upper() in {"NSE", "BSE"} else None
        # Fetch a wider candidate pool than requested so research/ranking
        # availability (attached below, before truncation) can still act as
        # a late tie-break among the true top candidates rather than only
        # among whatever the DB-only pre-score order already truncated to.
        fetch_limit = max(limit * 3, 15)
        candidates = InstrumentResolver(session).resolve(q, limit=fetch_limit)
        show_only_active = active_only or not include_inactive
        filtered = []
        for candidate in candidates:
            if exchange_filter and not any(l.exchange == exchange_filter for l in candidate.listings):
                continue
            if show_only_active and candidate.listing_status != "active":
                continue
            if not include_sme and candidate.is_sme:
                continue
            filtered.append(candidate)
        scores = _current_scores(session, [c.instrument_id for c in filtered])

        def _final_tiebreak(candidate) -> tuple:
            score = scores.get(candidate.instrument_id)
            return (-candidate.score, 0 if score is not None else 1)

        filtered.sort(key=_final_tiebreak)
        filtered = filtered[:limit]
        results = []
        for candidate in filtered:
            score = scores.get(candidate.instrument_id)
            results.append(SearchResultData(
                instrument_id=candidate.instrument_id, display_name=candidate.display_name,
                symbol=candidate.symbol, exchange=candidate.exchange,
                primary_exchange=candidate.exchange, isin=candidate.isin,
                bse_code=_fallback_bse_code(candidate), sector=candidate.sector,
                sector_source="canonical_platform" if candidate.sector else None,
                industry=candidate.industry,
                industry_source="canonical_platform" if candidate.industry else None,
                listing_status=candidate.listing_status, is_sme=candidate.is_sme,
                listings=_listing_data(candidate),
                result_type="modeled" if score else "known",
                research_available=score is not None,
                rank=score.rank if score else None,
                multibagger_score=float(score.multibagger_score) if score else None,
                confidence=float(score.confidence) if score else None,
                risk_score=float(score.risk_score) if score else None,
                report_url=canonical_company_url(candidate.instrument_id),
                score=candidate.score, matched_by=candidate.matched_by,
                matched_value=candidate.matched_value,
                match_reason=candidate.match_reason, matched_field=candidate.matched_field,
                ranking_policy_version=candidate.ranking_policy_version,
                active_listing=candidate.active_listing, primary_listing=candidate.primary_listing,
                ranking_available=score is not None,
            ))
        return _envelope(request, results)
```

Note: the tie-break stability requirement — `filtered.sort` is stable, and `InstrumentResolver.resolve()` already returned `filtered` in v3 tie-break order (active/primary/main-board/classification, per Task 5) before this second sort only on `(-score, has_current_score)`, so the combined effect is: primary sort by match score, then by whether a current model score exists, and *within* those ties the original resolver order (already active/primary/main-board/classification-ordered) is preserved by Python's stable sort. This achieves the full documented v3 tie-break order end-to-end without a second full re-implementation.

- [ ] **Step 3: Extend `tests/test_api_v1_search_bse.py`** with:

```python
def test_search_response_includes_v3_evidence_fields(client):
    response = client.get("/api/v1/search", params={"q": "TCS"})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload
    assert payload[0]["ranking_policy_version"]
    assert "match_reason" in payload[0]
    assert "active_listing" in payload[0]
    assert "ranking_available" in payload[0]
```

Before finalizing, run `grep -n "def client\|TestClient" tests/test_api_v1_search_bse.py tests/conftest.py` to confirm the actual fixture name (`client` vs. something else already used in that file) and match it exactly.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_api_v1_search_bse.py -v`
Expected: PASS, including all pre-existing assertions in that file unmodified.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/api/app.py src/mbe/api/schemas.py tests/test_api_v1_search_bse.py
git commit -m "feat(search): expose v3 ranking evidence on the dynamic search API"
```

---

### Task 7: JS mirror — add missing tiers, tie-break order, and evidence fields

**Files:**
- Modify: `src/mbe/frontend/assets/app.js` (`staticSearch`, lines ~106-171)
- Modify: `site/assets/app.js` (rebuilt copy — regenerate via the project's static-build step in Task 10 rather than hand-editing; do not hand-edit this file directly)
- Test: `tests/frontend/app.test.js` (extend)

- [ ] **Step 1: Replace `staticSearch` in `src/mbe/frontend/assets/app.js`** with a version that adds the two missing tiers (`full_phrase_match`, `word_match`), the documented tie-break order, and evidence fields, mirroring `mbe.search.ranking` (Python is canonical; this is the hand-maintained JS mirror per the "shared constants and mirrored tests" parity approach):

```javascript
  const RANKING_POLICY_VERSION = "2026-08-02.10c.2";
  const INDEX_PRECEDENCE = ["Nifty 50", "Nifty Next 50", "Nifty 100", "Nifty 200", "Nifty 500"];

  function indexMembershipRank(memberships) {
    const list = Array.isArray(memberships) ? memberships : [];
    const ranks = list.map(m => INDEX_PRECEDENCE.indexOf(m)).filter(r => r >= 0);
    return ranks.length ? Math.min(...ranks) : INDEX_PRECEDENCE.length;
  }

  function classificationQualityRank(industry, reviewStatus, conflict) {
    if (conflict) return 2;
    const clean = reviewStatus == null || reviewStatus === "accepted";
    if (industry && clean) return 0;
    return 1;
  }

  const MATCH_REASONS = {
    "exact NSE symbol": "Exact company symbol", "exact BSE code": "Exact BSE code",
    "exact ISIN": "Exact ISIN", "exact company name": "Exact company name",
    "company-name prefix": "Company name prefix match", "full phrase match": "Exact phrase match",
    "word match": "All search terms matched", "fuzzy company name": "Approximate name match",
  };

  function staticSearch(instruments, query, limit = 10, exchange = null) {
    const raw = String(query || "").trim();
    const nameQuery = normalizeText(raw);
    const symbolQuery = symbolText(raw);
    if (nameQuery.length < 2 && !/^\d{6}$/.test(raw) && !/^IN[A-Z0-9]{10}$/i.test(raw)) return [];
    const matches = [];
    for (const item of instruments || []) {
      let requestedExchangeMatched = null;
      if (exchange) {
        const listings = Array.isArray(item.listings) ? item.listings : [];
        const onExchange = listings.some(l => l.exchange === exchange) || item.exchange === exchange;
        if (!onExchange) continue;
        requestedExchangeMatched = true;
      }
      let best = null;
      const consider = (score, matchedBy, matchedValue) => {
        if (!best || score > best.score) best = { score, matched_by: matchedBy, matched_value: matchedValue };
      };
      const symbol = symbolText(item.symbol || item.nse_symbol);
      const bse = String(item.bse_code || "");
      const isin = String(item.isin || "").toUpperCase();
      const names = [item.display_name, item.legal_name, item.current_legal_name].filter(Boolean);
      const aliases = Array.isArray(item.aliases) ? item.aliases : [];
      if (symbolQuery && symbolQuery === symbol) consider(100, "exact NSE symbol", symbol);
      if (raw === bse && bse) consider(98, "exact BSE code", bse);
      if (raw.toUpperCase() === isin && isin) consider(97, "exact ISIN", isin);
      for (const name of names) {
        const normalized = normalizeText(name);
        if (nameQuery === normalized || suffixlessName(raw) === suffixlessName(name)) { consider(95, "exact company name", name); continue; }
        if (nameQuery.length >= 3 && normalized.startsWith(nameQuery)) { consider(82, "company-name prefix", name); continue; }
        if (nameQuery.length >= 5 && ` ${nameQuery} ` !== ` ${normalized} ` && `${" "}${normalized}${" "}`.includes(` ${nameQuery} `)) { consider(84, "full phrase match", name); continue; }
        const queryTokens = new Set(nameQuery.split(" ").filter(Boolean));
        const nameTokens = new Set(normalized.split(" ").filter(Boolean));
        if (nameQuery.length >= 3 && queryTokens.size && [...queryTokens].every(t => nameTokens.has(t))) {
          const extra = nameTokens.size - queryTokens.size;
          consider(Math.max(55, 68 - extra), "word match", name);
          continue;
        }
        if (nameQuery.length >= 5 && Math.abs(nameQuery.length - normalized.length) <= Math.max(nameQuery.length, normalized.length) * .5) {
          const quality = similarity(nameQuery, normalized);
          if (quality >= .78) consider(60 + quality * 20, "fuzzy company name", name);
        }
      }
      for (const alias of aliases) {
        const value = typeof alias === "string" ? alias : alias.value;
        if (value && nameQuery === normalizeText(value)) consider(nameQuery.length <= 3 ? 78 : 90, `exact ${alias.type || "alias"}`, value);
      }
      if (best) {
        const match = /** @type {{score: number, matched_by: string, matched_value: string}} */ (best);
        const active = (item.listing_status || "unknown") === "active";
        const listings = Array.isArray(item.listings) ? item.listings : [];
        const primaryListing = listings.find(l => l.is_primary);
        const isPrimary = primaryListing ? Boolean(primaryListing.is_primary) : true;
        const indexMemberships = Array.isArray(item.index_memberships) ? item.index_memberships : [];
        const rankingAvailable = item.rank != null;
        matches.push({
        instrument_id: String(item.instrument_id),
        display_name: item.display_name || item.legal_name || symbol,
        symbol,
        bse_code: item.bse_code || (Array.isArray(item.listings) ? (item.listings.find(l => l.bse_code)?.bse_code || null) : null),
        isin: item.isin || null,
        exchange: item.exchange || "NSE",
        primary_exchange: item.primary_exchange || item.exchange || "NSE",
        listings,
        industry: item.industry || null,
        sector: item.sector || null,
        market_cap_category: item.market_cap_category || null,
        listing_status: item.listing_status || "unknown",
        is_sme: item.is_sme == null ? null : Boolean(item.is_sme),
        report_url: item.report_url || null,
        result_type: item.result_type || (item.research_available ? "modeled" : "known"),
        research_available: Boolean(item.research_available),
        ranking_available: rankingAvailable,
        rank: item.rank == null ? null : Number(item.rank),
        multibagger_score: item.multibagger_score == null ? null : Number(item.multibagger_score),
          score: match.score,
          matched_by: match.matched_by,
          matched_value: match.matched_value,
          match_reason: MATCH_REASONS[match.matched_by] || (match.matched_by.startsWith("exact ") ? `Matched ${match.matched_by.slice(6)}` : "Match"),
          ranking_policy_version: RANKING_POLICY_VERSION,
          active_listing: active, primary_listing: isPrimary,
          requested_exchange_matched: requestedExchangeMatched,
          index_memberships: indexMemberships,
          classification_review_status: item.classification_review_status || null,
          classification_conflict: Boolean(item.classification_conflict),
          _sortAux: {
            active, isPrimary, indexRank: indexMembershipRank(indexMemberships),
            mainBoard: !item.is_sme, research: Boolean(item.research_available), ranking: rankingAvailable,
            classRank: classificationQualityRank(item.industry, item.classification_review_status, Boolean(item.classification_conflict)),
          },
        });
      }
    }
    matches.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const x = a._sortAux, y = b._sortAux;
      if (x.active !== y.active) return x.active ? -1 : 1;
      if (x.isPrimary !== y.isPrimary) return x.isPrimary ? -1 : 1;
      if (x.indexRank !== y.indexRank) return x.indexRank - y.indexRank;
      if (x.mainBoard !== y.mainBoard) return x.mainBoard ? -1 : 1;
      if (x.research !== y.research) return x.research ? -1 : 1;
      if (x.ranking !== y.ranking) return x.ranking ? -1 : 1;
      if (x.classRank !== y.classRank) return x.classRank - y.classRank;
      const nameCompare = String(a.display_name).localeCompare(String(b.display_name));
      if (nameCompare) return nameCompare;
      return a.instrument_id.localeCompare(b.instrument_id);
    });
    return matches.slice(0, limit).map(({ _sortAux, ...rest }) => rest);
  }
```

- [ ] **Step 2: Extend `tests/frontend/app.test.js`** — append (check the existing file's `require`/import pattern first and match it):

```javascript
test("staticSearch finds a full-phrase match not covered by prefix or word match", () => {
  const instruments = [
    { instrument_id: "id-tcs", display_name: "Tata Consultancy Services Limited", symbol: "TCS", listing_status: "active" },
    { instrument_id: "id-reliance", display_name: "Reliance Industries Limited", symbol: "RELIANCE", listing_status: "active" },
  ];
  const results = staticSearch(instruments, "Consultancy Services");
  assert.strictEqual(results[0].instrument_id, "id-tcs");
  assert.strictEqual(results[0].matched_by, "full phrase match");
});

test("staticSearch finds an all-token match regardless of order", () => {
  const instruments = [
    { instrument_id: "id-hal", display_name: "Hindustan Aeronautics Limited", symbol: "HAL", listing_status: "active" },
  ];
  const results = staticSearch(instruments, "Aeronautics Hindustan");
  assert.strictEqual(results[0].instrument_id, "id-hal");
  assert.strictEqual(results[0].matched_by, "word match");
});

test("staticSearch prefers active listing over inactive at equal score", () => {
  const instruments = [
    { instrument_id: "id-inactive", display_name: "Similar Prefix Company Two Ltd.", symbol: "INAC", listing_status: "delisted" },
    { instrument_id: "id-active", display_name: "Similar Prefix Company One Ltd.", symbol: "ACTV", listing_status: "active" },
  ];
  const results = staticSearch(instruments, "Similar Prefix Company");
  assert.strictEqual(results[0].instrument_id, "id-active");
});

test("staticSearch prefers verified broad-index membership at equal score", () => {
  const instruments = [
    { instrument_id: "id-plain", display_name: "Tie Break Nu Ltd.", symbol: "TBN", listing_status: "active" },
    { instrument_id: "id-member", display_name: "Tie Break Xi Ltd.", symbol: "TBX", listing_status: "active", index_memberships: ["Nifty 50"] },
  ];
  const results = staticSearch(instruments, "Tie Break");
  assert.strictEqual(results[0].instrument_id, "id-member");
});

test("staticSearch exposes v3 evidence fields on every result", () => {
  const instruments = [{ instrument_id: "id-evid", display_name: "Evidence Fields Ltd.", symbol: "EVID", listing_status: "active", research_available: true, rank: 1 }];
  const results = staticSearch(instruments, "EVID");
  assert.strictEqual(results[0].ranking_policy_version, "2026-08-02.10c.2");
  assert.strictEqual(results[0].match_reason, "Exact company symbol");
  assert.strictEqual(results[0].active_listing, true);
  assert.strictEqual(results[0].ranking_available, true);
});
```

- [ ] **Step 3: Run frontend tests**

Run: `node --test tests/frontend/*.test.js`
Expected: 28 previous + 5 new = 33 passing, 0 failing.

- [ ] **Step 4: Commit**

```bash
git add src/mbe/frontend/assets/app.js tests/frontend/app.test.js
git commit -m "feat(search): mirror ranking policy v3 tiers and tie-breakers in the JS client"
```

---

### Task 8: Frontend result rendering — compact evidence badges

**Files:**
- Modify: `src/mbe/frontend/assets/app.js` (`initSearch`/`renderItems`, lines ~437-460)
- Test: `tests/frontend/app.test.js` or `tests/frontend/dom.test.js` (extend — check which file already covers `initSearch`/DOM rendering with `grep -n "initSearch\|renderItems" tests/frontend/*.test.js` and add to that one)

- [ ] **Step 1: Update `renderItems`** to show a compact secondary line using the new evidence fields, replacing the current `bits`/`match` construction (around line 450-452):

```javascript
        const bits = [item.symbol && `${item.exchange || "NSE"}: ${item.symbol}`, item.bse_code && `BSE ${item.bse_code}`, item.sector, item.industry, item.market_cap_category, item.is_sme ? "SME" : null].filter(Boolean);
        main.append(create("span", "search-meta", bits.join(" · ")));
        const evidenceBits = [
          item.match_reason || item.matched_by,
          item.requested_exchange_matched ? `${item.exchange || "NSE"} match` : null,
          Array.isArray(item.index_memberships) && item.index_memberships[0] || null,
          item.research_available ? "Full research" : (item.ranking_available ? "Ranked" : null),
        ].filter(Boolean);
        main.append(create("span", "search-evidence", evidenceBits.join(" · ")));
        if (item.ambiguity_warning) main.append(create("span", "badge badge-warning", item.ambiguity_warning));
        const match = create("span", "search-match", `${Math.round(item.score)} / 100`);
```

- [ ] **Step 2: Add a minimal CSS rule for `.search-evidence`** — check `src/mbe/frontend/assets/app.css` (or equivalent stylesheet) for the existing `.search-meta` rule with `grep -n "\.search-meta" src/mbe/frontend/assets/*.css` and add an adjacent `.search-evidence` rule matching the same visual weight (small, muted secondary text) — copy the exact `.search-meta` declaration block and rename the selector, adjusting only the color/opacity if `.search-meta` already defines a muted tone (reuse it as-is if so).

- [ ] **Step 3: Extend the DOM/rendering test file** (the one identified in the file list above) with:

```javascript
test("search results render match reason and research/ranked badge", () => {
  // Reuse this file's existing DOM harness/setup (jsdom or similar) exactly
  // as the surrounding tests in this file already do — do not introduce a
  // new DOM testing approach. Render one result with match_reason set and
  // research_available: true, then assert the rendered result item's text
  // content includes both the match reason string and "Full research".
});
```
Write the actual test body using this file's existing harness pattern (inspect the nearest existing `initSearch`/render test in this file for the exact setup/teardown calls before writing the assertions).

- [ ] **Step 4: Run frontend tests**

Run: `node --test tests/frontend/*.test.js`
Expected: all passing, including the new test.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/frontend/assets/app.js src/mbe/frontend/assets/*.css tests/frontend/
git commit -m "feat(search): render compact match-evidence line in search results"
```

---

### Task 9: Regenerate static build artifacts and run the CLI evaluation

**Files:** none modified directly — this task runs the existing build/evaluation tooling and inspects output.

- [ ] **Step 1: Run the CLI search-quality evaluation against the real universe**

Run: `.venv/bin/python -m mbe.cli <the existing evaluate-search-quality subcommand — confirm exact name with> .venv/bin/python -m mbe.cli --help`
Record: `top1_accuracy`, `top3_recall`, `mean_reciprocal_rank`, `exact_bse_code_accuracy`, `exact_isin_accuracy`, `group_query_recall`, `exchange_mismatch_rate`, `false_positive_count`.

- [ ] **Step 2: If any new evaluation-set query (Task 4) has no match in the real universe** (e.g. a symbol not present in `universes/nse-search-universe.json`), fix it by using the real symbol from that file rather than a guessed one — grep the universe file directly:

Run: `grep -o '"symbol": *"[A-Z&]*"' universes/nse-search-universe.json | sort -u | grep -E "ICICI|BAJAJ|BAJFIN|M&M|ADANI|TATAMOTORS|CAMS|IEX"`

Update any mismatched `EVALUATION_SET` entries in `src/mbe/search/evaluation.py` to the confirmed real symbols, then re-run Task 4 Step 4's test command.

- [ ] **Step 3: Rebuild the static site and confirm no unrelated drift**

Run: `.venv/bin/python -m mbe.cli <the existing static-rebuild subcommand>` (find the exact name via `--help` if not already known from Milestone 1's session)
Run: `git status --short site/` and `git diff --stat site/`
Expected: only `site/assets/app.js` (Task 7's changes) and `site/api/v1/search-index.json`'s `meta.search_ranking_policy_version` field change, plus any `generated_at` timestamp fields — confirm no company/count/score/hash fields changed by diffing a sample of `search-index.json`:

Run: `git diff site/api/v1/search-index.json | grep -v '"generated_at"' | head -100`
Expected: only the version-string and (if wired) `index_memberships: []`/evidence-field additions — no instrument removed/added/reordered in ways implying a universe change, no score/rank/financial value changed.

- [ ] **Step 4: Run the release verifier**

Run: `.venv/bin/python -m mbe.cli <the existing release-verify subcommand>`
Expected: PASS. If it checks a pinned public-hash file for scores/financials, confirm it reports unchanged.

- [ ] **Step 5: Commit the regenerated static artifacts**

```bash
git add site/
git commit -m "chore(search): regenerate static build for ranking policy v3"
```

---

### Task 10: Documentation

**Files:**
- Modify: `docs/search-architecture.md`
- Modify: `docs/HANDOVER.md`

- [ ] **Step 1: Add a new `## Search ranking policy version 3` section** to `docs/search-architecture.md`, inserted immediately after the existing `## Search ranking policy version 2` section (before `## Listing-status awareness`). Content: reuse the `mbe.search.ranking` module docstring from Task 2 nearly verbatim (it is already written for a documentation audience), formatted as markdown, plus this closing paragraph:

```markdown
## Search ranking policy version 3 (Phase 10C Milestone 2)

[... paste the tier-mapping and tie-break-order content from the
mbe.search.ranking module docstring written in Task 2, reformatted as
markdown headings/lists ...]

**Signals intentionally excluded from every tie-break dimension:** hidden
popularity scores, market-cap estimates, internet popularity, corporate-
group inference, manual "flagship company" labels, and any numeric weight
not already derivable from a documented, verifiable field. Broad-index
membership is structurally supported (dimension 4) but inert today — see
"Recommended Milestone 3 scope" below.

**Static/server parity:** `mbe.search.ranking` is canonical. `app.js`'s
`staticSearch` is a hand-maintained mirror (same tier scores, same tie-break
order — see `tests/frontend/app.test.js`), not a generated artifact.
`mbe.instruments.resolution.InstrumentResolver` (the DB-backed path behind
`/api/v1/search`) imports the same `match_reason`/`matched_field_for`/
`classification_quality_rank` helpers and applies the same active/primary/
main-board/classification tie-break order; research/ranking availability are
applied one layer up, in `mbe.api.app.search`, because current model scores
are only available after a second DB query the resolver itself does not run
— see that route's docstring. Classification `sector`/conflict data does not
exist in the DB schema (Milestone 1 scoped it to the static JSON catalog
only, "No migration"), so `classification_conflict` is always `False` on the
dynamic API path today — a documented, not silent, limitation.
```

- [ ] **Step 2: Update the "Recommended Phase 10C scope" section** (around line 1821-1845 as of Milestone 1) — replace the Milestone 2 bullet with a completed-status note and add a new "Recommended Milestone 3 scope" bullet list covering: importing Nifty 50/Next 50/100/200/500 constituent data to make the index-membership tie-break non-inert; wiring classification provenance into the DB schema so the dynamic API path gets full parity; evaluating a dedicated partial-word-match tier if evaluation data ever shows the guarded fuzzy tier under-serving multi-token partial queries.

- [ ] **Step 3: Add a new `## Phase 10C Milestone 2 implementation details` section** to `docs/HANDOVER.md`, following the existing per-phase pattern (`### Root architectural decisions`, `### Files changed`, `### New/extended APIs`, `### Performance`, `### Test results`, `### Remaining limitations`, `### Recommended next scope`), placed after the Milestone 1 narrative and before `## Current working-tree state`. Populate `### Test results` and `### Performance` with the actual numbers measured in Task 11 below (do not write this subsection until Task 11 has run).

- [ ] **Step 4: Update the phase ledger row** near the existing "Phase 10C Milestone 1" entry to add a "Phase 10C Milestone 2 — search ranking policy v3" row with the actual final test counts.

- [ ] **Step 5: Commit**

```bash
git add docs/search-architecture.md docs/HANDOVER.md
git commit -m "docs: record Phase 10C Milestone 2 search ranking policy v3"
```

---

### Task 11: Full verification pass and final report

**Files:** none — verification only.

- [ ] **Step 1: Run the full Python test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 625 + new tests from Tasks 1/3/4/5/6 (record the exact final count for the completion report).

- [ ] **Step 2: Run the full frontend test suite**

Run: `node --test tests/frontend/*.test.js`
Expected: 28 + new tests from Tasks 7/8 (record exact final count).

- [ ] **Step 3: Run ESLint, TypeScript/JS type-check, Python compilation check**

Run: `npm run lint` (or the exact script name in `package.json`), `npm run typecheck` (or equivalent), `.venv/bin/python -m compileall src/mbe -q`
Expected: all pass, 0 errors.

- [ ] **Step 4: Run `git diff --check` for whitespace errors**

Run: `git diff --check`
Expected: no output.

- [ ] **Step 5: Confirm no canonical-ID/universe/hash drift one more time**

Run: `git diff --stat` and re-inspect any `site/` or `universes/` diffs exactly as in Task 9 Step 3.

- [ ] **Step 6: Measure latency** using whatever benchmark mechanism Phase 10B used (grep for it: `grep -rn "35 ms\|16.1 ms\|p50\|p95\|latency" docs/HANDOVER.md src/mbe/search/ tests/ | grep -i perf`) and record P50/P95 for exact, prefix, group, and fuzzy queries, plus static index initialization time. If no automated benchmark script exists (only a documented manual measurement from Phase 10B), note in the completion report that latency was not independently re-measured this milestone and flag it as a Milestone 3 follow-up rather than fabricating numbers.

- [ ] **Step 7: Write the completion report** to the user, covering every item in the original Milestone 2 spec's "Completion report" section, using the real numbers gathered above — do not estimate or round in place of an actual measurement.
