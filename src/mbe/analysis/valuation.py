"""Valuation engine: scenario DCF, reverse DCF, relative multiples.

Model choices (v0.1, all recorded in ValuationResult.assumptions):
- Base FCF = 3y average FCF (smooths capex cycles); latest FCF if the average
  is non-positive; 0.8 x 3y-avg net income as a flagged proxy otherwise.
- Two-stage DCF: growth g1 for years 1-5, g1/2 for years 6-10, then terminal.
- Discount rate 13% and terminal 4% for Indian listings (.NS/.BO);
  10% / 3% otherwise. Crude cost-of-equity proxies, deliberately explicit.
- Base growth = median of delivered 3y revenue/profit/FCF CAGRs, capped at
  25% (base) / 35% (bull). If no growth history exists, a conservative 5%
  default is used and recorded in assumptions.
"""

from __future__ import annotations

import statistics

from mbe.models.analysis import FundamentalMetrics
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.analysis import ValuationResult

STAGE1_YEARS = 5
TOTAL_YEARS = 10
DEFAULT_GROWTH = 0.05


def dcf_value(base_fcf: float, g1: float, discount: float, terminal: float) -> float:
    """Enterprise value of a two-stage FCF stream (g1 for 5y, g1/2 for 5y, then terminal)."""
    pv = 0.0
    fcf = base_fcf
    for t in range(1, TOTAL_YEARS + 1):
        g = g1 if t <= STAGE1_YEARS else g1 / 2
        fcf *= 1 + g
        pv += fcf / (1 + discount) ** t
    terminal_value = fcf * (1 + terminal) / (discount - terminal)
    return pv + terminal_value / (1 + discount) ** TOTAL_YEARS


def solve_implied_growth(
    base_fcf: float,
    market_value: float,
    discount: float,
    terminal: float,
    lo: float = -0.20,
    hi: float = 0.60,
) -> float | None:
    """Growth rate the market is pricing in (bisection; DCF is monotonic in g)."""
    if base_fcf <= 0 or market_value <= 0:
        return None
    if dcf_value(base_fcf, hi, discount, terminal) < market_value:
        return hi
    if dcf_value(base_fcf, lo, discount, terminal) > market_value:
        return lo
    for _ in range(60):
        mid = (lo + hi) / 2
        if dcf_value(base_fcf, mid, discount, terminal) < market_value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _avg_last3(fin: FinancialHistory, field: str) -> float | None:
    vals = [v for _, v in fin.series(field)[-3:]]
    return sum(vals) / len(vals) if vals else None


def _base_fcf(fin: FinancialHistory) -> tuple[float | None, bool]:
    """Returns (base_fcf, proxy_used)."""
    avg_fcf = _avg_last3(fin, "fcf")
    if avg_fcf is not None and avg_fcf > 0:
        return avg_fcf, False
    latest_fcf = fin.latest("fcf")
    if latest_fcf is not None and latest_fcf > 0:
        return latest_fcf, False
    avg_ni = _avg_last3(fin, "net_income")
    if avg_ni is not None and avg_ni > 0:
        return 0.8 * avg_ni, True
    return None, False


def compute_valuation(
    fin: FinancialHistory,
    info: CompanyInfo,
    fund: FundamentalMetrics,
    price: float,
) -> ValuationResult:
    is_india = info.ticker.endswith((".NS", ".BO"))
    discount = 0.13 if is_india else 0.10
    terminal = 0.04 if is_india else 0.03

    shares = info.shares_outstanding or fin.latest("shares_diluted")
    market_cap = info.market_cap
    if market_cap is None and shares and price:
        market_cap = shares * price

    debt = fin.latest("total_debt")
    cash = fin.latest("cash")
    net_cash = (cash - debt) if (cash is not None and debt is not None) else 0.0

    growth_signals = [
        g
        for g in (fund.revenue_cagr_3y, fund.profit_cagr_3y, fund.fcf_cagr_3y)
        if g is not None
    ]
    if growth_signals:
        g_base = min(max(statistics.median(growth_signals), 0.0), 0.25)
        growth_defaulted = 0.0
    else:
        g_base = DEFAULT_GROWTH
        growth_defaulted = 1.0
    g_bear = g_base * 0.6
    g_bull = min(g_base * 1.2, 0.35)

    base_fcf, proxy_used = _base_fcf(fin)

    # Owner-earnings floor: heavy growth capex depresses trailing FCF and
    # would wreck the DCF for reinvestment-phase compounders. When earnings
    # are cash-backed (cash conversion >= 0.8), floor base FCF at 0.7 x avg NI.
    owner_earnings_floor = 0.0
    if fund.cash_conversion is not None and fund.cash_conversion >= 0.8:
        avg_ni = _avg_last3(fin, "net_income")
        if avg_ni is not None and avg_ni > 0:
            floor = 0.7 * avg_ni
            if base_fcf is None or floor > base_fcf:
                base_fcf = floor
                owner_earnings_floor = 1.0
                proxy_used = False

    fair_bear = fair_base = fair_bull = None
    implied = None
    if base_fcf is not None and shares:
        def per_share(g: float) -> float:
            return (dcf_value(base_fcf, g, discount, terminal) + net_cash) / shares

        fair_bear, fair_base, fair_bull = per_share(g_bear), per_share(g_base), per_share(g_bull)
        if market_cap:
            implied = solve_implied_growth(
                base_fcf, market_cap - net_cash, discount, terminal
            )

    mos = (fair_base / price - 1) if (fair_base is not None and price) else None
    expected = None
    if fair_base is not None and price and fair_base > 0:
        # price converges to intrinsic over 5y while the business compounds at g_base
        expected = (fair_base / price) ** (1 / 5) * (1 + g_base) - 1

    ni = fin.latest("net_income")
    ebitda = fin.latest("ebitda")
    revenue = fin.latest("revenue")
    fcf_latest = fin.latest("fcf")

    pe = (market_cap / ni) if (market_cap and ni and ni > 0) else None
    peg = None
    if pe is not None and fund.profit_cagr_3y is not None and fund.profit_cagr_3y > 0:
        peg = pe / (fund.profit_cagr_3y * 100)
    ev_ebitda = None
    if market_cap and ebitda and ebitda > 0 and debt is not None and cash is not None:
        ev_ebitda = (market_cap + debt - cash) / ebitda
    ps = (market_cap / revenue) if (market_cap and revenue and revenue > 0) else None
    fcf_yield = (fcf_latest / market_cap) if (market_cap and fcf_latest is not None) else None

    fields = [fair_base, implied, mos, expected, pe, peg, ev_ebitda, ps, fcf_yield]
    completeness = sum(1 for v in fields if v is not None) / len(fields)

    return ValuationResult(
        price=price,
        fair_value_bear=fair_bear,
        fair_value_base=fair_base,
        fair_value_bull=fair_bull,
        margin_of_safety=mos,
        implied_growth=implied,
        expected_cagr_5y=expected,
        pe=pe,
        peg=peg,
        ev_ebitda=ev_ebitda,
        price_to_sales=ps,
        fcf_yield=fcf_yield,
        fcf_proxy_used=proxy_used,
        assumptions={
            "discount": discount,
            "terminal": terminal,
            "g_bear": g_bear,
            "g_base": g_base,
            "g_bull": g_bull,
            "base_fcf": base_fcf if base_fcf is not None else float("nan"),
            "growth_defaulted": growth_defaulted,
            "owner_earnings_floor": owner_earnings_floor,
        },
        completeness=completeness,
    )
