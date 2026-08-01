"""Build-time latest financial projections for reports and the screener."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import uuid

from mbe.financials.metrics import METRIC_DEFINITION_VERSION
from mbe.financials.official_domain import (
    NSE_XBRL_PARSER_VERSION,
    RECONCILIATION_RULE_VERSION,
    SOURCE_SELECTION_RULE_VERSION,
)
from mbe.models.company import FinancialHistory


PUBLIC_FINANCIAL_FIELDS = ("revenue_cagr_3y", "roce_3y")


def project_history(fin: FinancialHistory, *, instrument_id: str, cutoff: datetime,
                    source_code: str = "yahoo_compatibility") -> dict:
    from mbe.analysis.fundamentals import compute_fundamentals
    from mbe.models.company import CompanyInfo
    metrics = compute_fundamentals(fin, CompanyInfo(ticker=instrument_id))
    years = fin.years()
    latest_year = max(years) if years else None
    values = {field: getattr(metrics, field) for field in PUBLIC_FINANCIAL_FIELDS}
    metric_lineage = {
        field: {
            "selected_source": source_code if value is not None else None,
            "source_quality_tier": "B" if value is not None else "C",
            "reconciliation_status": "compatibility_only" if value is not None else "both_missing",
            "basis": "unknown",
        }
        for field, value in values.items()
    }
    facts = []
    for metric_id in ("revenue", "operating_income", "net_income", "ebitda", "cfo", "fcf", "total_debt", "total_equity"):
        value = fin.value(metric_id, latest_year) if latest_year else None
        if value is not None:
            facts.append({"metric_id": metric_id, "value": value, "fiscal_year": latest_year,
                          "period_type": "annual", "unit": "INR", "currency": "INR"})
    fingerprint = hashlib.sha256(json.dumps({"instrument_id": instrument_id, "years": years,
        "values": values}, sort_keys=True).encode()).hexdigest()
    return {
        "instrument_id": instrument_id, "latest_annual_fiscal_year": latest_year,
        "latest_quarterly_period": None, "basis": "unknown", "basis_reason":
        "Yahoo compatibility statements do not identify consolidated versus standalone basis.",
        "source_code": source_code, "source_category": "compatibility-provider fallback",
        "preferred_source": "nse_financial_results",
        "selected_source": source_code,
        "source_quality_tier": "B",
        "source_selection_status": "approved_metric_specific_fallback",
        "source_selection_reason": "No fixture-qualified official multi-year series is present in the static dataset; the approved compatibility fallback remains selected for Revenue CAGR and ROCE only.",
        "selection_policy_version": SOURCE_SELECTION_RULE_VERSION,
        "reconciliation_status": "not_reconciled",
        "official_filing_id": None,
        "official_filing_date": None,
        "official_period_end": None,
        "official_source_url": None,
        "audited_status": "unknown", "restated": False, "quality_status": "valid_with_warning",
        "quality_warnings": [
            "Statement basis and filing publication date are unavailable from the compatibility source.",
            "No accepted official filing series is present in this static dataset; verify against the issuer or exchange filing.",
        ], "data_cutoff": cutoff.isoformat(), "retrieved_at": cutoff.isoformat(),
        "metric_definition_version": METRIC_DEFINITION_VERSION,
        "values": values, "metric_lineage": metric_lineage,
        "facts": facts, "fingerprint": fingerprint,
    }


def financial_build(projections: list[dict], *, cutoff: datetime) -> dict:
    canonical = json.dumps([{"id": p["instrument_id"], "fingerprint": p["fingerprint"]}
                            for p in sorted(projections, key=lambda x: x["instrument_id"])],
                           sort_keys=True)
    build_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mbe-financials:{hashlib.sha256(canonical.encode()).hexdigest()}"))
    coverage = {field: sum(p["values"].get(field) is not None for p in projections)
                for field in PUBLIC_FINANCIAL_FIELDS}
    total = len(projections)
    fallback_coverage = {field: {
        "covered": count,
        "missing": total - count,
        "coverage_percent": round(count / total * 100, 1) if total else 0,
    } for field, count in coverage.items()}
    return {"financial_dataset_build_id": build_id, "schema_version": "1.1",
            "metric_definition_version": METRIC_DEFINITION_VERSION,
            "source_cutoff": cutoff.isoformat(), "built_at": datetime.now(timezone.utc).isoformat(),
            "companies_attempted": total, "companies_completed": total, "companies_failed": 0,
            "status": "complete", "source_versions": {"yahoo_compatibility": "runtime-cache", "nse_financial_results": "not imported into static build"},
            "official_discovery_cutoff": None,
            "compatibility_source_cutoff": cutoff.isoformat(),
            "official_filing_count": 0,
            "attachment_count": 0,
            "parser_versions": {"nse_ind_as_results_xbrl": NSE_XBRL_PARSER_VERSION},
            "reconciliation_rule_version": RECONCILIATION_RULE_VERSION,
            "source_selection_rule_version": SOURCE_SELECTION_RULE_VERSION,
            "official_coverage": {field: {"covered": 0, "coverage_percent": 0.0} for field in PUBLIC_FINANCIAL_FIELDS},
            "compatibility_fallback_coverage": fallback_coverage,
            "conflict_count": 0,
            "reconciliation_summary": {
                field: {
                    "exact_match": 0,
                    "within_rounding_tolerance": 0,
                    "material_difference": 0,
                    "official_only": 0,
                    "compatibility_only": count,
                    "both_missing": total - count,
                    "not_comparable_without_official_series": total,
                }
                for field, count in coverage.items()
            },
            "selected_source_distribution": {
                "nse_financial_results": 0,
                "yahoo_compatibility": sum(coverage.values()),
            },
            "unknown_basis_count": total,
            "unsupported_format_count": 0,
            "public_metric_eligibility": {
                field: "Tier B approved compatibility fallback; promote per instrument only after official multi-year lineage passes Tier A gates."
                for field in PUBLIC_FINANCIAL_FIELDS
            },
            "coverage": fallback_coverage,
            "quality_summary": {"valid_with_warning": total},
            "warnings": ["The current static dataset contains no canonical official filing series; all public financial rows use an approved compatibility fallback with unknown statement basis."],
            "configuration_hash": hashlib.sha256(canonical.encode()).hexdigest()}
