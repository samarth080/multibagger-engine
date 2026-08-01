"""Versioned, evidence-conservative XBRL-to-canonical concept registry."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


CONCEPT_MAPPING_VERSION = "2026-08-01.1"


@dataclass(frozen=True)
class ConceptMapping:
    canonical_metric_id: str
    standard_concepts: tuple[str, ...]
    known_taxonomy_namespaces: tuple[str, ...]
    statement_category: str
    period_type: str
    expected_units: tuple[str, ...]
    allowed_consolidation_dimensions: tuple[str, ...]
    sign_convention: str
    confidence: Decimal
    public_eligible: bool
    mapping_version: str = CONCEPT_MAPPING_VERSION


# These names are directly observed in the captured KFINTECH Ind-AS result
# excerpt. Namespace-less excerpt support proves parser behavior, not taxonomy-
# wide public eligibility. Company extension concepts are intentionally absent.
CONCEPT_REGISTRY: dict[str, ConceptMapping] = {
    "revenue": ConceptMapping("revenue", ("RevenueFromOperations", "Income"), (), "income_statement", "duration", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "net_income": ConceptMapping("net_income", ("ProfitLossForPeriod", "ProfitLossForPeriodFromContinuingOperations"), (), "income_statement", "duration", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "interest_expense": ConceptMapping("interest_expense", ("FinanceCosts",), (), "income_statement", "duration", ("INR",), ("standalone", "consolidated"), "expense_positive", Decimal("1"), True),
    "cfo": ConceptMapping("cfo", ("CashFlowsFromUsedInOperatingActivities",), (), "cash_flow", "duration", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "capex": ConceptMapping("capex", ("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",), (), "cash_flow", "duration", ("INR",), ("standalone", "consolidated"), "outflow_positive", Decimal("1"), True),
    "dividends_paid": ConceptMapping("dividends_paid", ("DividendsPaidClassifiedAsFinancingActivities",), (), "cash_flow", "duration", ("INR",), ("standalone", "consolidated"), "outflow_positive", Decimal("1"), True),
    "total_assets": ConceptMapping("total_assets", ("Assets",), (), "balance_sheet", "instant", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "total_equity": ConceptMapping("total_equity", ("Equity", "EquityAttributableToOwnersOfParent"), (), "balance_sheet", "instant", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "cash": ConceptMapping("cash", ("CashAndCashEquivalents",), (), "balance_sheet", "instant", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "current_assets": ConceptMapping("current_assets", ("CurrentAssets",), (), "balance_sheet", "instant", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
    "current_liabilities": ConceptMapping("current_liabilities", ("CurrentLiabilities",), (), "balance_sheet", "instant", ("INR",), ("standalone", "consolidated"), "reported", Decimal("1"), True),
}


def concept_mapping(metric_id: str) -> ConceptMapping:
    return CONCEPT_REGISTRY[metric_id]


def match_standard_concept(local_name: str) -> ConceptMapping | None:
    for mapping in CONCEPT_REGISTRY.values():
        if local_name in mapping.standard_concepts:
            return mapping
    return None


def extension_mapping_allowed(
    *,
    local_name: str,
    label_evidence: str | None,
    presentation_parent: str | None,
    calculation_parent: str | None,
) -> bool:
    """Fail closed: no company extension is accepted without a reviewed rule.

    The arguments make the required evidence explicit for future registry
    additions; vague label similarity can never authorize a mapping here.
    """
    del local_name, label_evidence, presentation_parent, calculation_parent
    return False
