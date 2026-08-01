"""Central metric dictionary and versioned derived formulas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


METRIC_DEFINITION_VERSION = "2026-08-01.1"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    label: str
    description: str
    statement_category: str
    value_kind: str
    unit: str
    sign_convention: str
    period_types: tuple[str, ...]
    additive_quarters: bool
    ttm_compatible: bool
    public_exposure: str = "internal"
    screener_eligible: bool = False
    formula: str | None = None
    missing_behavior: str = "Missing stays missing; zero is a reported value."
    quality_requirements: str = "Compatible source, period, currency and basis."
    version: str = METRIC_DEFINITION_VERSION


def _m(metric_id, label, category, kind="flow", unit="INR", **kwargs):
    return MetricDefinition(
        metric_id=metric_id, label=label, description=kwargs.pop("description", label),
        statement_category=category, value_kind=kind, unit=unit,
        sign_convention=kwargs.pop("sign_convention", "Provider-reported sign is preserved."),
        period_types=kwargs.pop("period_types", ("annual", "quarter", "year_to_date", "ttm")),
        additive_quarters=kwargs.pop("additive_quarters", kind == "flow"),
        ttm_compatible=kwargs.pop("ttm_compatible", kind == "flow"), **kwargs,
    )


_DEFINITIONS = [
    _m("revenue", "Revenue from operations", "income"),
    _m("gross_profit", "Gross profit", "income"),
    _m("operating_income", "Operating profit (EBIT)", "income"),
    _m("ebitda", "EBITDA", "income"),
    _m("net_income", "Profit after tax", "income"),
    _m("interest_expense", "Finance cost", "income", sign_convention="Stored as a positive expense magnitude."),
    _m("eps_diluted", "Diluted EPS", "income", unit="INR/share", additive_quarters=False),
    _m("total_assets", "Total assets", "balance_sheet", kind="stock", period_types=("instant", "annual", "quarter")),
    _m("total_equity", "Total equity / net worth", "balance_sheet", kind="stock", period_types=("instant", "annual", "quarter")),
    _m("total_debt", "Total debt", "balance_sheet", kind="stock", period_types=("instant", "annual", "quarter")),
    _m("cash", "Cash and cash equivalents", "balance_sheet", kind="stock", period_types=("instant", "annual", "quarter")),
    _m("current_assets", "Current assets", "balance_sheet", kind="stock", period_types=("instant", "annual", "quarter")),
    _m("current_liabilities", "Current liabilities", "balance_sheet", kind="stock", period_types=("instant", "annual", "quarter")),
    _m("cfo", "Cash flow from operations", "cash_flow"),
    _m("capex", "Capital expenditure", "cash_flow", sign_convention="Stored as a positive cash-outflow magnitude."),
    _m("fcf", "Free cash flow", "derived", formula="cfo - capex"),
    _m("shares_diluted", "Diluted weighted shares", "income", unit="shares", additive_quarters=False),
    _m("dividends_paid", "Dividends paid", "cash_flow", sign_convention="Stored as a positive cash-outflow magnitude."),
    _m("revenue_cagr_3y", "Revenue CAGR (3y)", "derived", unit="ratio", additive_quarters=False,
       ttm_compatible=False, public_exposure="ready_with_caveat", screener_eligible=True,
       formula="(revenue[t] / revenue[t-3])^(1/3) - 1",
       quality_requirements="Positive annual endpoints exactly three fiscal years apart; same source, currency and basis."),
    _m("roce_3y", "ROCE (3y average)", "derived", unit="ratio", additive_quarters=False,
       ttm_compatible=False, public_exposure="ready_with_caveat", screener_eligible=True,
       formula="mean(operating_income / (total_equity + total_debt)) over up to 3 annual periods, minimum 2",
       quality_requirements="Same-period EBIT, equity and debt; positive capital; one source/currency/basis."),
]

FINANCIAL_METRICS = {item.metric_id: item for item in _DEFINITIONS}


def cagr(start: Decimal | None, end: Decimal | None, years: int) -> Decimal | None:
    if start is None or end is None or start <= 0 or end <= 0 or years <= 0:
        return None
    return Decimal(str((float(end / start) ** (1 / years)) - 1))


def ratio(numerator: Decimal | None, denominator: Decimal | None, *, require_positive_denominator: bool = False) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    if require_positive_denominator and denominator <= 0:
        return None
    return numerator / denominator
