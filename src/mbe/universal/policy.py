"""Centralized, versioned Universal Research Score policy: factor
definitions, metric directions (reused from mbe.scoring.benchmarks),
weights, company-type rules, coverage thresholds. This is the one place
all of that lives — never duplicated into frontend code or scattered
across report-building modules.

Reuses mbe.scoring.benchmarks' HIGHER_BETTER/LOWER_BETTER tables and
score_metric() verbatim for every metric they already cover (roce_3y,
revenue_cagr_3y, debt_to_equity, etc.) — see the 2026-08-04 design doc's
"reuse proven factor logic" requirement. Only truly new metrics
(currently just net_margin) get a new table, in mbe.universal.benchmarks.
"""

from __future__ import annotations

from mbe.scoring.benchmarks import score_metric, score_rsi, score_trend
from mbe.universal.benchmarks import score_net_margin
from mbe.universal.domain import CompanyType

UNIVERSAL_SCORE_POLICY_VERSION = "universal-score-v1"

MIN_COVERAGE_FULL = 0.60
MIN_COVERAGE_PARTIAL = 0.30

FACTOR_WEIGHTS: dict[str, float] = {
    "Growth": 0.15,
    "Profitability": 0.12,
    "Capital efficiency": 0.10,
    "Financial strength": 0.10,
    "Cash-flow quality": 0.10,
    "Valuation": 0.15,
    "Momentum": 0.08,
    "Technical trend": 0.08,
    "Volatility and risk": 0.07,
    "Data quality": 0.05,
}

# (metric, weight-within-factor, rationale)
_GENERAL_FACTORS: dict[str, list[tuple[str, float, str]]] = {
    "Growth": [
        ("revenue_cagr_3y", 0.40, "Top-line growth is the rawest demand signal"),
        ("profit_cagr_3y", 0.40, "Profit growth shows demand converts to economics"),
        ("margin_trend", 0.20, "Expanding margins signal pricing power or operating leverage"),
    ],
    "Profitability": [
        ("roe_3y", 0.55, "Sustained return on equity shows durable shareholder economics"),
        ("net_margin", 0.45, "Net margin shows how much revenue converts to profit"),
    ],
    "Capital efficiency": [
        ("roce_3y", 1.0, "Return on capital employed is the engine of compounding"),
    ],
    "Financial strength": [
        ("debt_to_equity", 0.30, "Low leverage survives downturns and funds opportunity"),
        ("interest_coverage", 0.25, "Coverage headroom protects equity from creditors"),
        ("net_debt_to_ebitda", 0.25, "Deleveraging capacity in years of cash flow"),
        ("current_ratio", 0.20, "Short-term obligations comfortably met"),
    ],
    "Cash-flow quality": [
        ("fcf_margin", 0.35, "Free-cash-flow margin proves profits arrive as cash"),
        ("cash_conversion", 0.35, "CFO/NI near or above 1 validates earnings quality"),
        ("accruals_ratio", 0.30, "Low accruals mean accounting profit tracks cash reality"),
    ],
    "Valuation": [
        ("margin_of_safety", 0.40, "Price below conservatively-estimated intrinsic value"),
        ("peg", 0.20, "Price paid per unit of delivered growth"),
        ("implied_growth_gap", 0.20, "Market expectation vs delivered growth"),
        ("fcf_yield", 0.20, "Cash return earned at today's price"),
    ],
    "Momentum": [
        ("relative_strength_63d", 0.60, "Leaders outperform their index before big runs"),
        ("cmf20", 0.40, "Positive money flow confirms institutional buying"),
    ],
    "Technical trend": [
        ("trend_state", 0.50, "Stage-2 uptrends are where big moves happen"),
        ("rsi14", 0.25, "Momentum health without chasing overbought extremes"),
        ("dist_52w_high", 0.25, "Strength near 52-week highs signals accumulation"),
    ],
}

# Metrics assuming an industrial balance sheet — not meaningful for banks,
# NBFCs, insurers or asset managers (2026-08-04 audit finding). Excluded
# from the metric list entirely for these types, not scored-then-zeroed.
_INDUSTRIAL_ONLY_METRICS = {"roce_3y", "debt_to_equity", "net_debt_to_ebitda", "interest_coverage"}

FINANCIAL_COMPANY_TYPES = {
    CompanyType.BANK, CompanyType.NBFC, CompanyType.INSURANCE,
    CompanyType.ASSET_MANAGEMENT, CompanyType.OTHER_FINANCIAL,
}

_SPECIAL_SCORERS = {
    "net_margin": score_net_margin,
    "rsi14": score_rsi,
    "trend_state": score_trend,
}


def factors_for_company_type(company_type: CompanyType) -> dict[str, list[tuple[str, float, str]]]:
    if company_type not in FINANCIAL_COMPANY_TYPES:
        return {name: list(items) for name, items in _GENERAL_FACTORS.items()}
    return {
        name: [item for item in items if item[0] not in _INDUSTRIAL_ONLY_METRICS]
        for name, items in _GENERAL_FACTORS.items()
    }


def score_universal_metric(name: str, value) -> tuple[int, str] | None:
    """Returns (points, benchmark-string) or None when the metric has no
    defined scoring outcome for this value (e.g. trend_state == 'unknown')."""
    if name in _SPECIAL_SCORERS:
        return _SPECIAL_SCORERS[name](value)
    return score_metric(name, value)
