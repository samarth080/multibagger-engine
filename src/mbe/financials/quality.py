"""Non-destructive financial quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from mbe.financials.domain import FilingInput, QualityState


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    state: QualityState
    metric_id: str | None = None


def validate_filing(filing: FilingInput) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if filing.filing_date and filing.filing_date < filing.period.period_end:
        issues.append(QualityIssue("filing_before_period_end", "error", "Filing date precedes period end.", QualityState.REJECTED))
    if filing.basis.value == "conflicting":
        issues.append(QualityIssue("conflicting_basis", "error", "Filing metadata and parsed statement basis conflict.", QualityState.REJECTED))
    if filing.basis.value == "unknown":
        issues.append(QualityIssue("unknown_basis", "warning", "Consolidated versus standalone basis is unknown.", QualityState.VALID_WITH_WARNING))
    seen: set[tuple[str, str]] = set()
    values = {}
    for fact in filing.facts:
        key = (fact.metric_id, fact.source_field)
        if key in seen:
            issues.append(QualityIssue("duplicate_fact", "error", "Duplicate metric/source field in filing.", QualityState.REJECTED, fact.metric_id))
        seen.add(key)
        if fact.value is not None:
            values[fact.metric_id] = fact.value
    assets, equity, debt = values.get("total_assets"), values.get("total_equity"), values.get("total_debt")
    if assets is not None and equity is not None and debt is not None and assets != 0:
        # Debt + equity is not a complete liabilities equation, so only extreme excess is useful.
        if abs(equity + debt) > abs(assets) * Decimal("1.5"):
            issues.append(QualityIssue("balance_scale_anomaly", "warning", "Debt plus equity materially exceeds assets; check unit or taxonomy mapping.", QualityState.VALID_WITH_WARNING))
    if equity is not None and equity < 0:
        issues.append(QualityIssue("negative_equity", "warning", "Reported equity is negative.", QualityState.VALID_WITH_WARNING, "total_equity"))
    return issues


def freshness(period_end, *, as_of) -> tuple[str, str]:
    age = (as_of - period_end).days
    if age <= 550:
        return "current", f"Latest annual period ended {age} days before the dataset cutoff."
    if age <= 730:
        return "aging", f"Latest annual period ended {age} days before the dataset cutoff."
    return "stale", f"Latest annual period ended {age} days before the dataset cutoff."
