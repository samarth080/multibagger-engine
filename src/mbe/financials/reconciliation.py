"""Provider reconciliation and centralized public source selection."""

from __future__ import annotations

from decimal import Decimal

from mbe.financials.domain import ConsolidationBasis, FinancialPeriod
from mbe.financials.official_domain import ReconciliationResult, ReconciliationStatus


COMPATIBILITY_FALLBACK_METRICS = frozenset({"revenue_cagr_3y", "roce_3y"})


def tolerances(metric_id: str) -> tuple[Decimal, Decimal]:
    """Return (absolute, relative) tolerance in the metric's normalized unit."""
    if metric_id in {"revenue_cagr_3y", "roce_3y", "eps_diluted"}:
        return Decimal("0.0001"), Decimal("0.005")
    if metric_id == "shares_diluted":
        return Decimal("1"), Decimal("0.001")
    return Decimal("1"), Decimal("0.001")


def reconcile_values(
    *,
    instrument_id: str,
    metric_id: str,
    official_period: FinancialPeriod,
    compatibility_period: FinancialPeriod | None,
    official_basis: ConsolidationBasis,
    compatibility_basis: ConsolidationBasis,
    official_value: Decimal | None,
    compatibility_value: Decimal | None,
    official_unit: str,
    compatibility_unit: str,
    official_fact_id: str | None = None,
    official_quality: str = "valid",
    official_publication_state: str = "unreviewed",
) -> ReconciliationResult:
    absolute_difference = None
    percentage_difference = None
    if official_value is not None and compatibility_value is not None:
        absolute_difference = abs(official_value - compatibility_value)
        absolute_tolerance, _ = tolerances(metric_id)
        if abs(official_value) > absolute_tolerance:
            percentage_difference = absolute_difference / abs(official_value)

    if official_value is None and compatibility_value is None:
        status = ReconciliationStatus.BOTH_MISSING
    elif official_value is None:
        status = ReconciliationStatus.COMPATIBILITY_ONLY
    elif compatibility_value is None:
        status = ReconciliationStatus.OFFICIAL_ONLY
    elif official_unit != compatibility_unit:
        status = ReconciliationStatus.UNIT_MISMATCH
    elif compatibility_period is None or (
        official_period.period_type != compatibility_period.period_type
        or official_period.period_end != compatibility_period.period_end
    ):
        status = ReconciliationStatus.PERIOD_MISMATCH
    elif (
        official_basis in {ConsolidationBasis.UNKNOWN, ConsolidationBasis.CONFLICTING}
        or compatibility_basis in {ConsolidationBasis.UNKNOWN, ConsolidationBasis.CONFLICTING}
    ):
        status = ReconciliationStatus.UNRESOLVED
    elif (
        official_basis != compatibility_basis
    ):
        status = ReconciliationStatus.BASIS_MISMATCH
    elif absolute_difference == 0:
        status = ReconciliationStatus.EXACT_MATCH
    else:
        absolute_tolerance, relative_tolerance = tolerances(metric_id)
        if absolute_difference is not None and (
            absolute_difference <= absolute_tolerance
            or percentage_difference is not None and percentage_difference <= relative_tolerance
        ):
            status = ReconciliationStatus.WITHIN_ROUNDING
        else:
            status = ReconciliationStatus.MATERIAL_DIFFERENCE

    official_eligible = (
        official_value is not None
        and official_quality in {"valid", "valid_with_warning", "derived"}
        and official_publication_state in {"eligible", "published"}
        and official_basis in {ConsolidationBasis.CONSOLIDATED, ConsolidationBasis.STANDALONE}
        and status not in {
            ReconciliationStatus.UNIT_MISMATCH,
            ReconciliationStatus.PERIOD_MISMATCH,
            ReconciliationStatus.BASIS_MISMATCH,
        }
    )
    fallback_eligible = compatibility_value is not None and metric_id in COMPATIBILITY_FALLBACK_METRICS
    rejected: list[dict] = []
    if official_eligible:
        selected_value = official_value
        selected_source = "nse_financial_results"
        reason = "Selected validated, publication-eligible official NSE fact under source-precedence policy."
        if compatibility_value is not None:
            rejected.append({"source": "yahoo_compatibility", "reason": f"official source has precedence; reconciliation={status.value}"})
    elif fallback_eligible:
        selected_value = compatibility_value
        selected_source = "yahoo_compatibility"
        reason = "Official fact was unavailable or ineligible; approved metric-specific compatibility fallback selected."
        if official_value is not None:
            rejected.append({"source": "nse_financial_results", "reason": f"official quality/basis/review/publication gate failed; reconciliation={status.value}"})
    else:
        selected_value = None
        selected_source = None
        reason = "No source passed the metric-specific public selection policy."
        if official_value is not None:
            rejected.append({"source": "nse_financial_results", "reason": "official quality, basis, review or publication gate failed"})
        if compatibility_value is not None:
            rejected.append({"source": "yahoo_compatibility", "reason": "fallback is not approved for this metric"})

    return ReconciliationResult(
        instrument_id=instrument_id,
        metric_id=metric_id,
        period=official_period,
        basis=official_basis,
        official_fact_id=official_fact_id,
        official_value=official_value,
        compatibility_value=compatibility_value,
        unit=official_unit,
        absolute_difference=absolute_difference,
        percentage_difference=percentage_difference,
        status=status,
        selected_value=selected_value,
        selected_source=selected_source,
        selection_reason=reason,
        rejected_alternatives=rejected,
    )
