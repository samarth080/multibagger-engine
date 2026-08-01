from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from mbe.db.base import Base
from mbe.db.models import CompanyRow, FinancialFactRow, FinancialFilingRow, InstrumentRow
from mbe.financials.domain import ConsolidationBasis, FilingInput, FinancialPeriod, SourceFact
from mbe.financials.importer import import_filings
from mbe.financials.metrics import FINANCIAL_METRICS, cagr, ratio
from mbe.financials.normalization import annual_period, choose_basis, derive_quarter_from_ytd, derive_ttm, normalize_decimal
from mbe.financials.projection import financial_build, project_history
from mbe.financials.quality import freshness, validate_filing
from mbe.models.company import FinancialHistory


@pytest.mark.parametrize(("unit", "expected"), [
    ("INR", "2.5"), ("thousand_inr", "2500"), ("lakh_inr", "250000"),
    ("million_inr", "2500000"), ("crore_inr", "25000000"),
])
def test_decimal_unit_normalization(unit, expected):
    value, _ = normalize_decimal("2.5", unit)
    assert value == Decimal(expected)


def test_unit_normalization_preserves_negative_precision_and_rejects_unknown():
    assert normalize_decimal("-1.23456789", "crore_inr")[0] == Decimal("-12345678.90000000")
    with pytest.raises(ValueError):
        normalize_decimal("1", "mystery")


def test_period_and_basis_semantics():
    period = annual_period(2025)
    assert period.period_start == date(2024, 4, 1) and period.period_end == date(2025, 3, 31)
    assert choose_basis({ConsolidationBasis.STANDALONE, ConsolidationBasis.CONSOLIDATED}) == ConsolidationBasis.CONSOLIDATED
    with pytest.raises(ValueError):
        FinancialPeriod(period_type="annual", fiscal_year=2025, period_start=date(2025, 4, 1), period_end=date(2025, 3, 31))


def _ytd(value, quarter, end):
    return SourceFact(source_field="Revenue", metric_id="revenue", value=Decimal(value), unit="INR", currency="INR",
        basis="consolidated", source_location=f"q{quarter}", period=FinancialPeriod(
            period_type="year_to_date", fiscal_year=2025, fiscal_quarter=quarter,
            period_start=date(2024, 4, 1), period_end=end, duration_days=(end-date(2024,4,1)).days+1))


def test_quarter_derivation_and_ttm_require_compatible_sequential_periods():
    q1 = _ytd("100", 1, date(2024, 6, 30)); q2 = _ytd("230", 2, date(2024, 9, 30))
    assert derive_quarter_from_ytd(q2, q1).value == Decimal("130")
    quarters = []
    periods = ((date(2024,1,1),date(2024,3,31)),(date(2024,4,1),date(2024,6,30)),(date(2024,7,1),date(2024,9,30)),(date(2024,10,1),date(2024,12,31)))
    for i, (start, end) in enumerate(periods, 1):
        quarters.append(SourceFact(source_field="Revenue", metric_id="revenue", value=Decimal(i*10), unit="INR", currency="INR", basis="consolidated", source_location=f"x{i}", period=FinancialPeriod(period_type="quarter", fiscal_year=2025, fiscal_quarter=i, period_start=start, period_end=end, duration_days=(end-start).days+1)))
    assert derive_ttm(quarters).value == Decimal("100")
    with pytest.raises(ValueError):
        derive_ttm(quarters[:3])


def test_metric_dictionary_and_derived_denominator_rules():
    assert all(item.description and item.version and item.period_types for item in FINANCIAL_METRICS.values())
    assert float(cagr(Decimal("100"), Decimal("133.1"), 3)) == pytest.approx(.1)
    assert cagr(Decimal("0"), Decimal("1"), 3) is None
    assert ratio(Decimal("2"), Decimal("0")) is None
    assert ratio(Decimal("2"), Decimal("-1"), require_positive_denominator=True) is None


def _filing(raw_hash="a"*64, source_id="filing-1", revision=1, restates=None):
    period = annual_period(2025)
    return FilingInput(source_code="nse_results", source_filing_id=source_id,
        company_id="company", instrument_id="instrument", filing_type="annual_results",
        period=period, basis="consolidated", currency="INR", original_unit="crore_inr",
        filing_date=date(2025, 5, 20), publication_timestamp=datetime(2025,5,20,tzinfo=timezone.utc),
        audited_status="audited", revision_number=revision, restates_source_filing_id=restates,
        retrieved_at=datetime(2025,5,21,tzinfo=timezone.utc), raw_payload_hash=raw_hash,
        facts=[SourceFact(source_field="RevenueFromOperations", metric_id="revenue",
            value=Decimal("123.45"), unit="crore_inr", currency="INR", period=period,
            basis="consolidated", source_location="xbrl:RevenueFromOperations")])


def _store():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(CompanyRow(company_id="company", display_name="Test", country="IN"))
        session.add(InstrumentRow(instrument_id="instrument", company_id="company", security_type="equity", country="IN", currency="INR", timezone="Asia/Kolkata", quality_status="valid"))
        session.commit()
    return engine


def test_import_is_idempotent_decimal_safe_and_dry_run_rolls_back():
    engine = _store()
    with Session(engine) as session:
        first = import_filings(session, [_filing()])
    assert first.filings_created == 1 and first.facts_normalized == 1
    with Session(engine) as session:
        second = import_filings(session, [_filing()])
        assert second.filings_unchanged == 1 and second.facts_unchanged == 1
        assert session.scalar(select(FinancialFactRow.normalized_value)) == Decimal("1234500000.00000000")
    with Session(engine) as session:
        summary = import_filings(session, [_filing(source_id="dry")], dry_run=True)
        assert summary.filings_created == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(FinancialFilingRow)) == 1


def test_restatement_preserves_original_and_links_revision():
    engine = _store()
    with Session(engine) as session:
        import_filings(session, [_filing()])
    with Session(engine) as session:
        revised = import_filings(session, [_filing(raw_hash="b"*64, source_id="filing-2", revision=2, restates="filing-1")])
        assert revised.restatements_detected == 1
    with Session(engine) as session:
        rows = session.scalars(select(FinancialFilingRow).order_by(FinancialFilingRow.revision_number)).all()
        assert len(rows) == 2 and rows[0].quality_status == "superseded" and rows[1].restates_filing_id == rows[0].filing_id


def test_quality_and_freshness_warn_without_treating_zero_as_missing():
    filing = _filing().model_copy(update={"basis": ConsolidationBasis.UNKNOWN})
    assert {issue.code for issue in validate_filing(filing)} == {"unknown_basis"}
    assert freshness(date(2025,3,31), as_of=date(2026,8,1))[0] == "current"


def test_static_projection_keeps_lineage_and_deterministic_build_id():
    fin = FinancialHistory(data={"revenue": {2021:100, 2024:133.1},
        "operating_income": {2023:20, 2024:22}, "total_equity": {2023:60,2024:70},
        "total_debt": {2023:40,2024:40}})
    cutoff = datetime(2026,8,1,tzinfo=timezone.utc)
    projection = project_history(fin, instrument_id="instrument", cutoff=cutoff)
    assert projection["values"]["revenue_cagr_3y"] == pytest.approx(.1)
    assert projection["basis"] == "unknown" and projection["quality_warnings"]
    assert financial_build([projection], cutoff=cutoff)["financial_dataset_build_id"] == financial_build([projection], cutoff=cutoff)["financial_dataset_build_id"]
