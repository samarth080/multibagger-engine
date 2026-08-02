"""Phase 10C Milestone 1: classification provenance and reconciliation.

Every sector/industry/sub-industry value must trace to one of a small,
documented set of sources and must never be inferred from a company name,
ticker, or free text. These tests exercise the pure reconciliation function
in isolation from `mbe.search.catalog` (which is covered separately in
`tests/test_search_catalog_bse.py` for end-to-end merge behavior), plus the
coverage report and the catalog-level integration.
"""

from datetime import datetime, timedelta, timezone

from mbe.search.catalog import build_search_index
from mbe.search.classification import (
    CLASSIFICATION_POLICY_VERSION,
    ClassificationRecord,
    ClassificationReviewStatus,
    ClassificationSource,
    build_classification_coverage_report,
    select_canonical,
)
from mbe.search.domain import ExchangeListing, SearchIndexRecord, SearchResultType

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _record(source, *, industry=None, sector=None, source_date=None):
    return ClassificationRecord(
        instrument_id="id-1", source=source, sector=sector, industry=industry,
        source_date=source_date, retrieved_at=NOW,
    )


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


# --- Task 1/2: select_canonical ---------------------------------------------


def test_single_exchange_record_is_selected_when_no_research_claim_exists():
    records = [_record(ClassificationSource.EXCHANGE_MASTER, industry="Refineries")]
    result = select_canonical(records, now=NOW)
    selected = next(r for r in result if r.is_selected_canonical)
    assert selected.industry == "Refineries"
    assert selected.review_status == ClassificationReviewStatus.ACCEPTED
    assert selected.selection_reason == "highest_priority_available_source:exchange_master"
    assert selected.classification_version == CLASSIFICATION_POLICY_VERSION


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
    documents the contract by asserting the model has no such field at all,
    so there is nothing for a future change to accidentally read."""
    records = [ClassificationRecord(
        instrument_id="id-2", source=ClassificationSource.EXCHANGE_MASTER,
        sector=None, industry=None, sub_industry=None, retrieved_at=NOW,
    )]
    assert not hasattr(records[0], "display_name")
    assert not hasattr(records[0], "symbol")
    result = select_canonical(records, now=NOW)
    assert result[0].review_status == ClassificationReviewStatus.MISSING


# --- Task 3: SearchIndexRecord provenance fields ----------------------------


def test_search_index_record_carries_classification_provenance_fields_with_safe_defaults():
    record = _index_record("a")
    assert record.sub_industry is None
    assert record.sub_industry_source is None
    assert record.classification_version is None
    assert record.classification_confidence is None
    assert record.classification_review_status is None
    assert record.classification_selection_reason is None
    assert record.classification_conflict is False


# --- Task 4: coverage report -------------------------------------------------


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


# --- Task 5: catalog.py integration ------------------------------------------


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
