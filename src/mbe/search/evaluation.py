"""Deterministic search-quality evaluation (Phase 10B).

A fixed, versioned set of representative queries — exact symbol, BSE code,
ISIN, company name, group query, short-alias collision guard, and an
unknown-company negative case — with expected top result and any forbidden
result. Intentionally spans more than the handful of famous companies used
in ad hoc regression tests, so a ranking change can't silently regress
quality outside that narrow set without a metric moving.
"""

from __future__ import annotations

from typing import Any, Callable

from mbe.search.domain import SearchIndexRecord

EVALUATION_SET: list[dict[str, Any]] = [
    {"query": "RELIANCE", "expected_first": "RELIANCE", "forbidden": []},
    {"query": "TCS", "expected_first": "TCS", "forbidden": []},
    {"query": "Infosys", "expected_first": "INFY", "forbidden": []},
    {"query": "500325", "expected_first": "RELIANCE", "forbidden": []},
    {"query": "INE002A01018", "expected_first": "RELIANCE", "forbidden": []},
    {"query": "HDFC", "expected_first": "HDFCBANK", "forbidden": []},
    {"query": "Dixon", "expected_first": "DIXON", "forbidden": []},
    {"query": "Polycab", "expected_first": "POLYCAB", "forbidden": []},
    {"query": "Bharat Electronics", "expected_first": "BEL", "forbidden": []},
    {"query": "Hindustan Aeronautics", "expected_first": "HAL", "forbidden": []},
    {"query": "BLS", "expected_first": "BLS", "forbidden": []},
    {"query": "ACE", "expected_first": "ACE", "forbidden": []},
    {"query": "VIJAYA", "expected_first": "VIJAYA", "forbidden": []},
    {"query": "Reliance Power", "expected_first": "RPOWER", "forbidden": []},
    {"query": "Tata Consultancy Services", "expected_first": "TCS", "forbidden": []},
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
    accuracy, false positives and a per-query breakdown for diagnosis."""
    per_query = []
    top1_hits = 0
    topn_hits = 0
    false_positives = 0
    for case in evaluation_set:
        results = ranker(case["query"], index)
        symbols = [r.record.symbol for r in results]
        expected = case.get("expected_first")
        forbidden = case.get("forbidden") or []
        top1_ok = (symbols[0] if symbols else None) == expected
        topn_ok = expected is None or expected in symbols[:top_k]
        hit_forbidden = [s for s in symbols if s in forbidden]
        if top1_ok:
            top1_hits += 1
        if topn_ok:
            topn_hits += 1
        if hit_forbidden:
            false_positives += 1
        per_query.append({
            "query": case["query"], "expected_first": expected,
            "actual_first": symbols[0] if symbols else None,
            "top_results": symbols[:top_k], "passed": top1_ok and not hit_forbidden,
        })
    total = len(evaluation_set)
    return {
        "total": total,
        "top1_accuracy": round(top1_hits / total, 4) if total else 0.0,
        "top3_recall": round(topn_hits / total, 4) if total else 0.0,
        "false_positive_count": false_positives,
        "per_query": per_query,
    }
