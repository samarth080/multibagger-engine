"""Safe parser registry for explicitly supported official result templates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET

from mbe.data.provider import ProviderError
from mbe.financials.domain import ConsolidationBasis, FinancialPeriod, PeriodType, SourceFact
from mbe.financials.official_domain import (
    AttachmentFormat,
    DiscoveredOfficialFiling,
    FetchedDocument,
    NSE_XBRL_PARSER_VERSION,
    ParsedOfficialFiling,
    ParserRecognition,
    XbrlFactEvidence,
)
from mbe.financials.xbrl_concepts import CONCEPT_MAPPING_VERSION, CONCEPT_REGISTRY


SOURCE_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    metric_id: mapping.standard_concepts for metric_id, mapping in CONCEPT_REGISTRY.items()
}

MAX_XML_ELEMENTS = 50_000
MAX_XML_DEPTH = 64
MAX_TEXT_LENGTH = 1_000_000
MAX_CONTEXTS = 10_000
MAX_NUMERIC_FACTS = 100_000

SUPPORTED_FORMAT_MATRIX = {
    "nse_corporate_results_json": {
        "format": "json",
        "status": "metadata_only",
        "reason": "Official announcement discovery metadata; it is not itself a financial fact table.",
    },
    "nse_ind_as_results_xbrl": {
        "format": "xbrl_xml",
        "status": "supported",
        "reason": "Deterministic Ind-AS result contexts with explicit period, basis and units.",
    },
    "xbrl_xml": {
        "format": "xbrl_xml",
        "status": "supported",
        "reason": "Deterministic Ind-AS result contexts with explicit period, basis and units.",
    },
    "json": {
        "format": "json",
        "status": "metadata_only",
        "reason": "Official discovery metadata is retained but is not treated as a financial fact table.",
    },
    "csv": {"format": "csv", "status": "unsupported", "reason": "No NSE result CSV template is fixture-qualified."},
    "xls": {"format": "xls", "status": "unsupported", "reason": "Legacy binary workbooks are deferred; macros and encryption are never executed."},
    "xlsx": {"format": "xlsx", "status": "unsupported", "reason": "Workbook-template recognition and formula-cache validation are deferred."},
    "html": {"format": "html", "status": "unsupported", "reason": "Legacy pages vary and the old regex parser is not canonical lineage."},
    "text_pdf": {"format": "text_pdf", "status": "unsupported", "reason": "No bounded text-table template is fixture-qualified yet."},
    "image_pdf": {"format": "image_pdf", "status": "unsupported", "reason": "OCR is out of scope."},
    "zip": {"format": "zip", "status": "unsupported", "reason": "Archive expansion is disabled until an explicit safe member contract exists."},
    "other": {"format": "other", "status": "unsupported", "reason": "Unknown documents are quarantined, not guessed."},
}


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None
    return parsed if parsed.is_finite() else None


def _scaled_decimal(value: str, scale: str | None) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    if scale in (None, "", "0"):
        return parsed
    try:
        exponent = int(scale)
    except ValueError:
        return None
    if not -18 <= exponent <= 18:
        return None
    return parsed * (Decimal(10) ** exponent)


def _namespace(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def _validate_xml_bounds(root) -> None:
    elements = contexts = numeric = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        elements += 1
        if elements > MAX_XML_ELEMENTS:
            raise ProviderError("official XBRL exceeds the safe element-count limit")
        if depth > MAX_XML_DEPTH:
            raise ProviderError("official XBRL exceeds the safe element-depth limit")
        if element.text and len(element.text) > MAX_TEXT_LENGTH:
            raise ProviderError("official XBRL contains an oversized text node")
        if _local(element.tag) == "context":
            contexts += 1
            if contexts > MAX_CONTEXTS:
                raise ProviderError("official XBRL exceeds the safe context-count limit")
        if element.get("contextRef") and element.text and _decimal(element.text) is not None:
            numeric += 1
            if numeric > MAX_NUMERIC_FACTS:
                raise ProviderError("official XBRL exceeds the safe numeric-fact limit")
        stack.extend((child, depth + 1) for child in element)


def _basis(value: str | None) -> ConsolidationBasis:
    lowered = (value or "").strip().lower()
    if "consolidated" in lowered:
        return ConsolidationBasis.CONSOLIDATED
    if "standalone" in lowered:
        return ConsolidationBasis.STANDALONE
    return ConsolidationBasis.UNKNOWN


def _unit(unit_ref: str | None, metric_id: str) -> str | None:
    normalized = (unit_ref or "").lower()
    if metric_id == "shares_diluted":
        return "shares"
    if metric_id == "eps_diluted" or "pershare" in normalized:
        return "INR/share"
    if normalized in {"inr", "iso4217:inr"}:
        return "INR"
    return None


def _periods(discovery: DiscoveredOfficialFiling, root) -> tuple[FinancialPeriod, FinancialPeriod]:
    start = discovery.period.period_start
    end = discovery.period.period_end
    for element in root.iter():
        name = _local(element.tag)
        if element.get("contextRef") != "FourD" or not element.text:
            continue
        try:
            if name == "DateOfStartOfReportingPeriod":
                start = date.fromisoformat(element.text.strip())
            elif name == "DateOfEndOfReportingPeriod":
                end = date.fromisoformat(element.text.strip())
        except ValueError:
            continue
    duration = (end - start).days + 1 if start else discovery.period.duration_days
    flow = discovery.period.model_copy(update={"period_start": start, "period_end": end, "duration_days": duration})
    instant = FinancialPeriod(
        period_type=PeriodType.INSTANT,
        fiscal_year=flow.fiscal_year,
        period_end=end,
        instant_date=end,
        source_label=f"As at {end.isoformat()}",
    )
    return flow, instant


def parse_nse_results_xbrl(
    document: FetchedDocument,
    discovery: DiscoveredOfficialFiling,
) -> ParsedOfficialFiling:
    if document.attachment_format != AttachmentFormat.XBRL_XML:
        raise ProviderError("NSE XBRL parser received a different validated format")
    try:
        root = ET.fromstring(document.content)
    except (ParseError, ValueError) as exc:
        raise ProviderError("official XBRL is not safely parseable XML") from exc
    _validate_xml_bounds(root)
    flow_period, instant_period = _periods(discovery, root)
    values: dict[tuple[str, str], list[dict]] = {}
    reporting_quarter = None
    reported_basis = ConsolidationBasis.UNKNOWN
    namespaces: set[str] = set()
    for element in root.iter():
        name = _local(element.tag)
        namespace = _namespace(element.tag)
        if namespace:
            namespaces.add(namespace)
        context = element.get("contextRef")
        if element.text:
            if name == "ReportingQuarter":
                reporting_quarter = element.text.strip()
            elif name == "NatureOfReportStandaloneConsolidated":
                reported_basis = _basis(element.text)
            nil = element.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true" or element.get("nil") == "true"
            if context in {"FourD", "OneI"} and not nil:
                value = _scaled_decimal(element.text, element.get("scale"))
                if value is not None:
                    values.setdefault((name, context), []).append({
                        "value": value,
                        "original_value": element.text.strip(),
                        "unit_ref": element.get("unitRef"),
                        "decimals": element.get("decimals"),
                        "precision": element.get("precision"),
                        "scale": int(element.get("scale") or 0),
                        "namespace": namespace,
                    })
    annual = discovery.period.period_type == PeriodType.ANNUAL
    if annual and reporting_quarter not in {"Yearly", "Annual"}:
        raise ProviderError("XBRL template does not identify the expected annual result context")
    if reported_basis != ConsolidationBasis.UNKNOWN and discovery.basis_hint != ConsolidationBasis.UNKNOWN and reported_basis != discovery.basis_hint:
        basis = ConsolidationBasis.CONFLICTING
    else:
        basis = reported_basis if reported_basis != ConsolidationBasis.UNKNOWN else discovery.basis_hint
    facts: list[SourceFact] = []
    fact_evidence: list[XbrlFactEvidence] = []
    tag_for_metric: dict[str, str] = {}
    unresolved_units: list[str] = []
    duplicate_conflicts: list[str] = []
    for metric_id, tags in SOURCE_LABEL_ALIASES.items():
        context = "OneI" if metric_id in {"total_assets", "total_equity", "cash", "current_assets", "current_liabilities"} else "FourD"
        for tag in tags:
            candidates = values.get((tag, context), [])
            if not candidates:
                continue
            unique = {(item["value"], item["unit_ref"]) for item in candidates}
            if len(unique) > 1:
                duplicate_conflicts.append(f"{tag}:{context}")
                # A conflict in the preferred accepted concept is not permission
                # to silently fall through to a semantically broader alias.
                break
            found = candidates[0]
            value, unit_ref = found["value"], found["unit_ref"]
            unit = _unit(unit_ref, metric_id)
            if unit is None:
                unit = "unresolved"
                unresolved_units.append(tag)
            tag_for_metric[metric_id] = tag
            facts.append(SourceFact(
                source_field=tag,
                metric_id=metric_id,
                value=value,
                unit=unit,
                currency="INR" if unit.startswith("INR") else None,
                period=instant_period if context == "OneI" else flow_period,
                basis=basis,
                source_location=f"xbrl:{context}:{tag}",
            ))
            fact_evidence.append(XbrlFactEvidence(
                canonical_metric_id=metric_id,
                selected_value=value,
                original_value=found["original_value"],
                normalized_value=value,
                unit=unit,
                unit_ref=unit_ref,
                concept=tag,
                namespace=found["namespace"],
                context_id=context,
                decimals=found["decimals"],
                precision=found["precision"],
                scale=found["scale"],
                mapping_version=CONCEPT_MAPPING_VERSION,
                mapping_status="accepted" if unit != "unresolved" else "accepted_with_unresolved_unit",
                candidate_count=len(candidates),
                selection_reason="First accepted standard concept by versioned registry precedence; duplicate-equivalent candidates collapse.",
                duplicate_equivalent=len(candidates) > 1,
            ))
            break

    def raw(tag: str, context: str = "FourD") -> Decimal | None:
        items = values.get((tag, context), [])
        if not items or len({item["value"] for item in items}) > 1:
            return None
        return items[0]["value"]

    pbt, finance = raw("ProfitBeforeTax"), raw("FinanceCosts")
    if pbt is not None and finance is not None:
        operating_income = pbt + finance
        facts.append(SourceFact(
            source_field="ProfitBeforeTax+FinanceCosts",
            metric_id="operating_income",
            value=operating_income,
            unit="INR",
            currency="INR",
            period=flow_period,
            basis=basis,
            source_location="xbrl:FourD:derived-ebit-proxy",
            is_derived=True,
            source_fact_ids=("ProfitBeforeTax", "FinanceCosts"),
        ))
        depreciation = raw("DepreciationDepletionAndAmortisationExpense")
        if depreciation is not None:
            facts.append(SourceFact(
                source_field="ProfitBeforeTax+FinanceCosts+Depreciation",
                metric_id="ebitda",
                value=operating_income + depreciation,
                unit="INR",
                currency="INR",
                period=flow_period,
                basis=basis,
                source_location="xbrl:FourD:derived-ebitda-proxy",
                is_derived=True,
                source_fact_ids=("ProfitBeforeTax", "FinanceCosts", "DepreciationDepletionAndAmortisationExpense"),
            ))
    borrowings = [raw("BorrowingsCurrent", "OneI"), raw("BorrowingsNoncurrent", "OneI")]
    known_borrowings = [value for value in borrowings if value is not None]
    if known_borrowings:
        facts.append(SourceFact(
            source_field="BorrowingsCurrent+BorrowingsNoncurrent",
            metric_id="total_debt",
            value=sum(known_borrowings),
            unit="INR",
            currency="INR",
            period=instant_period,
            basis=basis,
            source_location="xbrl:OneI:derived-total-debt",
            is_derived=True,
            source_fact_ids=("BorrowingsCurrent", "BorrowingsNoncurrent"),
        ))
    paid_up, face_value = raw("PaidUpValueOfEquityShareCapital"), raw("FaceValueOfEquityShareCapital")
    if paid_up is not None and face_value not in (None, Decimal("0")):
        facts.append(SourceFact(
            source_field="PaidUpValueOfEquityShareCapital/FaceValueOfEquityShareCapital",
            metric_id="shares_diluted",
            value=paid_up / face_value,
            unit="shares",
            period=flow_period,
            basis=basis,
            source_location="xbrl:FourD:derived-shares",
            is_derived=True,
            source_fact_ids=("PaidUpValueOfEquityShareCapital", "FaceValueOfEquityShareCapital"),
        ))
    by_metric = {fact.metric_id: fact for fact in facts}
    if "cfo" in by_metric and "capex" in by_metric:
        facts.append(SourceFact(
            source_field="CashFlowsFromUsedInOperatingActivities-PurchaseOfPropertyPlantAndEquipment",
            metric_id="fcf",
            value=by_metric["cfo"].value - by_metric["capex"].value,
            unit="INR",
            currency="INR",
            period=flow_period,
            basis=basis,
            source_location="xbrl:FourD:derived-fcf",
            is_derived=True,
            source_fact_ids=(by_metric["cfo"].source_location or "", by_metric["capex"].source_location or ""),
        ))
    mapped = {fact.metric_id for fact in facts}
    required = {"revenue", "net_income"}
    confidence = Decimal("1") if required <= mapped and basis != ConsolidationBasis.CONFLICTING else Decimal("0.75")
    warnings: list[str] = []
    if unresolved_units:
        warnings.append(
            "Unresolved units prevent publication for: " + ", ".join(sorted(unresolved_units)) + "."
        )
    if duplicate_conflicts:
        warnings.append(
            "Conflicting duplicate facts were excluded: " + ", ".join(sorted(duplicate_conflicts)) + "."
        )
    if basis == ConsolidationBasis.UNKNOWN:
        warnings.append("Consolidation basis was not resolved from filing metadata or XBRL.")
    elif basis == ConsolidationBasis.CONFLICTING:
        warnings.append("Filing metadata and XBRL disagree on consolidation basis.")
    if not required <= mapped:
        warnings.append("The recognized template is missing one or more required income-statement facts.")
    taxonomy_namespace = sorted(namespaces)[0] if len(namespaces) == 1 else None
    taxonomy_status = "supported_excerpt" if not namespaces else "unsupported"
    if namespaces:
        warnings.append("A namespaced taxonomy has not been fixture-qualified for Phase 6 publication.")
    return ParsedOfficialFiling(
        parser_version=NSE_XBRL_PARSER_VERSION,
        recognition=ParserRecognition(
            template_id="nse-ind-as-results-xbrl",
            template_version="1",
            confidence=confidence,
            required_fields_present=required <= mapped,
            warnings=warnings,
        ),
        period=flow_period,
        basis=basis,
        audited_status=discovery.audited_status,
        currency="INR",
        original_unit="INR",
        facts=facts,
        taxonomy_namespace=taxonomy_namespace,
        taxonomy_version="captured-excerpt-v1" if not namespaces else None,
        taxonomy_status=taxonomy_status,
        fact_evidence=fact_evidence,
        warnings=warnings,
    )


class OfficialParserRegistry:
    def parse(self, document: FetchedDocument, discovery: DiscoveredOfficialFiling) -> ParsedOfficialFiling:
        if document.attachment_format == AttachmentFormat.XBRL_XML:
            return parse_nse_results_xbrl(document, discovery)
        matrix = SUPPORTED_FORMAT_MATRIX.get(document.attachment_format.value, SUPPORTED_FORMAT_MATRIX["other"])
        raise ProviderError(f"unsupported official filing format: {matrix['reason']}")

    @staticmethod
    def support(format_value: AttachmentFormat) -> dict:
        return SUPPORTED_FORMAT_MATRIX.get(format_value.value, SUPPORTED_FORMAT_MATRIX["other"])
