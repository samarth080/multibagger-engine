"""Valuation engine: scenario DCF, reverse DCF, relative multiples.

Model choices (v0.1, all recorded in ValuationResult.assumptions):
- Base FCF = latest FCF (current earning power); the 3y average only when the
  latest is non-positive; 0.8 x 3y-avg net income as a flagged proxy otherwise.
  Deliberately unsmoothed: averaging a growing level series understates it, and
  conservatism belongs in the bear scenario, not in the input all three share.
  How far the latest year stands out is recorded separately as the
  `fcf_spike_ratio` assumption (NaN when undefined) for scenario construction
  to consume; it never reduces the base itself.
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


def spike_ratio(fin: FinancialHistory, field: str) -> float | None:
    """How far the latest year of `field` stands out from its own recent past:
    latest / 3y mean, the mean including the latest year.

    A pure diagnostic. It is never used to reduce base FCF — a suspected peak
    year belongs to the bear scenario, not to an input all three scenarios
    share. Reported so that scenario construction can consume it deliberately.

    Scale: the denominator contains the numerator, so the ratio is
    3L/(a+b+L) — bounded above by 3.0, and `>= 1.5` is algebraically
    `L >= a + b`, i.e. the latest year alone out-earned the two before it
    combined. Steady compounding does not reach that bar: 25%/yr scores 1.23,
    40% scores 1.35, 60% scores 1.49, while HBLENGINE.NS's genuine step change
    scores 2.01. Excluding the latest year from the mean was considered and
    rejected for exactly this reason — it puts a steady 25% compounder at 1.54,
    so a 1.5 threshold would punish the bear case of every healthy compounder
    and could not tell a step change from ordinary growth.

    None rather than a neutral-looking 1.0 whenever the question has no honest
    answer: fewer than 3 consecutive fiscal years (a gap year means no valid
    comparison, not a skippable one), a non-positive mean to divide by, or a
    non-positive latest year — "did it spike?" is meaningless of a year that
    burned cash.
    """
    window = fin.series(field)[-3:]
    if len(window) < 3:
        return None
    years = [y for y, _ in window]
    if years != list(range(years[0], years[0] + 3)):
        return None
    values = [v for _, v in window]
    latest, mean = values[-1], sum(values) / len(values)
    if latest <= 0 or mean <= 0:
        return None
    return latest / mean


def _base_fcf(fin: FinancialHistory) -> tuple[float | None, bool]:
    """Returns (base_fcf, proxy_used).

    Current earning power, deliberately NOT a smoothed average. A trailing mean
    of a level series systematically understates a business whose cash flow is
    growing, and no averaging window can absorb a step change — measured on
    HBLENGINE.NS, every smoothing variant landed within 20% of the biased
    result. The risk that the latest year was a peak belongs to the *bear
    scenario* (see `spike_ratio`), not to a haircut applied to all three
    scenarios at once, which is what made even bull cases show downside.
    """
    latest_fcf = fin.latest("fcf")
    if latest_fcf is not None and latest_fcf > 0:
        return latest_fcf, False
    avg_fcf = _avg_last3(fin, "fcf")
    if avg_fcf is not None and avg_fcf > 0:
        return avg_fcf, False
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
    fcf_spike = spike_ratio(fin, "fcf")

    # Owner-earnings floor: growth capex heavy enough to swamp reported FCF
    # would wreck the DCF for a reinvestment-phase compounder. When earnings
    # are cash-backed (cash conversion >= 0.8), floor base FCF at 0.7 x latest
    # net income. Latest, not a 3y average: averaging a level series biases a
    # fading business upward exactly as it biases a growing one downward, and
    # this floor must not quietly reinstate the smoothing that base FCF above
    # deliberately removed.
    owner_earnings_floor = 0.0
    if fund.cash_conversion is not None and fund.cash_conversion >= 0.8:
        latest_ni = fin.latest("net_income")
        if latest_ni is not None and latest_ni > 0:
            floor = 0.7 * latest_ni
            if base_fcf is None or floor > base_fcf:
                base_fcf = floor
                owner_earnings_floor = 1.0
                proxy_used = False

    fair_bear = fair_base = fair_bull = None
    implied = None
    debt_overhang_floor = 0.0
    if base_fcf is not None and shares:
        def per_share(g: float) -> float:
            # Equity has limited liability: a DCF can legitimately imply net
            # debt exceeds the enterprise value, but per-share equity "worth
            # less than nothing" is not a real price — floor at 0 and flag it
            # rather than surface a nonsensical negative fair value.
            nonlocal debt_overhang_floor
            raw = (dcf_value(base_fcf, g, discount, terminal) + net_cash) / shares
            if raw < 0:
                debt_overhang_floor = 1.0
                return 0.0
            return raw

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
            "fcf_spike_ratio": fcf_spike if fcf_spike is not None else float("nan"),
            "growth_defaulted": growth_defaulted,
            "owner_earnings_floor": owner_earnings_floor,
            "debt_overhang_floor": debt_overhang_floor,
        },
        completeness=completeness,
    )
