import pytest

from mbe.analysis.business import assess_business
from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.stewardship import assess_stewardship, debt_ebit_gap, dilution_track
from mbe.models.company import CompanyInfo, FinancialHistory
from tests.test_business import _compounder

YEARS = list(range(2017, 2025))


def _profile(fin: FinancialHistory):
    info = CompanyInfo(ticker="T.NS")
    fund = compute_fundamentals(fin, info)
    business = assess_business(fin, info, fund)
    return assess_stewardship(fin, info, fund, business)


def test_dilution_track_anchors():
    # 100 -> 100 -> 103 -> 103 -> 100 over 5 years: one >2% dilution year,
    # one buyback year, ~0% full CAGR
    fin = FinancialHistory(
        data={"shares_diluted": dict(zip(range(2020, 2025), [100, 100, 103, 103, 100.0]))}
    )
    track = dilution_track(fin)
    assert track["share_cagr_full"] == pytest.approx(0.0, abs=1e-9)
    assert track["dilution_years_frac"] == pytest.approx(1 / 4)
    assert track["buyback_years_frac"] == pytest.approx(1 / 4)


def test_debt_ebit_gap_anchor():
    fin = FinancialHistory(
        data={
            "total_debt": {2020: 100.0, 2024: 200.0},   # +18.92%/yr
            "operating_income": {2020: 50.0, 2024: 60.0},  # +4.66%/yr
        }
    )
    gap = debt_ebit_gap(fin)
    assert gap == pytest.approx((2.0 ** 0.25 - 1) - (1.2 ** 0.25 - 1), abs=1e-6)


def test_clean_compounder_is_owner_operator():
    prof = _profile(_compounder())
    assert prof.classification == "Owner-Operator Discipline"
    assert prof.stewardship_score >= 75
    assert prof.evidence


def test_serial_diluter_flagged():
    rev = [100 * 1.25 ** i for i in range(8)]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(YEARS, rev)),
            "operating_income": dict(zip(YEARS, [r * 0.10 for r in rev])),
            "net_income": dict(zip(YEARS, [r * 0.05 for r in rev])),
            "total_equity": dict(zip(YEARS, [50 * 1.3 ** i for i in range(8)])),
            "total_debt": dict(zip(YEARS, [30] * 8)),
            "cash": dict(zip(YEARS, [10] * 8)),
            # shares compound at 12%/yr — persistent dilution
            "shares_diluted": dict(zip(YEARS, [100 * 1.12 ** i for i in range(8)])),
        }
    )
    prof = _profile(fin)
    assert prof.classification == "Serial Diluter"
    assert prof.stewardship_score < 50


def test_empire_builder_flagged():
    # heavy reinvestment at terrible incremental returns, debt outgrowing EBIT
    rev = [200 + 10 * i for i in range(8)]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(YEARS, rev)),
            "operating_income": dict(zip(YEARS, [30 + 0.5 * i for i in range(8)])),
            "net_income": dict(zip(YEARS, [15 + 0.2 * i for i in range(8)])),
            "total_equity": dict(zip(YEARS, [100 + 30 * i for i in range(8)])),
            "total_debt": dict(zip(YEARS, [50 * 1.25 ** i for i in range(8)])),
            "cash": dict(zip(YEARS, [10] * 8)),
            "cfo": dict(zip(YEARS, [25 + i for i in range(8)])),
            "capex": dict(zip(YEARS, [20 + i for i in range(8)])),  # ~80% of CFO
            "shares_diluted": dict(zip(YEARS, [100] * 8)),
        }
    )
    prof = _profile(fin)
    assert prof.classification == "Empire Builder"
    assert prof.allocation_fit_label.startswith("empire")


def test_short_history_unproven():
    fin = FinancialHistory(
        data={"revenue": {2023: 10.0, 2024: 12.0}, "shares_diluted": {2023: 5.0, 2024: 5.0}}
    )
    assert _profile(fin).classification == "Unproven"
