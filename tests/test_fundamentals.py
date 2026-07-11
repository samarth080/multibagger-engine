import pytest

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.models.company import CompanyInfo, FinancialHistory

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]


def _hist(field_values: dict[str, list[float]]) -> FinancialHistory:
    return FinancialHistory(
        data={
            field: dict(zip(YEARS, values))
            for field, values in field_values.items()
        }
    )


@pytest.fixture
def compounder() -> FinancialHistory:
    """Synthetic quality compounder, all values hand-computed in assertions."""
    return _hist(
        {
            "revenue": [100, 115, 132, 152, 175, 200],
            "net_income": [10, 12, 15, 18, 22, 26],
            "operating_income": [15, 17, 20, 24, 28, 33],
            "ebitda": [20, 23, 27, 32, 37, 43],
            "gross_profit": [40, 46, 53, 61, 70, 80],
            "interest_expense": [4, 4, 4, 4, 4, 4],
            "total_assets": [300, 340, 385, 435, 490, 550],
            "total_equity": [60, 70, 82, 96, 112, 130],
            "total_debt": [40, 40, 40, 40, 40, 40],
            "cash": [10, 12, 14, 16, 18, 20],
            "current_assets": [50, 55, 60, 65, 70, 75],
            "current_liabilities": [25, 27, 29, 31, 33, 35],
            "cfo": [12, 14, 18, 22, 26, 30],
            "capex": [5, 6, 7, 8, 9, 10],
            "fcf": [7, 8, 11, 14, 17, 20],
            "shares_diluted": [100, 100, 100, 100, 100, 100],
        }
    )


def test_growth_cagrs(compounder):
    m = compute_fundamentals(compounder, CompanyInfo(ticker="T"))
    # 3y CAGR spans t-3 -> t: (200/132)^(1/3) - 1
    assert m.revenue_cagr_3y == pytest.approx((200 / 132) ** (1 / 3) - 1, abs=1e-6)
    assert m.revenue_cagr_3y == pytest.approx(0.148556, abs=1e-4)
    assert m.revenue_cagr_5y == pytest.approx(0.148698, abs=1e-4)
    assert m.profit_cagr_3y == pytest.approx(0.201326, abs=1e-4)
    assert m.profit_cagr_5y == pytest.approx(0.210593, abs=1e-4)
    assert m.fcf_cagr_3y == pytest.approx(0.220523, abs=1e-4)


def test_margins_and_trend(compounder):
    m = compute_fundamentals(compounder, CompanyInfo(ticker="T"))
    assert m.net_margin == pytest.approx(26 / 200)
    assert m.operating_margin == pytest.approx(33 / 200)
    assert m.gross_margin == pytest.approx(80 / 200)
    assert m.ebitda_margin == pytest.approx(43 / 200)
    assert m.operating_margin_3y_avg == pytest.approx(0.160965, abs=1e-4)
    assert m.margin_trend == pytest.approx(33 / 200 - 20 / 132, abs=1e-6)


def test_returns_on_capital(compounder):
    m = compute_fundamentals(compounder, CompanyInfo(ticker="T"))
    assert m.roe == pytest.approx(26 / 130)
    assert m.roe_3y == pytest.approx((18 / 96 + 22 / 112 + 26 / 130) / 3)
    assert m.roce == pytest.approx(33 / 170)
    assert m.roic == pytest.approx(33 * 0.75 / 150)


def test_balance_sheet_and_cash(compounder):
    m = compute_fundamentals(compounder, CompanyInfo(ticker="T"))
    assert m.debt_to_equity == pytest.approx(40 / 130)
    assert m.net_debt_to_ebitda == pytest.approx(20 / 43)
    assert m.interest_coverage == pytest.approx(33 / 4)
    assert m.current_ratio == pytest.approx(75 / 35)
    assert m.fcf_margin == pytest.approx(20 / 200)
    assert m.cash_conversion == pytest.approx(78 / 66)
    assert m.accruals_ratio == pytest.approx(-4 / 550)
    assert m.reinvestment_rate == pytest.approx(27 / 78)
    assert m.share_count_cagr_3y == pytest.approx(0.0)
    assert m.completeness == 1.0


def test_roce_minimal_anchor():
    fin = FinancialHistory(
        data={
            "operating_income": {2024: 20.0},
            "total_equity": {2024: 60.0},
            "total_debt": {2024: 40.0},
        }
    )
    m = compute_fundamentals(fin, CompanyInfo(ticker="T"))
    assert m.roce == pytest.approx(0.20)


def test_missing_data_propagates_none_not_errors():
    fin = FinancialHistory(data={"revenue": {2023: 100.0, 2024: 110.0}})
    m = compute_fundamentals(fin, CompanyInfo(ticker="T"))
    assert m.revenue_cagr_3y is None  # not enough history
    assert m.roce is None
    assert m.net_margin is None
    assert m.completeness < 0.3


def test_cagr_meaningless_when_start_negative():
    fin = FinancialHistory(
        data={"net_income": {2021: -5.0, 2022: 1.0, 2023: 3.0, 2024: 8.0}}
    )
    m = compute_fundamentals(fin, CompanyInfo(ticker="T"))
    assert m.profit_cagr_3y is None
