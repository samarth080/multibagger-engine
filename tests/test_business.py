import pytest

from mbe.analysis.business import (
    assess_business,
    coefficient_of_variation,
    incremental_roic,
    ols_slope,
    worst_drawdown,
)
from mbe.analysis.fundamentals import compute_fundamentals
from mbe.models.company import CompanyInfo, FinancialHistory


# ---- pure helpers, exact hand-computed anchors ----

def test_coefficient_of_variation():
    assert coefficient_of_variation([0.16, 0.16, 0.16]) == pytest.approx(0.0)
    assert coefficient_of_variation([0.10, 0.20]) == pytest.approx(0.05 / 0.15)


def test_worst_drawdown():
    assert worst_drawdown([100, 120, 90, 130]) == pytest.approx(-0.25)
    assert worst_drawdown([100, 110, 121]) == pytest.approx(0.0)  # monotone up
    assert worst_drawdown([50]) == pytest.approx(0.0)


def test_ols_slope():
    assert ols_slope([(0, 0.10), (1, 0.12), (2, 0.14)]) == pytest.approx(0.02)
    assert ols_slope([(0, 0.15), (1, 0.15)]) == pytest.approx(0.0)


# ---- fixtures ----

COMPOUNDER_YEARS = list(range(2017, 2025))  # 8 years


def _compounder() -> FinancialHistory:
    rev = [100, 115, 132, 152, 175, 200, 230, 265]
    return FinancialHistory(
        data={
            "revenue": dict(zip(COMPOUNDER_YEARS, rev)),
            "operating_income": dict(zip(COMPOUNDER_YEARS, [round(r * 0.20) for r in rev])),
            "ebitda": dict(zip(COMPOUNDER_YEARS, [round(r * 0.26) for r in rev])),
            "net_income": dict(zip(COMPOUNDER_YEARS, [round(r * 0.13) for r in rev])),
            "total_equity": dict(zip(COMPOUNDER_YEARS, [60, 70, 82, 96, 112, 130, 150, 173])),
            "total_debt": dict(zip(COMPOUNDER_YEARS, [40] * 8)),
            "cash": dict(zip(COMPOUNDER_YEARS, [10, 12, 14, 16, 18, 20, 23, 26])),
            "cfo": dict(zip(COMPOUNDER_YEARS, [round(r * 0.15) for r in rev])),
            "capex": dict(zip(COMPOUNDER_YEARS, [round(r * 0.05) for r in rev])),
            "shares_diluted": dict(zip(COMPOUNDER_YEARS, [100] * 8)),
        }
    )


def test_incremental_roic_anchor():
    fin = FinancialHistory(
        data={
            "operating_income": {2020: 15.0, 2024: 33.0},
            "total_equity": {2020: 60.0, 2024: 130.0},
            "total_debt": {2020: 40.0, 2024: 40.0},
            "cash": {2020: 10.0, 2024: 20.0},
        }
    )
    # ΔEBIT·(1-0.25) / ΔInvestedCapital = 18*0.75 / (150-90) = 13.5/60
    assert incremental_roic(fin) == pytest.approx(0.225)


def test_incremental_roic_none_when_capital_shrinks():
    fin = FinancialHistory(
        data={
            "operating_income": {2020: 15.0, 2024: 33.0},
            "total_equity": {2020: 130.0, 2024: 60.0},
            "total_debt": {2020: 40.0, 2024: 40.0},
            "cash": {2020: 20.0, 2024: 10.0},
        }
    )
    assert incremental_roic(fin) is None


def test_business_profile_compounder():
    fin = _compounder()
    info = CompanyInfo(ticker="COMP.NS")
    fund = compute_fundamentals(fin, info)
    prof = assess_business(fin, info, fund)

    assert prof.history_years == 8
    assert prof.growth_positive_years == pytest.approx(1.0)  # every YoY positive
    assert prof.margin_stability == pytest.approx(1.0, abs=0.03)  # ~constant 20% margin
    assert prof.ever_lossmaking is False
    assert prof.worst_revenue_drawdown == pytest.approx(0.0)
    assert prof.classification == "Durable Compounder"
    assert prof.franchise_score >= 70
    assert prof.evidence, "franchise score must carry evidence"


