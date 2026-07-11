import pytest

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.valuation import compute_valuation, dcf_value, solve_implied_growth
from mbe.models.company import CompanyInfo, FinancialHistory


def _expected_dcf(base_fcf, g1, discount, terminal, years_stage1=5, years_total=10):
    """Independent hand-loop mirror of the DCF definition in the spec."""
    pv = 0.0
    fcf = base_fcf
    for t in range(1, years_total + 1):
        g = g1 if t <= years_stage1 else g1 / 2
        fcf = fcf * (1 + g)
        pv += fcf / (1 + discount) ** t
    tv = fcf * (1 + terminal) / (discount - terminal)
    pv += tv / (1 + discount) ** years_total
    return pv


def test_dcf_matches_hand_loop():
    got = dcf_value(base_fcf=100.0, g1=0.10, discount=0.13, terminal=0.04)
    assert got == pytest.approx(_expected_dcf(100.0, 0.10, 0.13, 0.04), rel=1e-9)


def test_reverse_dcf_recovers_growth():
    market_value = dcf_value(100.0, g1=0.15, discount=0.13, terminal=0.04)
    implied = solve_implied_growth(100.0, market_value, discount=0.13, terminal=0.04)
    assert implied == pytest.approx(0.15, abs=0.002)


@pytest.fixture
def bundle():
    years = [2021, 2022, 2023, 2024]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, [100.0, 120.0, 144.0, 172.8])),
            "net_income": dict(zip(years, [10.0, 12.5, 15.6, 19.5])),
            "operating_income": dict(zip(years, [14.0, 17.0, 21.0, 26.0])),
            "ebitda": dict(zip(years, [18.0, 22.0, 27.0, 33.0])),
            "total_equity": dict(zip(years, [50.0, 60.0, 72.0, 87.0])),
            "total_debt": dict(zip(years, [20.0, 20.0, 20.0, 20.0])),
            "cash": dict(zip(years, [30.0, 32.0, 35.0, 40.0])),
            "cfo": dict(zip(years, [12.0, 15.0, 19.0, 24.0])),
            "capex": dict(zip(years, [4.0, 5.0, 6.0, 7.0])),
            "fcf": dict(zip(years, [8.0, 10.0, 13.0, 17.0])),
            "shares_diluted": dict(zip(years, [10.0, 10.0, 10.0, 10.0])),
        }
    )
    info = CompanyInfo(
        ticker="TEST.NS", market_cap=400.0, shares_outstanding=10.0, price=40.0
    )
    fund = compute_fundamentals(fin, info)
    return fin, info, fund


def test_relative_multiples(bundle):
    fin, info, fund = bundle
    v = compute_valuation(fin, info, fund, price=40.0)
    assert v.pe == pytest.approx(400.0 / 19.5)
    assert v.ev_ebitda == pytest.approx((400.0 + 20.0 - 40.0) / 33.0)
    assert v.price_to_sales == pytest.approx(400.0 / 172.8)
    assert v.fcf_yield == pytest.approx(17.0 / 400.0)
    # profit 3y cagr = (19.5/10)^(1/3)-1 ~ 24.93%
    assert v.peg == pytest.approx((400.0 / 19.5) / 24.93, abs=0.05)


def test_dcf_scenarios_ordered_and_mos_consistent(bundle):
    fin, info, fund = bundle
    v = compute_valuation(fin, info, fund, price=40.0)
    assert v.fair_value_bear < v.fair_value_base < v.fair_value_bull
    assert v.margin_of_safety == pytest.approx(v.fair_value_base / 40.0 - 1)
    assert v.implied_growth is not None
    assert not v.fcf_proxy_used
    assert v.assumptions["discount"] == pytest.approx(0.13)  # .NS -> India
    assert v.assumptions["terminal"] == pytest.approx(0.04)


def test_negative_fcf_uses_ni_proxy():
    years = [2022, 2023, 2024]
    fin = FinancialHistory(
        data={
            "net_income": dict(zip(years, [10.0, 12.0, 15.0])),
            "fcf": dict(zip(years, [-5.0, -3.0, -2.0])),
            "shares_diluted": dict(zip(years, [10.0, 10.0, 10.0])),
        }
    )
    info = CompanyInfo(ticker="X.NS", market_cap=300.0, shares_outstanding=10.0)
    fund = compute_fundamentals(fin, info)
    v = compute_valuation(fin, info, fund, price=30.0)
    assert v.fcf_proxy_used
    assert v.fair_value_base is not None


def test_no_earnings_no_dcf_no_crash():
    fin = FinancialHistory(
        data={"net_income": {2023: -10.0, 2024: -8.0}, "fcf": {2023: -5.0, 2024: -4.0}}
    )
    info = CompanyInfo(ticker="X.NS", market_cap=100.0, shares_outstanding=10.0)
    fund = compute_fundamentals(fin, info)
    v = compute_valuation(fin, info, fund, price=10.0)
    assert v.fair_value_base is None
    assert v.margin_of_safety is None
    assert v.completeness < 0.5


def test_owner_earnings_floor_for_capex_heavy_compounder():
    """Trailing FCF depressed by growth capex must not wreck the DCF when
    earnings are cash-backed (cash conversion >= 0.8)."""
    years = [2021, 2022, 2023, 2024]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, [500.0, 550.0, 605.0, 665.0])),
            "net_income": dict(zip(years, [80.0, 88.0, 97.0, 107.0])),
            "cfo": dict(zip(years, [100.0, 110.0, 121.0, 133.0])),
            "capex": dict(zip(years, [85.0, 95.0, 105.0, 115.0])),
            "fcf": dict(zip(years, [15.0, 15.0, 16.0, 18.0])),
            "shares_diluted": dict(zip(years, [10.0, 10.0, 10.0, 10.0])),
        }
    )
    info = CompanyInfo(ticker="CAPEX.NS", market_cap=2000.0, shares_outstanding=10.0)
    fund = compute_fundamentals(fin, info)
    assert fund.cash_conversion is not None and fund.cash_conversion >= 0.8
    v = compute_valuation(fin, info, fund, price=200.0)
    # floor = 0.7 * avg NI(88, 97, 107) = 0.7 * 97.33 = 68.13 >> avg FCF 16.33
    assert v.assumptions["base_fcf"] == pytest.approx(0.7 * (88 + 97 + 107) / 3, abs=0.01)
    assert v.assumptions["owner_earnings_floor"] == 1.0


def test_owner_earnings_floor_skipped_when_earnings_not_cash_backed():
    years = [2021, 2022, 2023, 2024]
    fin = FinancialHistory(
        data={
            "net_income": dict(zip(years, [80.0, 88.0, 97.0, 107.0])),
            "cfo": dict(zip(years, [30.0, 33.0, 36.0, 40.0])),  # conversion ~0.37
            "fcf": dict(zip(years, [15.0, 15.0, 16.0, 18.0])),
            "shares_diluted": dict(zip(years, [10.0, 10.0, 10.0, 10.0])),
        }
    )
    info = CompanyInfo(ticker="ACCRUAL.NS", market_cap=2000.0, shares_outstanding=10.0)
    fund = compute_fundamentals(fin, info)
    v = compute_valuation(fin, info, fund, price=200.0)
    assert v.assumptions["base_fcf"] == pytest.approx((15 + 16 + 18) / 3, abs=0.01)
    assert v.assumptions["owner_earnings_floor"] == 0.0
