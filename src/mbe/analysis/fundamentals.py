"""Fundamental metric computation. Pure function of statement history.

Policy: a metric that cannot be computed from reported data is None.
None metrics lower `completeness`; nothing is imputed or guessed.
ROIC uses a flat 25% tax assumption (documented model choice for v0.1).
"""

from __future__ import annotations

from mbe.models.analysis import FundamentalMetrics
from mbe.models.company import CompanyInfo, FinancialHistory

TAX_RATE = 0.25


def _cagr(fin: FinancialHistory, field: str, years: int) -> float | None:
    by_year = {y: v for y, v in fin.series(field)}
    if not by_year:
        return None
    end_year = max(by_year)
    start_year = end_year - years
    start, end = by_year.get(start_year), by_year[end_year]
    if start is None or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / years) - 1


def _latest_ratio(fin: FinancialHistory, num: str, den: str) -> float | None:
    """num/den at the latest year where both are reported and den != 0."""
    num_by_year = dict(fin.series(num))
    den_by_year = dict(fin.series(den))
    common = sorted(set(num_by_year) & set(den_by_year))
    for year in reversed(common):
        if den_by_year[year] != 0:
            return num_by_year[year] / den_by_year[year]
    return None


def _avg_ratio_3y(fin: FinancialHistory, num: str, den: str) -> float | None:
    """Mean of num/den over the last up-to-3 common years (needs >= 2)."""
    num_by_year = dict(fin.series(num))
    den_by_year = dict(fin.series(den))
    common = [y for y in sorted(set(num_by_year) & set(den_by_year)) if den_by_year[y] != 0]
    last = common[-3:]
    if len(last) < 2:
        return None
    return sum(num_by_year[y] / den_by_year[y] for y in last) / len(last)


def _sum_ratio_3y(fin: FinancialHistory, num: str, den: str) -> float | None:
    """sum(num last 3y) / sum(den last 3y); requires positive denominator."""
    num_by_year = dict(fin.series(num))
    den_by_year = dict(fin.series(den))
    common = sorted(set(num_by_year) & set(den_by_year))[-3:]
    if len(common) < 2:
        return None
    den_sum = sum(den_by_year[y] for y in common)
    if den_sum <= 0:
        return None
    return sum(num_by_year[y] for y in common) / den_sum


def _capital_ratio(
    fin: FinancialHistory, year: int, ebit: float, subtract_cash: bool
) -> float | None:
    equity = fin.value("total_equity", year)
    debt = fin.value("total_debt", year)
    if equity is None or debt is None:
        return None
    capital = equity + debt
    if subtract_cash:
        cash = fin.value("cash", year)
        if cash is None:
            return None
        capital -= cash
        ebit = ebit * (1 - TAX_RATE)
    if capital <= 0:
        return None
    return ebit / capital


def _roce_like(fin: FinancialHistory, subtract_cash: bool) -> float | None:
    ebit_series = fin.series("operating_income")
    for year, ebit in reversed(ebit_series):
        r = _capital_ratio(fin, year, ebit, subtract_cash)
        if r is not None:
            return r
    return None


def _margin_trend(fin: FinancialHistory) -> float | None:
    op = dict(fin.series("operating_income"))
    rev = dict(fin.series("revenue"))
    common = [y for y in sorted(set(op) & set(rev)) if rev[y] != 0]
    if not common:
        return None
    latest = common[-1]
    past = latest - 3
    if past not in common:
        return None
    return op[latest] / rev[latest] - op[past] / rev[past]


def _accruals(fin: FinancialHistory) -> float | None:
    ni = dict(fin.series("net_income"))
    cfo = dict(fin.series("cfo"))
    assets = dict(fin.series("total_assets"))
    common = sorted(set(ni) & set(cfo) & set(assets))
    for year in reversed(common):
        if assets[year] > 0:
            return (ni[year] - cfo[year]) / assets[year]
    return None


def compute_fundamentals(fin: FinancialHistory, info: CompanyInfo) -> FundamentalMetrics:
    values: dict[str, float | None] = {
        "revenue_cagr_3y": _cagr(fin, "revenue", 3),
        "revenue_cagr_5y": _cagr(fin, "revenue", 5),
        "profit_cagr_3y": _cagr(fin, "net_income", 3),
        "profit_cagr_5y": _cagr(fin, "net_income", 5),
        "fcf_cagr_3y": _cagr(fin, "fcf", 3),
        "gross_margin": _latest_ratio(fin, "gross_profit", "revenue"),
        "operating_margin": _latest_ratio(fin, "operating_income", "revenue"),
        "ebitda_margin": _latest_ratio(fin, "ebitda", "revenue"),
        "net_margin": _latest_ratio(fin, "net_income", "revenue"),
        "operating_margin_3y_avg": _avg_ratio_3y(fin, "operating_income", "revenue"),
        "margin_trend": _margin_trend(fin),
        "roe": _latest_ratio(fin, "net_income", "total_equity"),
        "roe_3y": _avg_ratio_3y(fin, "net_income", "total_equity"),
        "roce": _roce_like(fin, subtract_cash=False),
        "roce_3y": None,  # filled below
        "roic": _roce_like(fin, subtract_cash=True),
        "debt_to_equity": _latest_ratio(fin, "total_debt", "total_equity"),
        "net_debt_to_ebitda": None,  # filled below
        "interest_coverage": _latest_ratio(fin, "operating_income", "interest_expense"),
        "current_ratio": _latest_ratio(fin, "current_assets", "current_liabilities"),
        "fcf_margin": _latest_ratio(fin, "fcf", "revenue"),
        "cash_conversion": _sum_ratio_3y(fin, "cfo", "net_income"),
        "accruals_ratio": _accruals(fin),
        "reinvestment_rate": _sum_ratio_3y(fin, "capex", "cfo"),
        "share_count_cagr_3y": _cagr(fin, "shares_diluted", 3),
    }

    # roce_3y: average ROCE over last up-to-3 years with full inputs
    roce_vals = []
    for year, ebit in fin.series("operating_income")[-3:]:
        r = _capital_ratio(fin, year, ebit, subtract_cash=False)
        if r is not None:
            roce_vals.append(r)
    values["roce_3y"] = sum(roce_vals) / len(roce_vals) if len(roce_vals) >= 2 else None

    # net debt / ebitda at latest common year, ebitda must be positive
    debt = dict(fin.series("total_debt"))
    cash = dict(fin.series("cash"))
    ebitda = dict(fin.series("ebitda"))
    common = sorted(set(debt) & set(cash) & set(ebitda))
    for year in reversed(common):
        if ebitda[year] > 0:
            values["net_debt_to_ebitda"] = (debt[year] - cash[year]) / ebitda[year]
            break

    computed = sum(1 for v in values.values() if v is not None)
    values["completeness"] = computed / len(values)
    return FundamentalMetrics(**values)
