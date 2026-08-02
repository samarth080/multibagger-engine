"""Static/server parity (Phase 10C Milestone 2): mbe.search.ranking and the
hand-maintained JS mirror (app.js's staticSearch) must agree on ordering for
the same shared fixture — see tests/frontend/app.test.js's matching test and
docs/search-architecture.md "Static/server parity"."""

import json
from pathlib import Path

from mbe.search.domain import ExchangeListing, SearchIndexRecord
from mbe.search.ranking import rank_search_candidates

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "search-ranking-parity.json").read_text()
)


def _index():
    records = []
    for row in FIXTURE["universe"]:
        records.append(SearchIndexRecord(
            instrument_id=row["instrument_id"], display_name=row["display_name"],
            legal_name=row["display_name"], symbol=row["symbol"],
            exchange=row.get("exchange", "NSE"), primary_exchange=row.get("primary_exchange", "NSE"),
            isin=row.get("isin"), bse_code=row.get("bse_code"),
            listing_status=row.get("listing_status", "active"),
            listings=[ExchangeListing(**listing) for listing in row.get("listings", [])],
            aliases=row.get("aliases", []), index_memberships=row.get("index_memberships", []),
            result_type="known", research_available=row.get("research_available", False),
            rank=row.get("rank"), report_url=f"/company/{row['instrument_id']}.html",
        ))
    return records


def test_python_ranking_matches_the_shared_parity_fixture():
    index = _index()
    for case in FIXTURE["cases"]:
        results = rank_search_candidates(case["query"], index, exchange=case.get("exchange"))
        actual_order = [r.record.instrument_id for r in results if r.record.instrument_id in case["expected_order"]]
        assert actual_order == case["expected_order"], case["query"]