def test_business_profile_short_history_is_unproven():
    fin = FinancialHistory(
        data={
            "revenue": {2023: 100.0, 2024: 130.0},
            "operating_income": {2023: 20.0, 2024: 26.0},
            "total_equity": {2023: 60.0, 2024: 70.0},
            "total_debt": {2023: 40.0, 2024: 40.0},
        }
    )
    info = CompanyInfo(ticker="NEW.NS")
    fund = compute_fundamentals(fin, info)
    prof = assess_business(fin, info, fund)
    assert prof.classification == "Unproven"


def test_business_profile_deteriorating():
    years = list(range(2017, 2025))
    rev = [200, 205, 210, 208, 205, 200, 195, 190]  # stagnant/declining
    op = [40, 38, 35, 30, 26, 22, 18, 14]  # margins collapsing
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, rev)),
            "operating_income": dict(zip(years, op)),
            "net_income": dict(zip(years, [round(o * 0.6) for o in op])),
            "total_equity": dict(zip(years, [100] * 8)),
            "total_debt": dict(zip(years, [80] * 8)),
            "cash": dict(zip(years, [5] * 8)),
        }
    )
    info = CompanyInfo(ticker="DECL.NS")
    fund = compute_fundamentals(fin, info)
    prof = assess_business(fin, info, fund)
    assert prof.margin_trajectory < 0
    assert prof.classification == "Deteriorating"
    assert prof.franchise_score < 55


def test_completeness_never_exceeds_one_with_trajectory_row():
    """A full-data company with a margin trajectory adds an adjustment evidence
    row; completeness must still be bounded at 1.0 (was a latent overflow)."""
    years = list(range(2016, 2025))
    rev = [100 + 15 * i for i in range(9)]
    op = [round(r * (0.14 + 0.01 * i)) for i, r in enumerate(rev)]  # expanding margins
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, rev)),
            "operating_income": dict(zip(years, op)),
            "net_income": dict(zip(years, [round(o * 0.7) for o in op])),
            "total_equity": dict(zip(years, [60 + 12 * i for i in range(9)])),
            "total_debt": dict(zip(years, [40] * 9)),
            "cash": dict(zip(years, [10 + i for i in range(9)])),
            "cfo": dict(zip(years, [round(o * 1.1) for o in op])),
        }
    )
    info = CompanyInfo(ticker="FULL.NS")
    fund = compute_fundamentals(fin, info)
    prof = assess_business(fin, info, fund)
    assert 0 <= prof.completeness <= 1.0
    assert prof.margin_trajectory > 0
    assert any(e.metric == "trajectory_adjustment" for e in prof.evidence)


def test_elite_compounder_with_expanding_margins_stays_bounded():
    """TCS-shaped bug: a near-perfect franchise x expanding-margin multiplier
    pushed points/score above 100 and crashed pydantic validation."""
    years = list(range(2016, 2025))
    rev = [100 * 1.12 ** i for i in range(9)]
    op = [r * (0.24 + 0.004 * i) for i, r in enumerate(rev)]  # high + expanding
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, rev)),
            "operating_income": dict(zip(years, op)),
            "net_income": dict(zip(years, [o * 0.75 for o in op])),
            "total_equity": dict(zip(years, [40 + 8 * i for i in range(9)])),
            "total_debt": dict(zip(years, [2] * 9)),
            "cash": dict(zip(years, [10 + 2 * i for i in range(9)])),
            "cfo": dict(zip(years, [o * 0.95 for o in op])),
        }
    )
    info = CompanyInfo(ticker="ELITE.NS")
    fund = compute_fundamentals(fin, info)
    prof = assess_business(fin, info, fund)  # must not raise
    assert 0 <= prof.franchise_score <= 100
    assert all(0 <= e.points <= 100 for e in prof.evidence)
    assert prof.classification == "Durable Compounder"
