"""Quality-gated public metrics derived only from compatible official facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from mbe.financials.domain import ConsolidationBasis, FinancialPeriod, PeriodType
from mbe.financials.metrics import cagr, ratio
from mbe.financials.official_repository import official_fact_view


def derive_official_public_metrics(
    session: Session,
    instrument_id: str,
    *,
    as_of: datetime,
) -> dict[str, dict]:
    facts = official_fact_view(
        session,
        instrument_id,
        metric_ids=("revenue", "operating_income", "total_equity", "total_debt"),
        as_of=as_of,
        view="latest_known",
    )
    by_basis: dict[str, dict[tuple[str, object], object]] = {}
    for fact in facts:
        if fact.consolidation_basis not in {"consolidated", "standalone"}:
            continue
        by_basis.setdefault(fact.consolidation_basis, {})[(fact.metric_id, fact.period_end)] = fact
    for basis_value in ("consolidated", "standalone"):
        indexed = by_basis.get(basis_value, {})
        if not indexed:
            continue
        revenue_rows = sorted(
            (fact for (metric, _), fact in indexed.items() if metric == "revenue" and fact.period_type == "annual"),
            key=lambda fact: fact.period_end,
        )
        revenue_metric = None
        for end in reversed(revenue_rows):
            start = next((item for item in revenue_rows if item.period_end.year == end.period_end.year - 3 and item.period_end.month == end.period_end.month and item.period_end.day == end.period_end.day), None)
            if start:
                value = cagr(start.normalized_value, end.normalized_value, 3)
                if value is not None:
                    revenue_metric = {
                        "metric_id": "revenue_cagr_3y",
                        "value": value,
                        "unit": "ratio",
                        "basis": basis_value,
                        "period": FinancialPeriod(
                            period_type=PeriodType.ANNUAL,
                            fiscal_year=end.period_end.year,
                            period_start=end.period_start,
                            period_end=end.period_end,
                            duration_days=(end.period_end - end.period_start).days + 1 if end.period_start else None,
                            source_label=f"FY{start.period_end.year}–FY{end.period_end.year}",
                        ),
                        "source_fact_ids": [start.fact_id, end.fact_id],
                        "quality_status": "derived",
                    }
                    break
        annual_operating = sorted(
            (fact for (metric, _), fact in indexed.items() if metric == "operating_income" and fact.period_type == "annual"),
            key=lambda fact: fact.period_end,
        )
        annual_ratios = []
        ratio_fact_ids = []
        for operating in annual_operating:
            equity = indexed.get(("total_equity", operating.period_end))
            debt = indexed.get(("total_debt", operating.period_end))
            if equity is None or debt is None:
                continue
            value = ratio(
                operating.normalized_value,
                equity.normalized_value + debt.normalized_value,
                require_positive_denominator=True,
            )
            if value is not None:
                annual_ratios.append((operating.period_end, value))
                ratio_fact_ids.append((operating.period_end, [operating.fact_id, equity.fact_id, debt.fact_id]))
        latest_ratios = annual_ratios[-3:]
        roce_metric = None
        if len(latest_ratios) >= 2:
            end = latest_ratios[-1][0]
            ids_by_end = dict(ratio_fact_ids)
            roce_metric = {
                "metric_id": "roce_3y",
                "value": sum(value for _, value in latest_ratios) / Decimal(len(latest_ratios)),
                "unit": "ratio",
                "basis": basis_value,
                "period": FinancialPeriod(
                    period_type=PeriodType.ANNUAL,
                    fiscal_year=end.year,
                    period_end=end,
                    source_label=f"Latest {len(latest_ratios)} official annual periods",
                ),
                "source_fact_ids": [fact_id for period_end, _ in latest_ratios for fact_id in ids_by_end[period_end]],
                "quality_status": "derived",
            }
        result = {}
        if revenue_metric:
            result["revenue_cagr_3y"] = revenue_metric
        if roce_metric:
            result["roce_3y"] = roce_metric
        if result:
            return result
    return {}
