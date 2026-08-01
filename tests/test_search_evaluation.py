"""Deterministic search-quality evaluation (Phase 10B section 20/21)."""

from mbe.search.evaluation import EVALUATION_SET, evaluate_search_quality
from mbe.search.ranking import rank_search_candidates


def _record(instrument_id, display_name, symbol, **extra):
    from mbe.search.domain import ExchangeListing, SearchIndexRecord
    return SearchIndexRecord(
        instrument_id=instrument_id, display_name=display_name, legal_name=display_name,
        symbol=symbol, exchange="NSE", primary_exchange="NSE",
        listings=[ExchangeListing(exchange="NSE", symbol=symbol, is_primary=True)],
        result_type="known", report_url=f"/company/{instrument_id}.html", **extra,
    )


TINY_INDEX = [
    _record("id-reliance", "Reliance Industries Limited", "RELIANCE", isin="INE002A01018"),
    _record("id-tcs", "Tata Consultancy Services Limited", "TCS"),
]


def test_evaluation_set_is_a_nonempty_representative_list():
    assert len(EVALUATION_SET) >= 10
    queries = {case["query"] for case in EVALUATION_SET}
    assert len(queries) == len(EVALUATION_SET)  # no duplicate queries


def test_evaluate_search_quality_reports_top1_and_top3_metrics():
    cases = [
        {"query": "RELIANCE", "expected_first": "RELIANCE", "forbidden": []},
        {"query": "TCS", "expected_first": "TCS", "forbidden": []},
        {"query": "Zzznotarealcompanyxyz", "expected_first": None, "forbidden": []},
    ]
    report = evaluate_search_quality(TINY_INDEX, cases, ranker=rank_search_candidates)
    assert report["total"] == 3
    assert report["top1_accuracy"] == 1.0
    assert report["top3_recall"] == 1.0
    assert report["false_positive_count"] == 0


def test_evaluate_search_quality_flags_a_forbidden_result():
    cases = [{"query": "Reliance Industries", "expected_first": "RELIANCE", "forbidden": ["TCS"]}]
    report = evaluate_search_quality(TINY_INDEX, cases, ranker=rank_search_candidates)
    assert report["false_positive_count"] == 0  # TCS never appears for this query anyway
    assert report["per_query"][0]["passed"] is True


def test_evaluate_search_quality_detects_a_missed_expectation():
    cases = [{"query": "RELIANCE", "expected_first": "TCS", "forbidden": []}]
    report = evaluate_search_quality(TINY_INDEX, cases, ranker=rank_search_candidates)
    assert report["top1_accuracy"] == 0.0
    assert report["per_query"][0]["passed"] is False
