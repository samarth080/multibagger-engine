"""Quality-ordered ranking over the merged search index.

Mirrors ``mbe.instruments.resolution.InstrumentResolver`` (same tier order
and short-abbreviation protection) so Phase 0 entity-disambiguation behavior
carries over unchanged, but operates over the wider search index rather than
only DB-imported instruments.

Search ranking policy version 2 (Phase 10B) tier order, highest first:
exact symbol > exact BSE code > exact ISIN > exact company name > exact
alias > exact former name > full contiguous-phrase match > company-name
prefix > all-token match > guarded fuzzy match. Within an equal score,
bounded tie-breakers apply (see ``_TIEBREAK_KEY``): active listing beats
inactive, primary listing beats secondary, then research/ranking
availability — strictly a LATE tie-break that can only order two otherwise
equally-scored candidates, never promote a worse match tier above a better
one — then stable alphabetical/instrument-ID order.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from mbe.models.instrument import normalize_name, normalize_symbol
from mbe.search.domain import SearchCandidate, SearchIndexRecord

SEARCH_RANKING_POLICY_VERSION = "2026-08-01.10b.1"

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
            # call entirely — a bounded-candidate-generation guard per
            # docs/search-architecture.md "Performance".
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


def _tiebreak_key(candidate: SearchCandidate) -> tuple:
    record = candidate.record
    active = record.listing_status == "active"
    primary_listing = next((listing for listing in record.listings if listing.is_primary), None)
    is_primary = primary_listing.is_primary if primary_listing else True
    main_board = not bool(record.is_sme)
    return (
        -candidate.score,
        0 if active else 1,
        0 if is_primary else 1,
        0 if main_board else 1,
        0 if record.research_available else 1,
        record.display_name or "",
        record.instrument_id,
    )


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
            candidates.append(SearchCandidate(
                record=record, score=round(score, 2),
                matched_by=matched_by, matched_value=matched_value,
            ))
    candidates.sort(key=_tiebreak_key)
    return candidates[:limit]
