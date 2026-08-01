"""Single source of truth for public screener fields and presets."""

from __future__ import annotations

from mbe.screener.domain import ScreenerField, limits_manifest

FIELD_REGISTRY_VERSION = "2026-08-01.3"

NUMERIC_OPERATORS = (
    "gt", "gte", "lt", "lte", "eq", "ne", "between",
    "is_available", "is_missing",
)
CATEGORICAL_OPERATORS = (
    "any_of", "none_of", "eq", "ne", "is_available", "is_missing",
)
TEXT_OPERATORS = ("contains", "starts_with", "eq", "ne", "is_available", "is_missing")
BOOLEAN_OPERATORS = ("is_true", "is_false", "is_available", "is_missing")
TRENDS = ("strong_up", "up", "sideways", "down", "strong_down", "unknown")


def _field(field_id: str, label: str, description: str, category: str, data_type: str,
           operators: tuple[str, ...], source: str, **kwargs) -> ScreenerField:
    return ScreenerField(
        field_id=field_id, label=label, description=description, category=category,
        data_type=data_type, operators=operators, data_source=source, **kwargs,
    )


_FIELDS = [
    _field("company", "Company", "Canonical display name for the issuer.", "Identity & classification", "text", TEXT_OPERATORS, "canonical company master", freshness_category="instrument_master", default_width="18rem"),
    _field("nse_symbol", "NSE symbol", "Current primary NSE trading symbol.", "Identity & classification", "text", TEXT_OPERATORS, "canonical primary listing", freshness_category="instrument_master"),
    _field("exchange", "Exchange", "Exchange for the current primary listing.", "Identity & classification", "categorical", CATEGORICAL_OPERATORS, "canonical primary listing", freshness_category="instrument_master", allowed_values=("NSE", "BSE")),
    _field("sector", "Sector", "Provider-normalized broad sector classification.", "Identity & classification", "categorical", CATEGORICAL_OPERATORS, "canonical instrument master", freshness_category="instrument_master", availability="ready_with_caveat", caveat="Classification follows the current pinned master/provider taxonomy."),
    _field("industry", "Industry", "Provider-normalized industry classification.", "Identity & classification", "categorical", CATEGORICAL_OPERATORS, "canonical instrument master", freshness_category="instrument_master", availability="ready_with_caveat", caveat="Classification follows the current pinned master/provider taxonomy.", default_width="14rem"),
    _field("rank", "Current rank", "Deterministic position within the selected scored build.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="rank", display_format="integer", minimum=1),
    _field("previous_rank", "Previous rank", "Rank in the immediately preceding available model build.", "Multibagger model", "number", NUMERIC_OPERATORS, "derived from adjacent score snapshots", freshness_category="model_build", unit="rank", display_format="integer", minimum=1, availability="ready_with_caveat", caveat="Missing when no earlier comparable build is persisted or published."),
    _field("rank_change", "Rank change", "Previous rank minus current rank; positive means rank improved.", "Multibagger model", "number", NUMERIC_OPERATORS, "derived from adjacent score snapshots", freshness_category="model_build", unit="positions", display_format="signed_integer", availability="ready_with_caveat", caveat="Missing when no earlier comparable build is available."),
    _field("multibagger_score", "Multibagger Score", "Explainable 0–100 research score; not a return forecast.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="score", display_format="score", minimum=0, maximum=100),
    _field("previous_multibagger_score", "Previous Multibagger Score", "Score from the immediately preceding available build.", "Multibagger model", "number", NUMERIC_OPERATORS, "derived from adjacent score snapshots", freshness_category="model_build", unit="score", display_format="score", minimum=0, maximum=100, availability="ready_with_caveat", caveat="Missing when no earlier comparable build is available."),
    _field("score_change", "Score change", "Current Multibagger Score minus the previous score.", "Multibagger model", "number", NUMERIC_OPERATORS, "derived from adjacent score snapshots", freshness_category="model_build", unit="score points", display_format="signed_decimal", availability="ready_with_caveat", caveat="Missing when no earlier comparable build is available."),
    _field("investment_score", "Investment Score", "Weighted 0–100 investment-quality score.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="score", display_format="score", minimum=0, maximum=100),
    _field("confidence", "Confidence", "Input coverage and history depth; not a probability of performance.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="ratio", display_format="percent", minimum=0, maximum=1),
    _field("risk_score", "Risk", "Rule-based 0–100 flag score; higher means more or more severe flags.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="score", display_format="score", minimum=0, maximum=100),
    _field("positive_signal_count", "Positive signals", "Count of model evidence items scoring at least 70.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="count", display_format="integer", minimum=0),
    _field("red_flag_count", "Red flags", "Count of rule-based risk flags and hard-gate failures.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="count", display_format="integer", minimum=0),
    _field("coverage_quality", "Coverage quality", "Normalized analysis coverage; currently aligned with model confidence.", "Multibagger model", "number", NUMERIC_OPERATORS, "score snapshot", freshness_category="model_build", unit="ratio", display_format="percent", minimum=0, maximum=1, availability="ready_with_caveat", caveat="Currently equivalent to confidence and retained as an explicit extension point."),
    _field("has_missing_data", "Has missing inputs", "Whether missing inputs reduced model confidence.", "Multibagger model", "boolean", BOOLEAN_OPERATORS, "score snapshot", freshness_category="model_build", display_format="boolean"),
    _field("technical_trend", "Technical trend", "Rule-based state from the build's daily-price history.", "Technical & momentum", "categorical", CATEGORICAL_OPERATORS, "score snapshot", freshness_category="model_build", allowed_values=TRENDS, display_format="trend"),
]

for field_id, label, component in (
    ("quality_score", "Quality pillar", "Quality"),
    ("growth_score", "Growth pillar", "Growth"),
    ("financial_strength_score", "Financial Strength pillar", "Financial Strength"),
    ("valuation_score", "Valuation pillar", "Valuation"),
    ("momentum_score", "Momentum pillar", "Momentum"),
    ("size_runway_score", "Size Runway pillar", "Size Runway"),
    ("reinvestment_score", "Reinvestment pillar", "Reinvestment"),
):
    _FIELDS.append(_field(
        field_id, label, f"Persisted 0–100 {component} component score.",
        "Score components", "number", NUMERIC_OPERATORS,
        f"score component: {component}", freshness_category="model_build",
        unit="score", display_format="score", minimum=0, maximum=100,
    ))

_FIELDS.extend([
    _field("revenue_cagr_3y", "Revenue CAGR (3y)", "Compound annual revenue growth between annual periods exactly three fiscal years apart.", "Fundamentals", "number", NUMERIC_OPERATORS, "normalized financial dataset: annual revenue", freshness_category="financial_dataset", unit="ratio", display_format="percent", minimum=-1, maximum=5, availability="ready_with_caveat", period="annual, latest comparable 3-year span", formula="(revenue[t] / revenue[t-3])^(1/3) - 1", consolidation_rule="One source and one statement basis across both endpoints; current compatibility rows label basis unknown.", quality_rule="Positive endpoints; valid or valid-with-warning normalized facts only.", caveat="Official NSE facts are preferred when the complete three-year span passes quality gates; current static rows remain approved Yahoo compatibility fallbacks with unknown basis.", preferred_source="Official NSE financial-result filing", fallback_source="Yahoo compatibility (metric-specific approval)", source_quality_tiers="Tier A official when period/unit/basis resolve; Tier B approved fallback; Tier C excluded", reconciliation_available=True),
    _field("roce_3y", "ROCE (3y average)", "Average annual operating profit divided by equity plus debt over the latest up to three compatible years (minimum two).", "Fundamentals", "number", NUMERIC_OPERATORS, "normalized financial dataset: annual EBIT, equity and debt", freshness_category="financial_dataset", unit="ratio", display_format="percent", minimum=-1, maximum=2, availability="ready_with_caveat", period="annual, latest up to 3 compatible periods", formula="mean(EBIT / (equity + debt)); positive capital required", consolidation_rule="Numerator and denominator must share period, source, currency and basis; current compatibility rows label basis unknown.", quality_rule="At least two valid or valid-with-warning annual ratios; no zero/negative capital denominator.", caveat="Official NSE facts are preferred when every annual numerator/denominator passes quality gates; current static rows remain approved Yahoo compatibility fallbacks with unknown basis and lender caveats.", preferred_source="Official NSE financial-result filing", fallback_source="Yahoo compatibility (metric-specific approval)", source_quality_tiers="Tier A official when period/unit/basis resolve; Tier B approved fallback; Tier C excluded", reconciliation_available=True),
    _field("main_positive_signal", "Main positive signal", "Highest-weight positive model evidence for context.", "Explainability", "text", tuple(), "score snapshot", freshness_category="model_build", filterable=False, sortable=False, default_width="20rem"),
    _field("main_risk", "Main risk", "First rule-based risk or hard-gate explanation for context.", "Explainability", "text", tuple(), "score snapshot", freshness_category="model_build", filterable=False, sortable=False, default_width="20rem"),
])

SCREENER_FIELDS = {field.field_id: field for field in _FIELDS}

COMPONENT_FIELDS = {
    "quality_score": "Quality",
    "growth_score": "Growth",
    "financial_strength_score": "Financial Strength",
    "valuation_score": "Valuation",
    "momentum_score": "Momentum",
    "size_runway_score": "Size Runway",
    "reinvestment_score": "Reinvestment",
}

SCREENER_PRESETS = [
    {
        "preset_id": "high-score-moderate-risk",
        "label": "High Score, Moderate Risk",
        "description": "Score at least 70 with risk no higher than 45.",
        "conditions": [
            {"field_id": "multibagger_score", "operator": "gte", "value": 70},
            {"field_id": "risk_score", "operator": "lte", "value": 45},
        ],
    },
    {
        "preset_id": "high-confidence",
        "label": "High Confidence Candidates",
        "description": "At least 90% model input coverage.",
        "conditions": [{"field_id": "confidence", "operator": "gte", "value": .9}],
    },
    {
        "preset_id": "positive-trend",
        "label": "Positive Technical Trend",
        "description": "Up or strong-up technical state at the selected build.",
        "conditions": [{"field_id": "technical_trend", "operator": "any_of", "values": ["up", "strong_up"]}],
    },
    {
        "preset_id": "improving-rank",
        "label": "Improving Rank",
        "description": "Moved up by at least one position since the previous comparable build.",
        "conditions": [{"field_id": "rank_change", "operator": "gte", "value": 1}],
    },
    {
        "preset_id": "lower-risk",
        "label": "Lower-Risk Research Candidates",
        "description": "Risk flag score no higher than 25; independent diligence is still required.",
        "conditions": [{"field_id": "risk_score", "operator": "lte", "value": 25}],
    },
    {
        "preset_id": "revenue-growth-and-returns",
        "label": "Revenue Growth & Returns",
        "description": "At least 10% three-year revenue CAGR and 15% three-year average ROCE; missing financials are excluded.",
        "conditions": [
            {"field_id": "revenue_cagr_3y", "operator": "gte", "value": .10},
            {"field_id": "roce_3y", "operator": "gte", "value": .15},
        ],
    },
]


def field_manifest(*, build: dict | None = None, categorical_values: dict[str, list[str]] | None = None) -> dict:
    categorical_values = categorical_values or {}
    fields = []
    for field in _FIELDS:
        row = field.model_dump(mode="json")
        if field.field_id in categorical_values:
            row["allowed_values"] = sorted(set(categorical_values[field.field_id]))
        fields.append(row)
    return {
        "schema_version": "1.0",
        "field_registry_version": FIELD_REGISTRY_VERSION,
        "logic": "and",
        "fields": fields,
        "categories": list(dict.fromkeys(field.category for field in _FIELDS)),
        "operators": {
            "number": list(NUMERIC_OPERATORS),
            "categorical": list(CATEGORICAL_OPERATORS),
            "text": list(TEXT_OPERATORS),
            "boolean": list(BOOLEAN_OPERATORS),
        },
        "presets": SCREENER_PRESETS,
        "limits": limits_manifest(),
        "build": build,
    }
