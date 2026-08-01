"""Decimal unit, period and quarter/TTM normalization."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from mbe.financials.domain import ConsolidationBasis, FinancialPeriod, PeriodType, SourceFact


UNIT_FACTORS = {
    "INR": Decimal("1"), "rupees": Decimal("1"), "thousand_inr": Decimal("1000"),
    "lakh_inr": Decimal("100000"), "million_inr": Decimal("1000000"),
    "crore_inr": Decimal("10000000"), "shares": Decimal("1"),
    "INR/share": Decimal("1"), "ratio": Decimal("1"),
}


def normalize_decimal(value, unit: str) -> tuple[Decimal, Decimal]:
    if unit not in UNIT_FACTORS:
        raise ValueError(f"unsupported financial unit: {unit}")
    try:
        original = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("invalid decimal financial value") from exc
    if not original.is_finite():
        raise ValueError("financial value must be finite")
    return original * UNIT_FACTORS[unit], UNIT_FACTORS[unit]


def annual_period(fiscal_year: int, fiscal_year_end_month: int = 3) -> FinancialPeriod:
    if fiscal_year_end_month == 12:
        end = date(fiscal_year, 12, 31)
        start = date(fiscal_year, 1, 1)
    else:
        end = date(fiscal_year, fiscal_year_end_month, 31)
        start = date(fiscal_year - 1, fiscal_year_end_month + 1, 1)
    return FinancialPeriod(period_type=PeriodType.ANNUAL, fiscal_year=fiscal_year,
                           period_start=start, period_end=end,
                           duration_days=(end - start).days + 1,
                           source_label=f"FY{fiscal_year}")


def derive_quarter_from_ytd(current: SourceFact, prior: SourceFact) -> SourceFact:
    if current.period.period_type != PeriodType.YEAR_TO_DATE or prior.period.period_type != PeriodType.YEAR_TO_DATE:
        raise ValueError("quarter derivation requires YTD facts")
    if current.metric_id != prior.metric_id or current.basis != prior.basis:
        raise ValueError("YTD facts must share metric and basis")
    if current.period.fiscal_year != prior.period.fiscal_year:
        raise ValueError("YTD facts must share fiscal year")
    if current.value is None or prior.value is None:
        raise ValueError("YTD values are required")
    period = current.period.model_copy(update={"period_type": PeriodType.QUARTER})
    return current.model_copy(update={
        "value": current.value - prior.value, "period": period, "is_derived": True,
        "source_fact_ids": tuple(x for x in (prior.source_location, current.source_location) if x),
    })


def derive_ttm(quarters: list[SourceFact]) -> SourceFact:
    ordered = sorted(quarters, key=lambda item: item.period.period_end)
    if len(ordered) != 4 or any(item.period.period_type != PeriodType.QUARTER for item in ordered):
        raise ValueError("TTM requires four quarter-only facts")
    identity = {(item.metric_id, item.basis, item.currency) for item in ordered}
    if len(identity) != 1 or any(item.value is None for item in ordered):
        raise ValueError("TTM quarters must share metric, basis and currency")
    for left, right in zip(ordered, ordered[1:]):
        gap = (right.period.period_end - left.period.period_end).days
        if not 75 <= gap <= 110:
            raise ValueError("TTM quarters are not sequential")
    last = ordered[-1]
    period = FinancialPeriod(period_type=PeriodType.TTM, fiscal_year=last.period.fiscal_year,
                             period_start=ordered[0].period.period_start,
                             period_end=last.period.period_end, duration_days=sum(
                                 item.period.duration_days or 0 for item in ordered),
                             source_label=f"TTM {last.period.period_end.isoformat()}")
    return last.model_copy(update={"value": sum(item.value for item in ordered),
                                   "period": period, "is_derived": True,
                                   "source_fact_ids": tuple(item.source_location or "" for item in ordered)})


def choose_basis(available: set[ConsolidationBasis]) -> ConsolidationBasis:
    if ConsolidationBasis.CONSOLIDATED in available:
        return ConsolidationBasis.CONSOLIDATED
    if ConsolidationBasis.STANDALONE in available:
        return ConsolidationBasis.STANDALONE
    return ConsolidationBasis.UNKNOWN
