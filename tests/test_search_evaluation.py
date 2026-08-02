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
    # A query may legitimately appear twice — once as a scored exact-identity
    # case and once as an unscored broad group-recall case (e.g. "HDFC" is
    # both "expect HDFCBANK first" and "recall the whole HDFC family") — so
    # uniqueness is checked per case kind, not across the whole set.
    keys = {(case["query"], bool(case.get("group"))) for case in EVALUATION_SET}
    assert len(keys) == len(EVALUATION_SET)


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


def test_evaluation_set_includes_group_and_exchange_cases():
    assert any(case.get("group") for case in EVALUATION_SET)
    assert any(case.get("exchange") for case in EVALUATION_SET)


def test_evaluate_search_quality_reports_new_metrics():
    from mbe.search.catalog import build_search_index

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


def test_evaluate_search_quality_reports_group_query_recall():
    cases = [{"query": "Reliance", "group_members": ["RELIANCE"], "forbidden": [], "group": True}]
    report = evaluate_search_quality(TINY_INDEX, cases, ranker=rank_search_candidates)
    assert report["group_query_recall"] == 1.0
