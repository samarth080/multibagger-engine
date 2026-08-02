"""Deterministic search-quality evaluation (Phase 10B, extended Phase 10C
Milestone 2 with group-query, exact-identity, exchange-aware, and
collision-sensitive cases — see docs/search-architecture.md "Search-quality
evaluation")."""

from __future__ import annotations

from typing import Any, Callable

from mbe.search.domain import SearchIndexRecord
from mbe.search.ranking import parse_exchange_hint

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
    {"query": "Tata Motors", "expected_first": "TMCV", "forbidden": []},
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
    {"query": "Tata", "group_members": ["TCS", "TMCV"], "forbidden": [], "group": True},
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
        # Exchange-aware queries (e.g. "NSE:TCS", "Reliance BSE") carry the
        # hint inside the query text itself, exactly as a real user would
        # type it — parse it the same way the API/frontend layers do rather
        # than searching the literal hint-prefixed string.
        parsed_query, parsed_exchange = parse_exchange_hint(query)
        exchange = case.get("exchange") or parsed_exchange
        kwargs = {"exchange": exchange} if exchange else {}
        results = ranker(parsed_query, index, **kwargs)
        symbols = [r.record.symbol for r in results]
        forbidden = case.get("forbidden") or []
        hit_forbidden = [s for s in symbols if s in forbidden]
        if hit_forbidden:
            false_positives += 1

        if case.get("group"):
            # Group-query success means "discoverable in the returned result
            # set" (docs/search-architecture.md "Group-query behavior"), not
            # top-3 dominance — a legitimate family member may rank behind
            # an unrelated company on remainder-length alone (see "Recommended
            # Milestone 3 scope"), and that is not a false negative.
            members = case.get("group_members", [])
            group_recall_hits.append(any(m in symbols for m in members))
            per_query.append({
                "query": query, "group_members": members, "top_results": symbols[:top_k],
                "passed": any(m in symbols for m in members) and not hit_forbidden,
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
