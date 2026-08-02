"""Quality-ordered ranking over the merged search index.

Search ranking policy version 3 (Phase 10C Milestone 2,
``SEARCH_RANKING_POLICY_VERSION``) preserves the identity-first tier order of
version 2 unchanged — no primary-tier score or ordering has moved — and adds
a documented, evidence-carrying late tie break stage. Mapping from the 13
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
     that reaches the tie break already matches (or no exchange was
     requested). Kept as an explicit tie break dimension and evidence field
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
     match, since this is strictly the second-to-last tie break. Missing
     *sector* is never used here — sector coverage is 0/2,947 today and must
     not materially penalize results; only industry presence and
     conflict/review status count.
  9. Stable alphabetical order (``display_name``)
 10. Canonical instrument ID (final deterministic tie break)

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
# see the module docstring, tie break dimension 4.
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
    """Very late classification-quality tie break (Milestone 1 fields):
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
