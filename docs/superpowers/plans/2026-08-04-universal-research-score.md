# Universal Research Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score any searchable Indian-listed stock — not just the 250-company
Nifty Smallcap ranking universe — with a company-type-aware, missing-data-safe,
versioned "Universal Research Score," rendered as an additive institutional-
style report section, without changing the existing Multibagger/Smallcap
model, its scores, ranks, build IDs, or history in any way.

**Architecture:** A new `mbe.universal.*` package reuses the existing,
already-universe-agnostic metric layer (`mbe.analysis.fundamentals/
technicals/valuation/risk`) and the existing generic scoring primitives
(`mbe.scoring.benchmarks.score_metric`, the renormalized-weighted-mean
pattern from `mbe.scoring.pillars.build_pillar`), regrouped into a new
10-factor taxonomy with company-type variants. A new bounded, resumable
refresh CLI (`scripts/build_universal_scores.py`) pre-warms static JSON
artifacts for a bounded set of instruments; `api/company.py` reads a
pre-warmed artifact when present and falls back to a live, single-instrument,
edge-cached computation otherwise — mirroring how `api/analyze.py` already
works today, just wired into the canonical `/company/{id}.html` route
instead of a separate URL.

**Tech Stack:** Python 3.12, Pydantic 2, existing `mbe.data.yahoo.YahooProvider`,
Jinja2 templates, vanilla JS (`quote-controller.js` pattern), pytest.

---

## File structure

New files:
- `src/mbe/universal/__init__.py` — empty, package marker
- `src/mbe/universal/domain.py` — `CompanyType`, `ReportState`,
  `UniversalFactorScore`, `UniversalScoreCard` (Pydantic models)
- `src/mbe/universal/classification.py` — `classify_company_type()`
- `src/mbe/universal/benchmarks.py` — additive benchmark(s) not in
  `mbe.scoring.benchmarks` (currently just `net_margin`)
- `src/mbe/universal/policy.py` — factor definitions per company type,
  top-level factor weights, coverage thresholds, `UNIVERSAL_SCORE_POLICY_VERSION`
- `src/mbe/universal/engine.py` — `build_universal_score()`
- `src/mbe/universal/explanations.py` — deterministic strengths/risks text
- `src/mbe/universal/report.py` — report payload dict builder (the section
  list required by the design doc)
- `src/mbe/universal/pipeline.py` — `analyze_universal(ticker, provider)`
  orchestration, reusing `compute_fundamentals`/`compute_technicals`/
  `compute_valuation`/`assess_risk` exactly like `mbe.pipeline.analyze_ticker`
  does today
- `src/mbe/universal/cache.py` — source-hash + policy-version cache key,
  JSON artifact read/write helpers
- `scripts/build_universal_scores.py` — bounded, resumable refresh CLI
- `tests/test_universal_classification.py`
- `tests/test_universal_engine.py`
- `tests/test_universal_report.py`
- `tests/test_universal_pipeline.py`
- `tests/test_universal_cache.py`
- `tests/test_build_universal_scores.py`

Modified files (Tasks 12+, exact diffs pending file-structure confirmation
from the integration-surface audit — see the note at the top of that
section):
- `src/mbe/research/coverage.py`, `src/mbe/publish.py`, `api/company.py`,
  `src/mbe/frontend/templates/company_coverage.html`,
  `src/mbe/frontend/templates/company.html`,
  `src/mbe/frontend/assets/app.js`, `src/mbe/frontend/assets/screener.js`,
  `src/mbe/search/catalog.py`, `docs/HANDOVER.md`,
  `docs/universal-research-score-architecture.md` (new doc).

---

## Task 1: Universal domain models

**Files:**
- Create: `src/mbe/universal/__init__.py` (empty)
- Create: `src/mbe/universal/domain.py`
- Test: `tests/test_universal_domain.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_domain.py
from mbe.universal.domain import (
    CompanyType, ReportState, UniversalFactorScore, UniversalScoreCard,
)


def test_company_type_values_are_stable_strings():
    assert CompanyType.GENERAL_CORPORATE.value == "general_corporate"
    assert CompanyType.BANK.value == "bank"
    assert CompanyType.NBFC.value == "nbfc"
    assert CompanyType.INSURANCE.value == "insurance"
    assert CompanyType.ASSET_MANAGEMENT.value == "asset_management"
    assert CompanyType.OTHER_FINANCIAL.value == "other_financial"
    assert CompanyType.UNKNOWN_LIMITED_DATA.value == "unknown_limited_data"


def test_report_state_values_are_stable_strings():
    assert ReportState.FULL.value == "full_evaluated_report"
    assert ReportState.PARTIAL.value == "partial_evaluated_report"
    assert ReportState.TECHNICAL_ONLY.value == "technical_only_evaluated_report"
    assert ReportState.INSUFFICIENT.value == "insufficient_data_for_scoring"


def test_factor_score_defaults_to_none_score_not_zero():
    factor = UniversalFactorScore(name="Growth", confidence=0.0, eligible_weight=0.0)
    assert factor.score is None  # missing data must never default to 0


def test_scorecard_requires_policy_version():
    card = UniversalScoreCard(
        ticker="RELIANCE.NS", company_type=CompanyType.GENERAL_CORPORATE,
        confidence="Low", confidence_score=0.1, data_coverage_pct=10.0,
        report_state=ReportState.INSUFFICIENT, policy_version="universal-score-v1",
    )
    assert card.overall_score is None
    assert card.factors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_domain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.universal'`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/__init__.py
```

```python
# src/mbe/universal/domain.py
"""Universal Research Score domain types. A score that can be computed for
any searchable company with sufficient data — distinct from and never
mixed with mbe.models.scoring.ScoreCard (the validated Nifty Smallcap 250
Multibagger/Investment score). See docs/coverage-architecture.md for the
separate concept of *coverage level* (how much data exists); this module
is about the *score* computed from that data.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from mbe.models.scoring import Evidence


class CompanyType(str, Enum):
    GENERAL_CORPORATE = "general_corporate"
    BANK = "bank"
    NBFC = "nbfc"
    INSURANCE = "insurance"
    ASSET_MANAGEMENT = "asset_management"
    OTHER_FINANCIAL = "other_financial"
    UNKNOWN_LIMITED_DATA = "unknown_limited_data"


class ReportState(str, Enum):
    FULL = "full_evaluated_report"
    PARTIAL = "partial_evaluated_report"
    TECHNICAL_ONLY = "technical_only_evaluated_report"
    INSUFFICIENT = "insufficient_data_for_scoring"


class UniversalFactorScore(BaseModel):
    name: str
    score: float | None = Field(default=None, ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    eligible_weight: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []
    excluded_metrics: list[str] = []


class UniversalScoreCard(BaseModel):
    instrument_id: str | None = None
    ticker: str
    company_type: CompanyType
    overall_score: float | None = Field(default=None, ge=0, le=100)
    confidence: str  # "Low" | "Medium" | "High"
    confidence_score: float = Field(ge=0, le=1)
    data_coverage_pct: float = Field(ge=0, le=100)
    report_state: ReportState
    factors: list[UniversalFactorScore] = []
    policy_version: str
    excluded_factor_notes: list[str] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_domain.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/__init__.py src/mbe/universal/domain.py tests/test_universal_domain.py
git commit -m "feat(universal): add Universal Research Score domain types"
```

---

## Task 2: Company-type classification

**Files:**
- Create: `src/mbe/universal/classification.py`
- Test: `tests/test_universal_classification.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_classification.py
from mbe.universal.classification import classify_company_type
from mbe.universal.domain import CompanyType


def test_bank_detected_from_industry_keyword():
    assert classify_company_type("Financial Services", "Banks—Regional") == CompanyType.BANK
    assert classify_company_type("Financial Services", "Banks—Diversified") == CompanyType.BANK


def test_insurance_detected_from_industry_keyword():
    assert classify_company_type("Financial Services", "Insurance—Life") == CompanyType.INSURANCE


def test_nbfc_detected_from_credit_services():
    assert classify_company_type("Financial Services", "Credit Services") == CompanyType.NBFC


def test_asset_management_detected():
    assert classify_company_type("Financial Services", "Asset Management") == CompanyType.ASSET_MANAGEMENT


def test_other_financial_is_conservative_default_for_unmatched_financial_industry():
    assert classify_company_type("Financial Services", "Financial Data & Stock Exchanges") == CompanyType.OTHER_FINANCIAL
    assert classify_company_type("Financial Services", None) == CompanyType.OTHER_FINANCIAL


def test_general_corporate_for_non_financial_sector():
    assert classify_company_type("Technology", "Software—Application") == CompanyType.GENERAL_CORPORATE
    assert classify_company_type("Industrials", "Specialty Industrial Machinery") == CompanyType.GENERAL_CORPORATE


def test_unknown_limited_data_when_no_sector_or_industry():
    assert classify_company_type(None, None) == CompanyType.UNKNOWN_LIMITED_DATA
    assert classify_company_type("", "") == CompanyType.UNKNOWN_LIMITED_DATA


def test_case_insensitive_matching():
    assert classify_company_type("financial services", "BANKS—REGIONAL") == CompanyType.BANK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_classification.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/classification.py
"""Deterministic company-type classification for the Universal Research
Score's company-type-aware scoring policy (mbe.universal.policy).

No cleaner company-type taxonomy exists anywhere in this repository (see
2026-08-04 audit): mbe.search.classification is source-provenance
reconciliation for raw sector/industry strings, not a type taxonomy, and
mbe.scoring.sector_themes explicitly keys off the same raw Yahoo strings
for descriptive-only theme matching. This module is a small, explicit
keyword table — not a fuzzy classifier — so every classification decision
is auditable. Real limitation, disclosed rather than hidden: Yahoo's
industry taxonomy is the only signal available; a company with an
unusual or missing industry string may be classified conservatively as
other_financial or unknown_limited_data rather than guessed precisely.
"""

from __future__ import annotations

from mbe.universal.domain import CompanyType

_BANK_KEYWORDS = ("bank",)
_INSURANCE_KEYWORDS = ("insurance",)
_NBFC_KEYWORDS = ("credit services",)
_ASSET_MANAGEMENT_KEYWORDS = ("asset management",)


def classify_company_type(sector: str | None, industry: str | None) -> CompanyType:
    sector_l = (sector or "").strip().lower()
    industry_l = (industry or "").strip().lower()

    if not sector_l and not industry_l:
        return CompanyType.UNKNOWN_LIMITED_DATA
    if sector_l != "financial services":
        return CompanyType.GENERAL_CORPORATE
    if any(keyword in industry_l for keyword in _BANK_KEYWORDS):
        return CompanyType.BANK
    if any(keyword in industry_l for keyword in _INSURANCE_KEYWORDS):
        return CompanyType.INSURANCE
    if any(keyword in industry_l for keyword in _NBFC_KEYWORDS):
        return CompanyType.NBFC
    if any(keyword in industry_l for keyword in _ASSET_MANAGEMENT_KEYWORDS):
        return CompanyType.ASSET_MANAGEMENT
    return CompanyType.OTHER_FINANCIAL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_classification.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/classification.py tests/test_universal_classification.py
git commit -m "feat(universal): add deterministic company-type classifier"
```

---

## Task 3: Additive benchmark for net margin

**Files:**
- Create: `src/mbe/universal/benchmarks.py`
- Test: `tests/test_universal_benchmarks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_benchmarks.py
from mbe.universal.benchmarks import score_net_margin


def test_net_margin_thresholds():
    assert score_net_margin(0.20) == (90, ">= 0.15 earns 90")
    assert score_net_margin(0.12) == (75, ">= 0.10 earns 75")
    assert score_net_margin(0.07) == (60, ">= 0.05 earns 60")
    assert score_net_margin(0.01) == (40, ">= 0.00 earns 40")
    assert score_net_margin(-0.05) == (10, "negative net margin, floor 10")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_benchmarks.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/benchmarks.py
"""Additive benchmark table(s) for metrics the Universal Research Score
scores that mbe.scoring.benchmarks does not define a threshold for.
Kept in a separate module — never edits mbe.scoring.benchmarks — so the
existing Multibagger/Investment score stays byte-identical (a hard
compatibility requirement of this feature)."""

from __future__ import annotations

NET_MARGIN_THRESHOLDS: list[tuple[float, int]] = [
    (0.15, 90), (0.10, 75), (0.05, 60), (0.0, 40),
]


def score_net_margin(value: float) -> tuple[int, str]:
    for threshold, points in NET_MARGIN_THRESHOLDS:
        if value >= threshold:
            return points, f">= {threshold:.2f} earns {points}"
    return 10, "negative net margin, floor 10"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_benchmarks.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/benchmarks.py tests/test_universal_benchmarks.py
git commit -m "feat(universal): add net-margin benchmark table"
```

---

## Task 4: Universal scoring policy — factor definitions and weights

**Files:**
- Create: `src/mbe/universal/policy.py`
- Test: `tests/test_universal_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_policy.py
import pytest

from mbe.universal.domain import CompanyType
from mbe.universal.policy import (
    FACTOR_WEIGHTS, MIN_COVERAGE_FULL, MIN_COVERAGE_PARTIAL,
    UNIVERSAL_SCORE_POLICY_VERSION, factors_for_company_type,
    score_universal_metric,
)


def test_policy_version_is_stamped():
    assert UNIVERSAL_SCORE_POLICY_VERSION == "universal-score-v1"


def test_factor_weights_sum_to_one():
    assert sum(FACTOR_WEIGHTS.values()) == pytest.approx(1.0)


def test_factor_weights_cover_the_required_ten_factors():
    expected = {
        "Growth", "Profitability", "Capital efficiency", "Financial strength",
        "Cash-flow quality", "Valuation", "Momentum", "Technical trend",
        "Volatility and risk", "Data quality",
    }
    assert set(FACTOR_WEIGHTS) == expected


def test_general_corporate_includes_capital_efficiency_metric():
    factors = factors_for_company_type(CompanyType.GENERAL_CORPORATE)
    metrics = [m for m, _, _ in factors["Capital efficiency"]]
    assert "roce_3y" in metrics


def test_bank_excludes_industrial_leverage_and_capital_efficiency_metrics():
    factors = factors_for_company_type(CompanyType.BANK)
    assert factors["Capital efficiency"] == []
    strength_metrics = [m for m, _, _ in factors["Financial strength"]]
    assert "debt_to_equity" not in strength_metrics
    assert "net_debt_to_ebitda" not in strength_metrics
    assert "interest_coverage" not in strength_metrics
    # Growth/Profitability/Valuation/Momentum/Technical trend stay intact
    assert [m for m, _, _ in factors["Growth"]] == [m for m, _, _ in factors_for_company_type(CompanyType.GENERAL_CORPORATE)["Growth"]]


@pytest.mark.parametrize("company_type", [
    CompanyType.NBFC, CompanyType.INSURANCE, CompanyType.ASSET_MANAGEMENT,
    CompanyType.OTHER_FINANCIAL,
])
def test_every_financial_type_excludes_the_same_industrial_metrics(company_type):
    factors = factors_for_company_type(company_type)
    assert factors["Capital efficiency"] == []
    strength_metrics = [m for m, _, _ in factors["Financial strength"]]
    assert strength_metrics == ["current_ratio"]


def test_score_universal_metric_dispatches_shared_and_new_metrics():
    points, _ = score_universal_metric("revenue_cagr_3y", 0.30)
    assert points == 95  # reuses mbe.scoring.benchmarks table verbatim
    points, _ = score_universal_metric("net_margin", 0.20)
    assert points == 90  # uses the new universal-only table
    assert score_universal_metric("trend_state", "strong_up") == (95, "trend template: strong_up")
    assert score_universal_metric("trend_state", "unknown") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_policy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/policy.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_policy.py -v`
Expected: PASS (7 passed, with the parametrized test counting as 4)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/policy.py tests/test_universal_policy.py
git commit -m "feat(universal): add centralized versioned scoring policy"
```

---

## Task 5: Universal scoring engine

**Files:**
- Create: `src/mbe/universal/engine.py`
- Test: `tests/test_universal_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_engine.py
import pytest

from mbe.models.analysis import FundamentalMetrics, RiskAssessment, RiskFlag, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo
from mbe.universal.domain import CompanyType, ReportState
from mbe.universal.engine import build_universal_score


def _full_general_inputs():
    info = CompanyInfo(ticker="DIXON.NS", sector="Technology", industry="Electronic Components")
    fund = FundamentalMetrics(
        revenue_cagr_3y=0.28, profit_cagr_3y=0.32, margin_trend=0.02,
        roe_3y=0.22, net_margin=0.06, roce_3y=0.24,
        debt_to_equity=0.4, interest_coverage=12.0, net_debt_to_ebitda=0.8, current_ratio=1.6,
        fcf_margin=0.08, cash_conversion=1.05, accruals_ratio=0.03,
        completeness=0.95,
    )
    tech = TechnicalState(
        relative_strength_63d=0.10, cmf20=0.08, trend_state="up", rsi14=58.0,
        dist_52w_high=-0.08, completeness=0.9,
    )
    val = ValuationResult(margin_of_safety=0.20, peg=1.1, implied_growth=0.18, fcf_yield=0.03, completeness=0.9)
    risk = RiskAssessment(risk_score=20.0, flags=[RiskFlag(code="LOW_LIQUIDITY", severity=1, detail="thin volume")])
    return info, fund, tech, val, risk


def test_full_data_general_corporate_produces_full_report_state_and_score():
    info, fund, tech, val, risk = _full_general_inputs()
    card = build_universal_score("DIXON.NS", info, fund, tech, val, risk)
    assert card.company_type == CompanyType.GENERAL_CORPORATE
    assert card.report_state == ReportState.FULL
    assert card.overall_score is not None
    assert 0 <= card.overall_score <= 100
    assert card.data_coverage_pct > 60
    assert card.confidence in {"Medium", "High"}
    assert card.policy_version == "universal-score-v1"


def test_factor_subscores_reconcile_to_overall_via_stated_weights():
    info, fund, tech, val, risk = _full_general_inputs()
    card = build_universal_score("DIXON.NS", info, fund, tech, val, risk)
    from mbe.universal.policy import FACTOR_WEIGHTS
    # Exclude Data quality meta-factor from reconciliation (it reports coverage %, not company quality)
    scored = [f for f in card.factors if f.confidence > 0 and f.name != "Data quality"]
    total_weight = sum(FACTOR_WEIGHTS[f.name] for f in scored)
    recombined = sum(FACTOR_WEIGHTS[f.name] * f.score for f in scored) / total_weight
    assert card.overall_score == pytest.approx(round(recombined, 1))


def test_missing_fundamentals_never_scores_zero():
    info = CompanyInfo(ticker="XYZ.NS", sector="Technology", industry="Software")
    fund = FundamentalMetrics(completeness=0.0)  # everything None
    tech = TechnicalState(relative_strength_63d=0.05, cmf20=0.02, trend_state="sideways", rsi14=50.0, completeness=0.6)
    val = ValuationResult(completeness=0.0)
    risk = RiskAssessment(risk_score=0.0)
    card = build_universal_score("XYZ.NS", info, fund, tech, val, risk)
    growth = next(f for f in card.factors if f.name == "Growth")
    assert growth.score is None  # never fabricated as 0
    assert growth.confidence == 0.0
    assert card.report_state == ReportState.TECHNICAL_ONLY


def test_no_data_at_all_is_insufficient():
    info = CompanyInfo(ticker="ZZZ.NS")
    fund = FundamentalMetrics(completeness=0.0)
    tech = TechnicalState(completeness=0.0)
    val = ValuationResult(completeness=0.0)
    risk = RiskAssessment(risk_score=0.0)
    card = build_universal_score("ZZZ.NS", info, fund, tech, val, risk)
    assert card.report_state == ReportState.INSUFFICIENT
    assert card.company_type == CompanyType.UNKNOWN_LIMITED_DATA
    # When no data exists at all, overall_score must be None (never fabricated as 0.0)
    assert card.overall_score is None


def test_bank_excludes_capital_efficiency_and_lowers_coverage_and_confidence():
    info = CompanyInfo(ticker="HDFCBANK.NS", sector="Financial Services", industry="Banks—Regional")
    fund = FundamentalMetrics(
        revenue_cagr_3y=0.15, profit_cagr_3y=0.18, margin_trend=0.01,
        roe_3y=0.16, net_margin=0.22, roce_3y=0.02,  # roce_3y present but must be excluded, not scored
        debt_to_equity=8.0, interest_coverage=1.1, net_debt_to_ebitda=5.0, current_ratio=1.1,
        fcf_margin=None, cash_conversion=None, accruals_ratio=None,
        completeness=0.6,
    )
    tech = TechnicalState(relative_strength_63d=0.05, cmf20=0.01, trend_state="up", rsi14=55.0, dist_52w_high=-0.10, completeness=0.9)
    val = ValuationResult(margin_of_safety=0.10, peg=1.5, implied_growth=0.12, fcf_yield=0.02, completeness=0.8)
    risk = RiskAssessment(risk_score=15.0)
    card = build_universal_score("HDFCBANK.NS", info, fund, tech, val, risk)
    assert card.company_type == CompanyType.BANK
    capital_efficiency = next(f for f in card.factors if f.name == "Capital efficiency")
    assert capital_efficiency.score is None
    assert capital_efficiency.confidence == 0.0
    strength = next(f for f in card.factors if f.name == "Financial strength")
    assert "debt_to_equity" not in [e.metric for e in strength.evidence]
    assert any("not meaningful for" in note for note in card.excluded_factor_notes)
    general_info = CompanyInfo(ticker="GENERAL.NS", sector="Technology", industry="Software")
    general_card = build_universal_score("GENERAL.NS", general_info, fund, tech, val, risk)
    assert card.data_coverage_pct < general_card.data_coverage_pct


def test_instrument_id_is_passed_through():
    info, fund, tech, val, risk = _full_general_inputs()
    card = build_universal_score("DIXON.NS", info, fund, tech, val, risk, instrument_id="abc-123")
    assert card.instrument_id == "abc-123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/engine.py
"""Universal Research Score engine: combines factor scores into an overall
score, coverage percentage, confidence and report state. Reuses the exact
renormalized-weighted-mean pattern mbe.scoring.pillars.build_pillar and
mbe.scoring.engine.combine already use — missing data is excluded and
weight renormalized within each factor, never scored as zero."""

from __future__ import annotations

from mbe.models.analysis import FundamentalMetrics, RiskAssessment, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo
from mbe.models.scoring import Evidence
from mbe.universal.classification import classify_company_type
from mbe.universal.domain import CompanyType, ReportState, UniversalFactorScore, UniversalScoreCard
from mbe.universal.policy import (
    FACTOR_WEIGHTS, FINANCIAL_COMPANY_TYPES, MIN_COVERAGE_FULL, MIN_COVERAGE_PARTIAL,
    UNIVERSAL_SCORE_POLICY_VERSION, factors_for_company_type, score_universal_metric,
)


def _combined_values(fund: FundamentalMetrics, tech: TechnicalState, val: ValuationResult) -> dict:
    delivered = fund.profit_cagr_3y if fund.profit_cagr_3y is not None else fund.revenue_cagr_3y
    implied_growth_gap = None
    if val.implied_growth is not None and delivered is not None:
        implied_growth_gap = val.implied_growth - delivered
    return {
        "revenue_cagr_3y": fund.revenue_cagr_3y,
        "profit_cagr_3y": fund.profit_cagr_3y,
        "margin_trend": fund.margin_trend,
        "roe_3y": fund.roe_3y if fund.roe_3y is not None else fund.roe,
        "net_margin": fund.net_margin,
        "roce_3y": fund.roce_3y if fund.roce_3y is not None else fund.roce,
        "debt_to_equity": fund.debt_to_equity,
        "interest_coverage": fund.interest_coverage,
        "net_debt_to_ebitda": fund.net_debt_to_ebitda,
        "current_ratio": fund.current_ratio,
        "fcf_margin": fund.fcf_margin,
        "cash_conversion": fund.cash_conversion,
        "accruals_ratio": fund.accruals_ratio,
        "margin_of_safety": val.margin_of_safety,
        "peg": val.peg,
        "implied_growth_gap": implied_growth_gap,
        "fcf_yield": val.fcf_yield,
        "relative_strength_63d": tech.relative_strength_63d,
        "cmf20": tech.cmf20,
        "trend_state": tech.trend_state if tech.trend_state != "unknown" else None,
        "rsi14": tech.rsi14,
        "dist_52w_high": tech.dist_52w_high,
    }


def _build_factor(name: str, items: list[tuple[str, float, str]], values: dict) -> UniversalFactorScore:
    evidence: list[Evidence] = []
    weighted_points = 0.0
    weight_present = 0.0
    excluded: list[str] = []
    for metric, weight, rationale in items:
        value = values.get(metric)
        if value is None:
            excluded.append(metric)
            continue
        scored = score_universal_metric(metric, value)
        if scored is None:
            excluded.append(metric)
            continue
        points, benchmark = scored
        evidence.append(Evidence(
            metric=metric, value=round(value, 6) if isinstance(value, float) else value,
            benchmark=benchmark, points=points, weight=weight, rationale=rationale,
        ))
        weighted_points += weight * points
        weight_present += weight
    score = weighted_points / weight_present if weight_present > 0 else None
    return UniversalFactorScore(
        name=name, score=score, confidence=weight_present,
        eligible_weight=weight_present, evidence=evidence, excluded_metrics=excluded,
    )


def _risk_factor(risk: RiskAssessment, data_confidence: float) -> UniversalFactorScore:
    score = max(0.0, 100.0 - risk.risk_score)
    evidence = [
        Evidence(
            metric=f"risk_flag:{flag.code}", value=flag.severity, benchmark=flag.detail,
            points=max(0, 100 - flag.severity * 30), weight=0.0, rationale=flag.detail,
        )
        for flag in risk.flags
    ]
    return UniversalFactorScore(
        name="Volatility and risk", score=score, confidence=data_confidence,
        eligible_weight=data_confidence, evidence=evidence,
    )


def _report_state(coverage_fraction: float, has_financials: bool, has_prices: bool) -> ReportState:
    if not has_financials and has_prices:
        return ReportState.TECHNICAL_ONLY
    if not has_financials and not has_prices:
        return ReportState.INSUFFICIENT
    if coverage_fraction >= MIN_COVERAGE_FULL:
        return ReportState.FULL
    if coverage_fraction >= MIN_COVERAGE_PARTIAL:
        return ReportState.PARTIAL
    return ReportState.INSUFFICIENT


def build_universal_score(
    ticker: str,
    info: CompanyInfo,
    fund: FundamentalMetrics,
    tech: TechnicalState,
    val: ValuationResult,
    risk: RiskAssessment,
    *,
    instrument_id: str | None = None,
) -> UniversalScoreCard:
    company_type = classify_company_type(info.sector, info.industry)
    factor_defs = factors_for_company_type(company_type)
    values = _combined_values(fund, tech, val)

    factors = [_build_factor(name, items, values) for name, items in factor_defs.items()]
    data_confidence = (fund.completeness + tech.completeness + val.completeness) / 3
    factors.append(_risk_factor(risk, data_confidence))

    total_possible_weight = sum(FACTOR_WEIGHTS.values())
    non_meta_total = total_possible_weight - FACTOR_WEIGHTS["Data quality"]
    non_meta_scored = sum(
        FACTOR_WEIGHTS[f.name] for f in factors if f.confidence > 0 and f.name != "Data quality"
    )
    coverage_pct = round(100 * non_meta_scored / non_meta_total, 1) if non_meta_total else 0.0

    # Calculate overall_score from real factors only, excluding Data quality meta-factor.
    # When all real factors have zero confidence, overall_score stays None (not fabricated as 0.0).
    scored_weight = sum(FACTOR_WEIGHTS[f.name] for f in factors if f.confidence > 0)
    overall_score = None
    if scored_weight > 0:
        overall_score = round(
            sum(FACTOR_WEIGHTS[f.name] * f.score for f in factors if f.confidence > 0) / scored_weight, 1
        )

    # Append Data quality for reporting (coverage percentage), but it doesn't affect overall_score.
    factors.append(UniversalFactorScore(
        name="Data quality", score=coverage_pct, confidence=1.0, eligible_weight=1.0, evidence=[],
    ))

    has_financials = fund.completeness > 0
    has_prices = tech.completeness > 0
    report_state = _report_state(non_meta_scored / non_meta_total if non_meta_total else 0.0, has_financials, has_prices)

    confidence_score = round(
        0.6 * (coverage_pct / 100) + 0.2 * data_confidence + 0.2 * (1.0 if has_prices else 0.0), 3
    )
    confidence_label = "High" if confidence_score >= 0.7 else "Medium" if confidence_score >= 0.4 else "Low"

    excluded_notes: list[str] = []
    if company_type in FINANCIAL_COMPANY_TYPES:
        excluded_notes.append(
            "Capital-efficiency and leverage metrics (ROCE, debt-to-equity, "
            "net-debt-to-EBITDA, interest coverage) are not meaningful for "
            f"{company_type.value.replace('_', ' ')} companies and were excluded "
            "from scoring, not zeroed."
        )

    return UniversalScoreCard(
        instrument_id=instrument_id, ticker=ticker, company_type=company_type,
        overall_score=overall_score, confidence=confidence_label, confidence_score=confidence_score,
        data_coverage_pct=coverage_pct, report_state=report_state, factors=factors,
        policy_version=UNIVERSAL_SCORE_POLICY_VERSION, excluded_factor_notes=excluded_notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_engine.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/engine.py src/mbe/universal/policy.py tests/test_universal_engine.py
git commit -m "feat(universal): add Universal Research Score engine"
```

---

## Task 6: Deterministic strengths and risks

**Files:**
- Create: `src/mbe/universal/explanations.py`
- Test: `tests/test_universal_explanations.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_explanations.py
from mbe.models.scoring import Evidence
from mbe.universal.domain import CompanyType, ReportState, UniversalFactorScore, UniversalScoreCard
from mbe.universal.explanations import build_strengths_and_risks


def _card_with_factor(name: str, score: float, confidence: float = 0.9) -> UniversalScoreCard:
    factor = UniversalFactorScore(
        name=name, score=score, confidence=confidence, eligible_weight=confidence,
        evidence=[Evidence(metric="x", value=score, benchmark="b", points=score, weight=1.0, rationale="r")],
    )
    other = UniversalFactorScore(name="Data quality", score=80.0, confidence=1.0, eligible_weight=1.0)
    return UniversalScoreCard(
        ticker="T.NS", company_type=CompanyType.GENERAL_CORPORATE, overall_score=score,
        confidence="High", confidence_score=0.8, data_coverage_pct=80.0,
        report_state=ReportState.FULL, factors=[factor, other], policy_version="universal-score-v1",
    )


def test_high_scoring_factor_becomes_a_strength():
    card = _card_with_factor("Growth", 85.0)
    strengths, risks = build_strengths_and_risks(card)
    assert any("Growth" in s for s in strengths)


def test_low_scoring_factor_becomes_a_risk():
    card = _card_with_factor("Financial strength", 20.0)
    strengths, risks = build_strengths_and_risks(card)
    assert any("Financial strength" in r for r in risks)


def test_low_confidence_factor_is_never_used_as_evidence():
    card = _card_with_factor("Growth", 90.0, confidence=0.1)
    strengths, risks = build_strengths_and_risks(card)
    assert not any("Growth" in s for s in strengths)


def test_mid_scoring_factor_is_neither_strength_nor_risk():
    card = _card_with_factor("Momentum", 55.0)
    strengths, risks = build_strengths_and_risks(card)
    assert not any("Momentum" in s for s in strengths)
    assert not any("Momentum" in r for r in risks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_explanations.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/explanations.py
"""Deterministic, rule-based strengths/risks for the Universal Research
Score. Unlike mbe.research.explanations (which needs a cross-sectional
median over the Nifty Smallcap ranking universe — architecturally
incompatible with "any stock"), this module only ever looks at one
company's own factor scores and evidence — same self-contained approach
mbe.thesis.engine and mbe.analysis.risk already use for a single ticker.
No LLM; every sentence is template text keyed off a scored factor."""

from __future__ import annotations

from mbe.universal.domain import UniversalScoreCard

_STRENGTH_THRESHOLD = 70.0
_RISK_THRESHOLD = 35.0
_MIN_CONFIDENCE_FOR_EVIDENCE = 0.3


def build_strengths_and_risks(card: UniversalScoreCard) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    for factor in card.factors:
        if factor.name == "Data quality" or factor.score is None:
            continue
        if factor.confidence < _MIN_CONFIDENCE_FOR_EVIDENCE:
            continue
        if factor.score >= _STRENGTH_THRESHOLD:
            strengths.append(f"{factor.name} scores {factor.score:.0f}/100, above the strength threshold.")
        elif factor.score <= _RISK_THRESHOLD:
            risks.append(f"{factor.name} scores {factor.score:.0f}/100, below the risk threshold.")
    for note in card.excluded_factor_notes:
        risks.append(note)
    return strengths, risks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_explanations.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/explanations.py tests/test_universal_explanations.py
git commit -m "feat(universal): add deterministic strengths/risks generator"
```

---

## Task 7: Report payload builder

**Files:**
- Create: `src/mbe/universal/report.py`
- Test: `tests/test_universal_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_report.py
from datetime import datetime, timezone

from mbe.models.analysis import FundamentalMetrics, RiskAssessment, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo
from mbe.universal.engine import build_universal_score
from mbe.universal.report import FORBIDDEN_REPORT_KEYS, build_universal_report


def _card():
    info = CompanyInfo(ticker="DIXON.NS", sector="Technology", industry="Electronic Components")
    fund = FundamentalMetrics(revenue_cagr_3y=0.28, profit_cagr_3y=0.32, roe_3y=0.22, net_margin=0.06,
                               roce_3y=0.24, debt_to_equity=0.4, interest_coverage=12.0,
                               net_debt_to_ebitda=0.8, current_ratio=1.6, fcf_margin=0.08,
                               cash_conversion=1.05, accruals_ratio=0.03, completeness=0.95)
    tech = TechnicalState(relative_strength_63d=0.10, cmf20=0.08, trend_state="up", rsi14=58.0,
                           dist_52w_high=-0.08, completeness=0.9)
    val = ValuationResult(margin_of_safety=0.20, peg=1.1, implied_growth=0.18, fcf_yield=0.03, completeness=0.9)
    risk = RiskAssessment(risk_score=20.0)
    return build_universal_score("DIXON.NS", info, fund, tech, val, risk, instrument_id="dixon-id")


def test_report_contains_every_required_section():
    card = _card()
    report = build_universal_report(card, generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
    required_sections = {
        "executive_summary", "company_identity", "universal_score", "factor_breakdown",
        "business_and_financial_quality", "growth", "profitability", "capital_efficiency",
        "balance_sheet_strength", "cash_flow_quality", "valuation", "technical_trend",
        "momentum", "volatility_and_risk", "strengths", "risks", "data_quality_notes",
        "methodology", "source_lineage",
    }
    assert required_sections <= set(report)


def test_report_never_contains_a_forecast_or_recommendation_section():
    card = _card()
    report = build_universal_report(card, generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
    for key in FORBIDDEN_REPORT_KEYS:
        assert key not in report


def test_methodology_section_carries_policy_version():
    card = _card()
    report = build_universal_report(card, generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert report["methodology"]["policy_version"] == "universal-score-v1"


def test_source_lineage_carries_generated_timestamp():
    card = _card()
    when = datetime(2026, 8, 4, 18, 30, tzinfo=timezone.utc)
    report = build_universal_report(card, generated_at=when)
    assert report["source_lineage"]["generated_at"] == when.isoformat()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/report.py
"""Deterministic Universal Research Score report payload. Template-driven,
no LLM. Deliberately excludes System A's (mbe.report.markdown) 3-Year
Price Forecast, Entry & Exit Framework and Position Sizing sections —
those generate scenario price targets and trading guidance, which
conflicts with this feature's explicit "no fabricated price targets or
recommendations" constraint. FORBIDDEN_REPORT_KEYS below is asserted
against directly by tests so that constraint cannot silently regress."""

from __future__ import annotations

from datetime import datetime

from mbe.universal.domain import UniversalScoreCard
from mbe.universal.explanations import build_strengths_and_risks

FORBIDDEN_REPORT_KEYS = ("price_forecast", "entry_exit_framework", "position_sizing", "price_target")


def _factor(card: UniversalScoreCard, name: str) -> dict:
    factor = next((f for f in card.factors if f.name == name), None)
    if factor is None:
        return {"available": False}
    return {
        "available": factor.score is not None,
        "score": factor.score,
        "confidence": round(factor.confidence, 3),
        "evidence": [e.model_dump(mode="json") for e in factor.evidence],
        "excluded_metrics": factor.excluded_metrics,
    }


def build_universal_report(card: UniversalScoreCard, *, generated_at: datetime) -> dict:
    strengths, risks = build_strengths_and_risks(card)
    return {
        "executive_summary": {
            "overall_score": card.overall_score,
            "confidence": card.confidence,
            "data_coverage_pct": card.data_coverage_pct,
            "report_state": card.report_state.value,
            "company_type": card.company_type.value,
        },
        "company_identity": {"ticker": card.ticker, "instrument_id": card.instrument_id, "company_type": card.company_type.value},
        "universal_score": {
            "overall_score": card.overall_score,
            "confidence": card.confidence,
            "confidence_score": card.confidence_score,
            "data_coverage_pct": card.data_coverage_pct,
        },
        "factor_breakdown": [
            {"name": f.name, "score": f.score, "confidence": round(f.confidence, 3)} for f in card.factors
        ],
        "business_and_financial_quality": _factor(card, "Profitability"),
        "growth": _factor(card, "Growth"),
        "profitability": _factor(card, "Profitability"),
        "capital_efficiency": _factor(card, "Capital efficiency"),
        "balance_sheet_strength": _factor(card, "Financial strength"),
        "cash_flow_quality": _factor(card, "Cash-flow quality"),
        "valuation": _factor(card, "Valuation"),
        "technical_trend": _factor(card, "Technical trend"),
        "momentum": _factor(card, "Momentum"),
        "volatility_and_risk": _factor(card, "Volatility and risk"),
        "strengths": strengths,
        "risks": risks,
        "data_quality_notes": {
            "coverage_pct": card.data_coverage_pct,
            "excluded_factor_notes": card.excluded_factor_notes,
        },
        "methodology": {
            "policy_version": card.policy_version,
            "company_type_policy": card.company_type.value,
            "factor_weights_note": "See docs/universal-research-score-architecture.md for the full weight table.",
        },
        "source_lineage": {"generated_at": generated_at.isoformat()},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_report.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/report.py tests/test_universal_report.py
git commit -m "feat(universal): add deterministic report payload builder"
```

---

## Task 8: Pipeline orchestration

**Files:**
- Create: `src/mbe/universal/pipeline.py`
- Test: `tests/test_universal_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_pipeline.py
import pandas as pd
import pytest

from mbe.data.provider import ProviderError
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.universal.pipeline import analyze_universal


class _StubProvider:
    def __init__(self, *, fail: bool = False):
        self._fail = fail

    def get_info(self, ticker):
        if self._fail:
            raise ProviderError("no data")
        return CompanyInfo(ticker=ticker, sector="Technology", industry="Software", market_cap=5e10)

    def get_financials(self, ticker):
        years = {2023: 100.0, 2024: 130.0, 2025: 170.0}
        return FinancialHistory(data={
            "revenue": years, "net_income": {y: v * 0.1 for y, v in years.items()},
            "cfo": {y: v * 0.12 for y, v in years.items()}, "capex": {y: -v * 0.04 for y, v in years.items()},
            "fcf": {y: v * 0.08 for y, v in years.items()}, "total_equity": {y: v * 0.5 for y, v in years.items()},
            "total_debt": {y: v * 0.1 for y, v in years.items()}, "cash": {y: v * 0.2 for y, v in years.items()},
            "total_assets": {y: v * 0.9 for y, v in years.items()},
            "current_assets": {y: v * 0.4 for y, v in years.items()},
            "current_liabilities": {y: v * 0.2 for y, v in years.items()},
            "interest_expense": {y: v * 0.01 for y, v in years.items()},
            "shares_diluted": {y: 1_000_000.0 for y in years},
        })

    def get_prices(self, ticker, years=3):
        idx = pd.bdate_range("2023-01-01", periods=260)
        df = pd.DataFrame({"close": [100 + i * 0.1 for i in range(len(idx))]}, index=idx)
        return PriceHistory(ticker=ticker, df=df)

    def benchmark_ticker(self, ticker):
        return "^NSEI"


def test_analyze_universal_returns_a_score_for_any_ticker():
    card = analyze_universal("MADEUP.NS", _StubProvider())
    assert card.ticker == "MADEUP.NS"
    assert card.overall_score is not None


def test_analyze_universal_tolerates_missing_benchmark():
    class _NoBenchmark(_StubProvider):
        def benchmark_ticker(self, ticker):
            raise ProviderError("no index data")

    card = analyze_universal("MADEUP.NS", _NoBenchmark())
    assert card.overall_score is not None  # relative strength just becomes unavailable


def test_analyze_universal_propagates_provider_error_for_unknown_ticker():
    with pytest.raises(ProviderError):
        analyze_universal("NOPE.NS", _StubProvider(fail=True))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/pipeline.py
"""Universal Research Score orchestration: ticker -> provider data ->
existing metric engines -> Universal Research Score. Deliberately mirrors
mbe.pipeline.analyze_ticker's shape (same provider calls, same
graceful-benchmark-failure handling) since that function already proved
this exact orchestration works for an arbitrary ticker — this module
reuses it rather than re-deriving it, just swapping
mbe.scoring.engine.build_scorecard for mbe.universal.engine.build_universal_score."""

from __future__ import annotations

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.risk import assess_risk
from mbe.analysis.technicals import compute_technicals
from mbe.analysis.valuation import compute_valuation
from mbe.data.provider import DataProvider, ProviderError
from mbe.universal.domain import UniversalScoreCard
from mbe.universal.engine import build_universal_score


def analyze_universal(
    ticker: str, provider: DataProvider, *, instrument_id: str | None = None,
) -> UniversalScoreCard:
    info = provider.get_info(ticker)
    fin = provider.get_financials(ticker)
    prices = provider.get_prices(ticker)

    benchmark = None
    try:
        benchmark = provider.get_prices(provider.benchmark_ticker(ticker))
    except ProviderError:
        pass

    fund = compute_fundamentals(fin, info)
    tech = compute_technicals(prices, benchmark)
    price = prices.last_close() or info.price or 0.0
    val = compute_valuation(fin, info, fund, price)
    risk = assess_risk(fin, fund, tech, val, info)

    return build_universal_score(ticker, info, fund, tech, val, risk, instrument_id=instrument_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_pipeline.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/pipeline.py tests/test_universal_pipeline.py
git commit -m "feat(universal): add per-ticker orchestration pipeline"
```

---

## Task 9: Cache-key hashing and JSON artifact I/O

**Files:**
- Create: `src/mbe/universal/cache.py`
- Test: `tests/test_universal_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universal_cache.py
import json

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
import pandas as pd

from mbe.universal.cache import cache_key_for, read_cached_report, write_cached_report


def _snapshot():
    info = CompanyInfo(ticker="DIXON.NS", sector="Technology")
    fin = FinancialHistory(data={"revenue": {2024: 100.0}})
    prices = PriceHistory(ticker="DIXON.NS", df=pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2024-01-01", periods=1)))
    return info, fin, prices


def test_cache_key_is_deterministic_for_identical_inputs():
    info, fin, prices = _snapshot()
    key1 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    key2 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    assert key1 == key2
    assert len(key1) == 64  # sha256 hex digest


def test_cache_key_changes_when_policy_version_changes():
    info, fin, prices = _snapshot()
    key1 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    key2 = cache_key_for(info, fin, prices, policy_version="universal-score-v2")
    assert key1 != key2


def test_cache_key_changes_when_financial_data_changes():
    info, fin, prices = _snapshot()
    key1 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    fin2 = FinancialHistory(data={"revenue": {2024: 200.0}})
    key2 = cache_key_for(info, fin2, prices, policy_version="universal-score-v1")
    assert key1 != key2


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "abc-123.json"
    payload = {"instrument_id": "abc-123", "cache_key": "deadbeef", "report": {"a": 1}}
    write_cached_report(path, payload)
    loaded = read_cached_report(path)
    assert loaded == payload
    assert json.loads(path.read_text()) == payload


def test_read_missing_artifact_returns_none(tmp_path):
    assert read_cached_report(tmp_path / "missing.json") is None


def test_read_cached_report_rejects_stale_cache_key(tmp_path):
    path = tmp_path / "abc-123.json"
    write_cached_report(path, {"instrument_id": "abc-123", "cache_key": "old-key", "report": {}})
    loaded = read_cached_report(path, expected_cache_key="new-key")
    assert loaded is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_cache.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/mbe/universal/cache.py
"""Source-data-hash + policy-version cache keys, and JSON artifact
read/write for the Universal Research Score refresh pipeline. A cache hit
means the underlying financial/price snapshot and the scoring policy are
both byte-identical to what produced the cached report — anything else
(a new financial period, a metric formula fix, a policy version bump)
invalidates it deterministically."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory


def cache_key_for(
    info: CompanyInfo, fin: FinancialHistory, prices: PriceHistory, *, policy_version: str,
) -> str:
    payload = {
        "policy_version": policy_version,
        "info": info.model_dump(mode="json"),
        "financials": fin.model_dump(mode="json"),
        "last_close": prices.last_close(),
        "price_rows": len(prices.df),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_cached_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def read_cached_report(path: Path, *, expected_cache_key: str | None = None) -> dict | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if expected_cache_key is not None and payload.get("cache_key") != expected_cache_key:
        return None
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_cache.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/cache.py tests/test_universal_cache.py
git commit -m "feat(universal): add source-hash cache keys and artifact I/O"
```

---

## Task 10: Bounded, resumable refresh CLI

**Files:**
- Create: `scripts/build_universal_scores.py`
- Test: `tests/test_build_universal_scores.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_universal_scores.py
import json

from mbe.data.provider import ProviderError

from scripts.build_universal_scores import RefreshOutcome, run_refresh


class _StubProvider:
    def __init__(self, fail_tickers=()):
        self._fail_tickers = set(fail_tickers)

    def get_info(self, ticker):
        if ticker in self._fail_tickers:
            raise ProviderError("boom")
        from mbe.models.company import CompanyInfo
        return CompanyInfo(ticker=ticker, sector="Technology", market_cap=1e10)

    def get_financials(self, ticker):
        from mbe.models.company import FinancialHistory
        return FinancialHistory(data={"revenue": {2024: 100.0}, "net_income": {2024: 10.0}})

    def get_prices(self, ticker, years=3):
        import pandas as pd
        from mbe.models.company import PriceHistory
        idx = pd.bdate_range("2024-01-01", periods=60)
        return PriceHistory(ticker=ticker, df=pd.DataFrame({"close": [100.0] * len(idx)}, index=idx))

    def benchmark_ticker(self, ticker):
        return "^NSEI"


def test_run_refresh_writes_one_artifact_per_instrument(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}, {"instrument_id": "id-2", "provider_symbol": "BBB.NS"}]
    result = run_refresh(instruments, provider=_StubProvider(), output_dir=tmp_path)
    assert result.succeeded == ["id-1", "id-2"]
    assert result.failed == {}
    assert (tmp_path / "id-1.json").exists()
    assert (tmp_path / "id-2.json").exists()


def test_run_refresh_isolates_per_company_failure(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}, {"instrument_id": "id-2", "provider_symbol": "BAD.NS"}]
    result = run_refresh(instruments, provider=_StubProvider(fail_tickers={"BAD.NS"}), output_dir=tmp_path, retry_backoff_seconds=0)
    assert result.succeeded == ["id-1"]
    assert "id-2" in result.failed
    assert (tmp_path / "id-1.json").exists()
    assert not (tmp_path / "id-2.json").exists()


def test_run_refresh_is_resumable_and_skips_fresh_cache(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}]
    provider = _StubProvider()
    first = run_refresh(instruments, provider=provider, output_dir=tmp_path)
    assert first.succeeded == ["id-1"]

    class _FailIfCalled(_StubProvider):
        def get_info(self, ticker):
            raise AssertionError("should not re-fetch a fresh cache entry")

    second = run_refresh(instruments, provider=_FailIfCalled(), output_dir=tmp_path)
    assert second.succeeded == ["id-1"]
    assert second.skipped_cached == ["id-1"]


def test_run_refresh_retries_a_transient_failure_before_giving_up(tmp_path):
    calls = {"count": 0}

    class _FlakyThenOkProvider(_StubProvider):
        def get_info(self, ticker):
            calls["count"] += 1
            if calls["count"] < 3:
                raise ProviderError("transient")
            return super().get_info(ticker)

    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}]
    result = run_refresh(instruments, provider=_FlakyThenOkProvider(), output_dir=tmp_path, max_retries=3, retry_backoff_seconds=0)
    assert result.succeeded == ["id-1"]
    assert calls["count"] == 3


def test_run_refresh_gives_up_after_max_retries_and_records_the_failure(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "ALWAYS_FAILS.NS"}]
    result = run_refresh(
        instruments, provider=_StubProvider(fail_tickers={"ALWAYS_FAILS.NS"}), output_dir=tmp_path,
        max_retries=2, retry_backoff_seconds=0,
    )
    assert result.succeeded == []
    assert "id-1" in result.failed


def test_run_refresh_respects_limit(tmp_path):
    instruments = [{"instrument_id": f"id-{i}", "provider_symbol": f"T{i}.NS"} for i in range(5)]
    result = run_refresh(instruments, provider=_StubProvider(), output_dir=tmp_path, limit=2)
    assert len(result.succeeded) == 2


def test_run_refresh_writes_manifest_with_partial_completion_report(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}, {"instrument_id": "id-2", "provider_symbol": "BAD.NS"}]
    run_refresh(instruments, provider=_StubProvider(fail_tickers={"BAD.NS"}), output_dir=tmp_path, retry_backoff_seconds=0)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["succeeded_count"] == 1
    assert manifest["failed_count"] == 1
    assert "id-2" in manifest["failures"]
    assert "generated_at" in manifest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_build_universal_scores.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# scripts/build_universal_scores.py
"""Bounded, resumable Universal Research Score refresh CLI.

Per-company failure isolation (one bad ticker never aborts the batch, same
pattern as mbe.pipeline.screen), retry-with-backoff on transient provider
failures, a cache-key skip for already-fresh entries (resumable — a rerun
only recomputes what changed or previously failed), and a manifest
recording exactly what happened this run (partial-completion reporting,
per the design doc's "bounded universal analysis refresh" requirement).

Deliberately sequential, not concurrent, despite the design doc's "bounded
concurrency (small worker pool)" language: concurrent Yahoo requests from
one process meaningfully raise rate-limit risk (the same risk the original
2026-07-19 live-search-analyze design flagged: "heavy use could get
Vercel's shared IP range rate-limited by Yahoo"), and this CLI runs from a
single developer/CI machine, not serverless, so there is no per-request
latency budget forcing concurrency. `--limit` plus retry-with-backoff
already satisfy "bounded" and "resilient to transient failure" without
that added risk and complexity; revisit only if refresh throughput
becomes a real bottleneck at larger scale.

Usage:
    .venv/bin/python scripts/build_universal_scores.py \
        --instruments universes/verification-set.json \
        --output site/api/v1/universal-scores \
        --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.provider import DataProvider, ProviderError  # noqa: E402
from mbe.universal.cache import cache_key_for, read_cached_report, write_cached_report  # noqa: E402
from mbe.universal.pipeline import analyze_universal  # noqa: E402
from mbe.universal.policy import UNIVERSAL_SCORE_POLICY_VERSION  # noqa: E402
from mbe.universal.report import build_universal_report  # noqa: E402


@dataclass
class RefreshOutcome:
    succeeded: list[str] = field(default_factory=list)
    skipped_cached: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def _fetch_with_retry(provider: DataProvider, ticker: str, *, max_retries: int, backoff_seconds: float):
    """Returns (info, fin, prices) or raises the last ProviderError after
    exhausting retries. A fresh transient failure (e.g. a dropped
    connection) gets up to `max_retries` attempts with linear backoff;
    a systematically bad ticker still fails after the same bounded number
    of attempts, so one bad company can never hang the batch."""
    last_error: ProviderError | None = None
    for attempt in range(1, max_retries + 1):
        try:
            info = provider.get_info(ticker)
            fin = provider.get_financials(ticker)
            prices = provider.get_prices(ticker)
            return info, fin, prices
        except ProviderError as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)
    raise last_error


def run_refresh(
    instruments: list[dict],
    *,
    provider: DataProvider,
    output_dir: Path,
    limit: int | None = None,
    max_retries: int = 3,
    retry_backoff_seconds: float = 2.0,
) -> RefreshOutcome:
    outcome = RefreshOutcome()
    output_dir = Path(output_dir)
    processed = 0
    for record in instruments:
        if limit is not None and processed >= limit:
            break
        processed += 1
        instrument_id = record["instrument_id"]
        ticker = record["provider_symbol"]
        artifact_path = output_dir / f"{instrument_id}.json"
        try:
            info, fin, prices = _fetch_with_retry(
                provider, ticker, max_retries=max_retries, backoff_seconds=retry_backoff_seconds,
            )
        except ProviderError as exc:
            outcome.failed[instrument_id] = str(exc)
            continue

        key = cache_key_for(info, fin, prices, policy_version=UNIVERSAL_SCORE_POLICY_VERSION)
        cached = read_cached_report(artifact_path, expected_cache_key=key)
        if cached is not None:
            outcome.succeeded.append(instrument_id)
            outcome.skipped_cached.append(instrument_id)
            continue

        try:
            card = analyze_universal(ticker, provider, instrument_id=instrument_id)
        except ProviderError as exc:
            outcome.failed[instrument_id] = str(exc)
            continue
        except Exception as exc:  # one bad ticker must never abort the batch
            outcome.failed[instrument_id] = f"unexpected: {exc!r}"
            continue

        generated_at = datetime.now(timezone.utc)
        report = build_universal_report(card, generated_at=generated_at)
        payload = {
            "instrument_id": instrument_id, "cache_key": key,
            "policy_version": UNIVERSAL_SCORE_POLICY_VERSION,
            "generated_at": generated_at.isoformat(), "report": report,
        }
        write_cached_report(artifact_path, payload)
        outcome.succeeded.append(instrument_id)

    manifest = {
        "policy_version": UNIVERSAL_SCORE_POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "succeeded_count": len(outcome.succeeded),
        "skipped_cached_count": len(outcome.skipped_cached),
        "failed_count": len(outcome.failed),
        "failures": outcome.failed,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return outcome


def _load_instruments(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instruments", type=Path, required=True, help="JSON list of {instrument_id, provider_symbol}")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    from mbe.data.yahoo import YahooProvider
    provider = YahooProvider(cache=None)
    instruments = _load_instruments(args.instruments)
    outcome = run_refresh(instruments, provider=provider, output_dir=args.output, limit=args.limit)
    print(json.dumps({
        "succeeded": len(outcome.succeeded), "skipped_cached": len(outcome.skipped_cached),
        "failed": len(outcome.failed), "failure_detail": outcome.failed,
    }, indent=2))
    return 0 if not outcome.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_build_universal_scores.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/build_universal_scores.py tests/test_build_universal_scores.py
git commit -m "feat(universal): add bounded resumable refresh CLI"
```

---

## Task 11: Universal-scores artifact summary loader

**Files:**
- Modify: `src/mbe/universal/cache.py`
- Test: `tests/test_universal_cache.py`

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
# append to tests/test_universal_cache.py
from mbe.universal.cache import load_universal_scores_summary


def test_load_universal_scores_summary_reads_every_artifact_except_manifest(tmp_path):
    (tmp_path / "id-1.json").write_text(json.dumps({
        "instrument_id": "id-1", "cache_key": "k1", "policy_version": "universal-score-v1",
        "report": {"executive_summary": {
            "overall_score": 72.5, "confidence": "Medium", "data_coverage_pct": 65.0,
            "report_state": "full_evaluated_report",
        }},
    }))
    (tmp_path / "manifest.json").write_text(json.dumps({"succeeded_count": 1}))
    summary = load_universal_scores_summary(tmp_path)
    assert summary == {
        "id-1": {
            "overall_score": 72.5, "confidence": "Medium", "data_coverage_pct": 65.0,
            "report_state": "full_evaluated_report", "policy_version": "universal-score-v1",
        }
    }


def test_load_universal_scores_summary_on_missing_directory_returns_empty(tmp_path):
    assert load_universal_scores_summary(tmp_path / "does-not-exist") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_universal_cache.py -v -k summary`
Expected: FAIL with `ImportError: cannot import name 'load_universal_scores_summary'`

- [ ] **Step 3: Append the implementation to `src/mbe/universal/cache.py`**

```python
def load_universal_scores_summary(artifacts_dir: Path) -> dict[str, dict]:
    """Reads every pre-warmed artifact in artifacts_dir into the small
    summary shape mbe.search.catalog.build_search_index needs — never the
    full report payload (that stays lazily loaded per company page)."""
    summary: dict[str, dict] = {}
    if not artifacts_dir.exists():
        return summary
    for path in sorted(artifacts_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = read_cached_report(path)
        if not payload:
            continue
        exec_summary = payload.get("report", {}).get("executive_summary", {})
        summary[payload["instrument_id"]] = {
            "overall_score": exec_summary.get("overall_score"),
            "confidence": exec_summary.get("confidence"),
            "data_coverage_pct": exec_summary.get("data_coverage_pct"),
            "report_state": exec_summary.get("report_state"),
            "policy_version": payload.get("policy_version"),
        }
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_universal_cache.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mbe/universal/cache.py tests/test_universal_cache.py
git commit -m "feat(universal): add artifact-directory summary loader for search integration"
```

---

## Task 12: Search-index integration — new fields on `SearchIndexRecord`

The 2026-08-04 integration audit confirms `SearchIndexRecord` lives in
`src/mbe/search/domain.py` (lines 51-114) and `build_search_index()` in
`src/mbe/search/catalog.py` (lines 48-176) has one per-record loop (lines
135-176) that is already the single join point where every record —
regardless of which of the three source branches it came from — gets its
`assess_coverage()` fields set. This is the correct place to also set the
new universal fields, keyed by `instrument_id` from the summary dict Task
11 produces.

**Files:**
- Modify: `src/mbe/search/domain.py` (add fields to `SearchIndexRecord`)
- Modify: `src/mbe/search/catalog.py` (add `universal_scores` param and set
  the new fields inside the existing per-record loop)
- Test: `tests/test_search_catalog.py` (existing file — add new test
  functions; read the file first to match its existing fixture-building
  helpers rather than duplicating them)

- [ ] **Step 1: Read `tests/test_search_catalog.py` first**

Run: `.venv/bin/python -m pytest tests/test_search_catalog.py --collect-only -q`
to see the existing fixture/helper names, then add new tests using the
same helpers (do not invent new fixture-building code if a helper like
`_search_universe_row(...)` or similar already exists in that file).

- [ ] **Step 2: Write the failing test (append to `tests/test_search_catalog.py`, adapting to its existing helper names)**

```python
def test_build_search_index_attaches_universal_score_when_summary_provided():
    rows = [_search_universe_row(instrument_id="id-1")]  # use the file's real existing helper
    universal_scores = {
        "id-1": {
            "overall_score": 61.0, "confidence": "Medium", "data_coverage_pct": 55.0,
            "report_state": "partial_evaluated_report", "policy_version": "universal-score-v1",
        },
    }
    records = build_search_index(rows, universal_scores=universal_scores)
    record = next(r for r in records if r.instrument_id == "id-1")
    assert record.universal_score_available is True
    assert record.universal_score == 61.0
    assert record.universal_confidence == "Medium"
    assert record.universal_data_coverage_pct == 55.0
    assert record.universal_report_state == "partial_evaluated_report"
    assert record.universal_score_policy_version == "universal-score-v1"


def test_build_search_index_leaves_universal_fields_unset_without_summary():
    rows = [_search_universe_row(instrument_id="id-2")]
    records = build_search_index(rows)  # no universal_scores kwarg — must stay backward compatible
    record = next(r for r in records if r.instrument_id == "id-2")
    assert record.universal_score_available is False
    assert record.universal_score is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_search_catalog.py -v -k universal`
Expected: FAIL — `TypeError: build_search_index() got an unexpected keyword argument 'universal_scores'` (or `AttributeError` on `record.universal_score_available`)

- [ ] **Step 4: Add the new fields to `SearchIndexRecord` in `src/mbe/search/domain.py`**

Insert immediately after the existing `coverage_policy_version: str = ""` field (the last field in the Phase 11 Milestone 2A coverage block):

```python
    coverage_policy_version: str = ""

    # Universal Research Score, additive (Phase 11 Milestone 3). Populated
    # only when a pre-warmed artifact exists for this instrument — see
    # mbe.universal.cache.load_universal_scores_summary. Never fabricated;
    # absence means "not yet refreshed," not "scored zero."
    universal_score_available: bool = False
    universal_score: float | None = None
    universal_confidence: str | None = None
    universal_data_coverage_pct: float | None = None
    universal_report_state: str | None = None
    universal_score_policy_version: str | None = None
```

- [ ] **Step 5: Add the `universal_scores` parameter to `build_search_index()` in `src/mbe/search/catalog.py`**

Change the signature (around line 48-54) from:

```python
def build_search_index(
    search_universe_rows: list[dict[str, Any]],
    research_instruments: list[dict[str, Any]] | None = None,
    screener_rows: list[dict[str, Any]] | None = None,
    *,
    bse_rows: list[dict[str, Any]] | None = None,
) -> list[SearchIndexRecord]:
```

to:

```python
def build_search_index(
    search_universe_rows: list[dict[str, Any]],
    research_instruments: list[dict[str, Any]] | None = None,
    screener_rows: list[dict[str, Any]] | None = None,
    *,
    bse_rows: list[dict[str, Any]] | None = None,
    universal_scores: dict[str, dict[str, Any]] | None = None,
) -> list[SearchIndexRecord]:
```

Then inside the existing per-record loop (the one that already calls
`assess_coverage(...)` and sets `record.financial_available`,
`record.research_coverage_level`, etc. — around lines 135-176), add
immediately after the last `record.coverage_policy_version = assessment.coverage_policy_version`
line:

```python
        universal = (universal_scores or {}).get(record.instrument_id)
        if universal:
            record.universal_score_available = True
            record.universal_score = universal.get("overall_score")
            record.universal_confidence = universal.get("confidence")
            record.universal_data_coverage_pct = universal.get("data_coverage_pct")
            record.universal_report_state = universal.get("report_state")
            record.universal_score_policy_version = universal.get("policy_version")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_search_catalog.py -v`
Expected: PASS, including the two new tests and every pre-existing test in
the file (confirms the new kwarg is truly additive/backward compatible)

- [ ] **Step 7: Commit**

```bash
git add src/mbe/search/domain.py src/mbe/search/catalog.py tests/test_search_catalog.py
git commit -m "feat(universal): thread Universal Research Score fields through the search index"
```

---

## Task 13: `api/company.py` — serve a Universal Research Score for Levels 0-2

`api/company.py`'s `render_company()` currently hard-codes
`has_model_score=False` (confirmed in the file) and its own docstring says
it "never" computes a score. This task adds a Universal Research Score
attempt — pre-warmed artifact first, live on-demand fallback second — for
any instrument with `coverage.quote_available` true, without touching the
existing coverage-level logic (`assess_coverage` itself is untouched).

**Files:**
- Modify: `api/company.py`
- Modify: `src/mbe/research/coverage.py` (`build_coverage_research` gains
  an optional `universal` payload passthrough)
- Modify: `src/mbe/publish.py` (`render_coverage_company_page` gains an
  optional `universal` param and passes it through)
- Test: `tests/test_company_fn.py` (existing file covering `api/company.py`
  — read it first for its existing fixture/index-building helpers)

- [ ] **Step 1: Read the existing test file for `api/company.py`**

Run: `.venv/bin/python -m pytest tests/test_company_fn.py --collect-only -q`
to find its exact fixture-building helpers (likely something like
`_record(...)`) before writing new tests, so the new tests reuse them
rather than duplicating fixture construction.

- [ ] **Step 2: Write the failing test (append to `tests/test_company_fn.py`, adapted to its real helpers)**

```python
def test_render_company_uses_a_prewarmed_universal_artifact_when_present(tmp_path):
    from mbe.universal.cache import write_cached_report
    index = [_record(instrument_id="id-1", provider_symbol="AAA.NS", research_available=False)]
    artifacts_dir = tmp_path / "universal-scores"
    write_cached_report(artifacts_dir / "id-1.json", {
        "instrument_id": "id-1", "cache_key": "k1", "policy_version": "universal-score-v1",
        "generated_at": "2026-08-04T00:00:00+00:00",
        "report": {"executive_summary": {
            "overall_score": 70.0, "confidence": "Medium", "data_coverage_pct": 60.0,
            "report_state": "full_evaluated_report", "company_type": "general_corporate",
        }},
    })
    status, html = render_company(
        "id-1", index=index, quote_fetcher=lambda symbol: _SAMPLE_CHART,
        universal_artifacts_dir=artifacts_dir, universal_provider=_FailIfCalledProvider(),
    )
    assert status == 200
    assert "70.0" in html or "70" in html  # rendered from the artifact, not live-computed


def test_render_company_falls_back_to_live_computation_when_no_artifact(tmp_path):
    index = [_record(instrument_id="id-2", provider_symbol="BBB.NS", research_available=False)]
    status, html = render_company(
        "id-2", index=index, quote_fetcher=lambda symbol: _SAMPLE_CHART,
        universal_artifacts_dir=tmp_path / "empty",
        universal_provider=_StubUniversalProvider(),
    )
    assert status == 200
    assert "Universal Research" in html


def test_render_company_never_computes_universal_score_without_a_provider_symbol(tmp_path):
    index = [_record(instrument_id="id-3", provider_symbol=None, research_available=False)]
    status, html = render_company(
        "id-3", index=index, universal_artifacts_dir=tmp_path,
        universal_provider=_FailIfCalledProvider(),
    )
    assert status == 200  # no exception raised — the fail-if-called provider was never touched
```

(`_FailIfCalledProvider`/`_StubUniversalProvider`/`_SAMPLE_CHART` are new
small test doubles to add near the top of `tests/test_company_fn.py`,
matching the shape of `_StubProvider` in `tests/test_universal_pipeline.py`
from Task 8 — a `get_info`/`get_financials`/`get_prices`/`benchmark_ticker`
object, with `_FailIfCalledProvider.get_info` raising `AssertionError`.)

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_company_fn.py -v -k universal`
Expected: FAIL — `TypeError: render_company() got an unexpected keyword argument 'universal_artifacts_dir'`

- [ ] **Step 4: Modify `src/mbe/research/coverage.py`**

```python
def build_coverage_research(
    record: dict,
    quote: dict | None,
    coverage: CoverageAssessment,
    financial_summary: dict | None = None,
    *,
    universal: dict | None = None,
    now: datetime | None = None,
) -> dict:
    if coverage.research_coverage_level >= 3:
        raise ValueError(
            "build_coverage_research refuses a Level 3 assessment — that "
            "company must use mbe.research.builder.build_company_research instead."
        )
    payload = build_lightweight_research(record, quote, now=now)
    payload["coverage"] = coverage.model_dump(mode="json")
    payload["financial_summary"] = (
        financial_summary if coverage.research_coverage_level >= 2 else None
    )
    payload["universal"] = universal
    return payload
```

- [ ] **Step 5: Modify `render_coverage_company_page` in `src/mbe/publish.py`**

```python
def render_coverage_company_page(
    record: dict, quote: dict | None, coverage: CoverageAssessment,
    financial_summary: dict | None = None, *, universal: dict | None = None,
) -> str:
    payload = build_coverage_research(record, quote, coverage, financial_summary, universal=universal)
    identity = payload["identity"]
    canonical_path = payload["canonical_url"]
    context = _base_context(
        title=f"{identity['display_name']} ({identity['symbol']}) | Multibagger Engine",
        description=(
            f"Company identity and live quote for {identity['display_name']}. "
            f"{coverage.source_quality_summary}"
        ),
        path=canonical_path, active_route="rankings", asset_prefix="/assets", root_href="/",
    )
    context["canonical_url"] = f"{PUBLIC_SITE_URL}{canonical_path}"
    return _ENV.get_template("company_coverage.html").render(**context, company=payload)
```

- [ ] **Step 6: Modify `api/company.py`**

Add two new imports and a new `_universal_payload` helper, then thread it
through `render_company`:

```python
from mbe.universal.cache import load_universal_scores_summary, read_cached_report, write_cached_report  # noqa: E402
from mbe.universal.pipeline import analyze_universal  # noqa: E402
from mbe.universal.policy import UNIVERSAL_SCORE_POLICY_VERSION  # noqa: E402
from mbe.universal.report import build_universal_report  # noqa: E402

_DEFAULT_UNIVERSAL_ARTIFACTS_DIR = _ROOT / "site" / "api" / "v1" / "universal-scores"


def _default_universal_provider():
    from mbe.data.yahoo import YahooProvider
    return YahooProvider(cache=None)


def _universal_payload(
    instrument_id: str, provider_symbol: str | None, *,
    artifacts_dir: Path, provider,
) -> dict | None:
    if not provider_symbol:
        return None
    artifact_path = artifacts_dir / f"{instrument_id}.json"
    cached = read_cached_report(artifact_path)
    if cached is not None:
        return cached["report"]
    try:
        from datetime import datetime, timezone as tz
        card = analyze_universal(provider_symbol, provider, instrument_id=instrument_id)
        report = build_universal_report(card, generated_at=datetime.now(tz.utc))
    except Exception as exc:
        _log("universal_score_failure", instrument_id=instrument_id, error_type=type(exc).__name__)
        return None
    return report
```

Then change `render_company`'s signature and body:

```python
def render_company(
    instrument_id: str, *, index: list[dict] | None = None, quote_fetcher=None,
    universal_artifacts_dir: Path | None = None, universal_provider=None,
) -> tuple[int, str]:
    """Returns (http_status, html). Pure function — directly unit-testable
    with an injected index and quote fetcher, same shape as api/analyze.py."""
    if not instrument_id or not _ID_RE.match(instrument_id):
        return 400, "<h1>Invalid instrument ID</h1>"
    records = index if index is not None else _load_index()
    record = next((row for row in records if row.get("instrument_id") == instrument_id), None)
    if record is None:
        return 404, "<h1>No matching listed company.</h1>"
    if record.get("research_available"):
        _log("company_fallback_hit_modeled_instrument", instrument_id=instrument_id)
        return 404, "<h1>This company's research page is temporarily unavailable. Please retry.</h1>"
    coverage = assess_coverage(
        record, has_financial_data=bool(record.get("financial_available")),
        has_model_score=False, has_full_research_payload=False,
    )
    quote = None
    if coverage.quote_available:
        fetcher = quote_fetcher or YahooChartQuoteProvider()._fetch
        quote = _fetch_quote(record.get("provider_symbol"), fetcher)
    universal = None
    if coverage.quote_available:
        universal = _universal_payload(
            instrument_id, record.get("provider_symbol"),
            artifacts_dir=universal_artifacts_dir or _DEFAULT_UNIVERSAL_ARTIFACTS_DIR,
            provider=universal_provider or _default_universal_provider(),
        )
    html = render_coverage_company_page(record, quote, coverage, universal=universal)
    return 200, html
```

Add `Cache-Control` note: leave the existing handler's
`"Cache-Control": "s-maxage=300, stale-while-revalidate=600"` header
unchanged — it already covers the whole page (identity + quote +
Universal section together), so no separate header is needed for the new
section.

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_company_fn.py -v`
Expected: PASS, including every pre-existing test in the file

- [ ] **Step 8: Commit**

```bash
git add api/company.py src/mbe/research/coverage.py src/mbe/publish.py tests/test_company_fn.py
git commit -m "feat(universal): serve Universal Research Score on coverage-fallback company pages"
```

---

## Task 14: `company_coverage.html` — render the Universal Research Score section

**Files:**
- Modify: `src/mbe/frontend/templates/company_coverage.html`
- Test: `tests/test_publish_coverage.py` (existing file — read first for
  its fixture-building pattern)

- [ ] **Step 1: Write the failing test**

```python
def test_coverage_page_renders_universal_score_section_when_available():
    coverage = _sample_coverage(level=1)  # use the file's existing helper
    universal = {
        "executive_summary": {
            "overall_score": 70.0, "confidence": "Medium", "data_coverage_pct": 60.0,
            "report_state": "full_evaluated_report", "company_type": "general_corporate",
        },
        "strengths": ["Growth scores 82/100, above the strength threshold."],
        "risks": [],
        "data_quality_notes": {"coverage_pct": 60.0, "excluded_factor_notes": []},
        "methodology": {"policy_version": "universal-score-v1", "company_type_policy": "general_corporate"},
        "source_lineage": {"generated_at": "2026-08-04T18:30:00+00:00"},
    }
    html = render_coverage_company_page(_sample_record(), _sample_quote(), coverage, universal=universal)
    assert "Universal Research Score" in html
    assert "70" in html
    assert "This company is not currently included in a validated universe ranking" in html


def test_coverage_page_shows_not_yet_refreshed_when_universal_is_none():
    coverage = _sample_coverage(level=1)
    html = render_coverage_company_page(_sample_record(), _sample_quote(), coverage, universal=None)
    assert "not yet been refreshed" in html or "Universal Research Report available" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_publish_coverage.py -v -k universal`
Expected: FAIL — template renders without the new text (assertion failure, not a crash)

- [ ] **Step 3: Insert a new section into `company_coverage.html`**

Insert immediately after the existing `#scoring-status` section (the "Not
yet evaluated" notice — currently lines 45-49) and before the `#business-description` section:

```html
      {% if company.universal %}
      <section class="panel research-section" aria-labelledby="universal-score">
        <div class="section-heading"><div><p class="eyebrow">Universal Research Score</p><h2 id="universal-score">Universal Research Score: {{ company.universal.executive_summary.overall_score | round(0, 'floor') | int if company.universal.executive_summary.overall_score is not none else 'Unavailable' }}/100</h2></div></div>
        <p class="notice notice-info"><span aria-hidden="true">ℹ</span> Universal Research Report available. This company is not currently included in a validated universe ranking.</p>
        <dl class="metric-strip">
          <div><dt>Confidence</dt><dd>{{ company.universal.executive_summary.confidence }}</dd></div>
          <div><dt>Data coverage</dt><dd>{{ '%.0f%%'|format(company.universal.executive_summary.data_coverage_pct) if company.universal.executive_summary.data_coverage_pct is not none else 'Unavailable' }}</dd></div>
          <div><dt>Report state</dt><dd>{{ company.universal.executive_summary.report_state | replace('_', ' ') | title }}</dd></div>
          <div><dt>Company type</dt><dd>{{ company.universal.executive_summary.company_type | replace('_', ' ') | title }}</dd></div>
        </dl>
        {% if company.universal.strengths %}
        <h3>Strengths</h3>
        <ul>{% for item in company.universal.strengths %}<li>{{ item }}</li>{% endfor %}</ul>
        {% endif %}
        {% if company.universal.risks %}
        <h3>Risks</h3>
        <ul>{% for item in company.universal.risks %}<li>{{ item }}</li>{% endfor %}</ul>
        {% endif %}
        <p class="cell-note">Universal analysis updated: {{ company.universal.source_lineage.generated_at }} · Model {{ company.universal.methodology.policy_version }}. Not a buy/sell recommendation, guaranteed outcome or price target — see <a href="/methodology.html">methodology</a>.</p>
      </section>
      {% else %}
      <section class="panel research-section" aria-labelledby="universal-score-pending">
        <div class="section-heading"><div><p class="eyebrow">Universal Research Score</p><h2 id="universal-score-pending">Not yet refreshed</h2></div></div>
        <p class="empty-state">A Universal Research Score for this company has not yet been refreshed.</p>
      </section>
      {% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_publish_coverage.py -v`
Expected: PASS, including every pre-existing test in the file

- [ ] **Step 5: Commit**

```bash
git add src/mbe/frontend/templates/company_coverage.html tests/test_publish_coverage.py
git commit -m "feat(universal): render Universal Research Score on coverage-only company pages"
```

---

## Task 15: `company.html` — Universal Research Score as a Level-3 supplement

Level-3 pages read the same pre-warmed artifact directory (via the
already-fresh instrument_id) rather than ever computing live during the
deterministic offline build — this keeps `render_site_from_manifest`'s
`deny_network()` guarantee intact (confirmed by the 2026-08-04 integration
audit: every offline stage asserts `if audit.attempted: raise
AssertionError(...)` after running).

**Files:**
- Modify: `src/mbe/research/builder.py` (`build_company_research()`, whose
  current full signature is:

  ```python
  def build_company_research(
      *, identity: dict, ranking: dict, model_build: dict | None, financial: dict | None,
      technical: dict | None, history: list[dict], peer_candidates: list[dict],
      universe_medians: dict[str, float | None], news: list[dict] | None = None,
      filings: list[dict] | None = None, generated_at: str, data_mode: str = "static",
      quote: dict | None = None,
  ) -> CompanyResearch:
  ```

  gains one more keyword-only param, `universal: dict | None = None`,
  appended after `quote`, and the function stores it on the returned
  payload the same way Task 13 added `payload["universal"] = universal` to
  `build_coverage_research`)
- Modify: `src/mbe/research/static.py` — its `build_static_research(data:
  dict, result: ScreenResult) -> dict[str, dict]` function (confirmed by
  a direct read) is the real call site for all 250 static company pages;
  the call is at line 95:

  ```python
  page = build_company_research(
      identity=normalized_identity,
      ranking=ranking, model_build=build, financial=financial_by_id.get(instrument_id),
      technical=technical, history=history, peer_candidates=candidates,
      universe_medians=medians, news=top.get("news", []), filings=[],
      generated_at=data["built_at"], data_mode="static",
      quote={"price": bundle.tech.price if bundle else None, "currency": bundle.info.currency if bundle else "INR",
             "timestamp": data["built_at"], "state": "build_close", "stale": True},
  )
  ```

  add `universal=_universal_for(instrument_id),` as the next line inside
  that same call, and add the small helper above `build_static_research`:

  ```python
  from pathlib import Path
  from mbe.universal.cache import read_cached_report

  _UNIVERSAL_ARTIFACTS_DIR = Path("site/api/v1/universal-scores")


  def _universal_for(instrument_id: str) -> dict | None:
      cached = read_cached_report(_UNIVERSAL_ARTIFACTS_DIR / f"{instrument_id}.json")
      return cached["report"] if cached else None
  ```

  (Also check `src/mbe/research/operations.py:99` and
  `src/mbe/research/dynamic.py:52` — both call `build_company_research`
  too, for the incremental-rebuild and DB-backed dynamic paths
  respectively. Apply the identical `universal=_universal_for(instrument_id)`
  argument at both call sites for consistency, reusing the same
  `_universal_for` helper — import it from `mbe.research.static` or lift
  it into a shared location such as `mbe.research.lightweight` if that
  reads more naturally once you're looking at all three call sites
  side by side.)
- Modify: `src/mbe/frontend/templates/company.html`
- Test: `tests/test_publish.py` and/or `tests/test_research_static.py` if
  that file exists (check with `ls tests/ | grep -i research` first — the
  integration audit did not confirm which file covers
  `build_static_research` directly)

- [ ] **Step 1: Confirm the exact test file covering `build_static_research`**

Run: `grep -rln "build_static_research" tests/`
Use whichever file(s) it finds for Step 2 below, matching their existing
fixture-building helpers rather than inventing new ones.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_publish.py — add near existing build_company_research/render tests
def test_render_company_page_includes_universal_section_when_artifact_present(tmp_path, monkeypatch):
    from mbe.universal.cache import write_cached_report
    artifacts_dir = tmp_path / "universal-scores"
    write_cached_report(artifacts_dir / "some-instrument-id.json", {
        "instrument_id": "some-instrument-id", "cache_key": "k", "policy_version": "universal-score-v1",
        "generated_at": "2026-08-04T00:00:00+00:00",
        "report": {"executive_summary": {
            "overall_score": 81.0, "confidence": "High", "data_coverage_pct": 92.0,
            "report_state": "full_evaluated_report", "company_type": "general_corporate",
        }},
    })
    # Use whatever fixture this file already uses to build a minimal research
    # payload for one of the 250 (read the file's existing tests for the
    # pattern), then call _render_company_page(research) after attaching
    # research["universal"] via the real load path, and assert "81" appears.
```

(This step intentionally stays adaptive — write it using the file's real
existing `research` payload fixture rather than fabricating one, since
`build_company_research`'s exact required inputs weren't fully captured by
the audit. The assertion shape (artifact present → score text appears in
rendered HTML) is the same as Task 14's; reuse Task 14's finished template
pattern as the reference.)

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_publish.py -v -k universal`
(substitute the real file found in Step 1 if different)
Expected: FAIL (missing text in rendered HTML)

- [ ] **Step 4: Wire `universal` through `build_company_research` and its three call sites**

Apply exactly the code already specified in this task's **Files** section
above: add `universal: dict | None = None` to
`build_company_research(...)` in `src/mbe/research/builder.py` (storing it
as `payload["universal"] = universal`, same key name as Task 13/14 so the
template partial can be shared), add the `_universal_for()` helper and
`universal=_universal_for(instrument_id)` argument to the call site in
`src/mbe/research/static.py:95`, and apply the same argument at the
`build_company_research` calls in `src/mbe/research/operations.py:99` and
`src/mbe/research/dynamic.py:52`.

- [ ] **Step 5: Add the same section markup to `company.html`**

Insert the identical `{% if company.universal %}...{% else %}...{% endif %}`
block from Task 14 Step 3 into `company.html`'s `research-main` column
(e.g. immediately after `#research-summary`), using `research.universal`
instead of `company.universal` as the variable prefix (match whichever
top-level context variable name `company.html` already uses for its
payload — confirmed in the audit as `research` for the quote block, so use
`research.universal` here for consistency with the rest of that template).

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_publish.py -v`
Expected: PASS, including every pre-existing test in the file

- [ ] **Step 7: Commit**

```bash
git add src/mbe/research/builder.py src/mbe/publish.py src/mbe/frontend/templates/company.html tests/test_publish.py
git commit -m "feat(universal): supplement Level-3 research pages with the Universal Research Score"
```

---

## Task 16: Frontend search — stop the `/api/analyze` fallback, surface Universal Score

**Files:**
- Modify: `src/mbe/frontend/assets/app.js`
- Modify: `src/mbe/frontend/assets/screener.js`
- Test: `tests/frontend/app.test.js`, `tests/frontend/screener.test.js`
  (existing files — read first for exact test structure)

- [ ] **Step 1: Write the failing test (add to `tests/frontend/app.test.js`, matching its existing test style)**

```javascript
test("reportDestination always resolves to the canonical company route, never /api/analyze", () => {
  const item = { instrument_id: "abc-123", symbol: "RELIANCE", exchange: "NSE" };
  expect(reportDestination(item)).toBe("/company/abc-123.html");
});

test("reportDestination with no instrument_id and no report_url still avoids /api/analyze", () => {
  const item = { symbol: "RELIANCE", exchange: "NSE" };
  expect(reportDestination(item)).not.toMatch(/\/api\/analyze/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run check` (or the file's specific test runner invocation — see
`package.json`'s `test` script)
Expected: FAIL — the second test fails because the current fallback still
returns an `/api/analyze?ticker=...` URL when `instrument_id` is absent

- [ ] **Step 3: Update `reportDestination()` in `src/mbe/frontend/assets/app.js`**

Every search-universe record already carries a valid `instrument_id` (per
`nse-search-universe.json`/`bse-search-universe.json` covering all
~2,947 companies — confirmed in the 2026-08-04 audit, which found the
`/api/analyze` branch is "effectively dead code in the live search UX").
Simplify to always resolve to the canonical route, with the ticker-query
form only as a last-resort defensive fallback (never network-facing,
since it should be unreachable in practice):

```javascript
  function reportDestination(item) {
    if (item.report_url) return item.report_url;
    if (/^[A-Za-z0-9-]{1,80}$/.test(String(item.instrument_id || ""))) return `/company/${item.instrument_id}.html`;
    return "/"; // defensive fallback only — every real search-universe item carries instrument_id
  }
```

- [ ] **Step 4: Apply the identical change to `reportDestination()` in `src/mbe/frontend/assets/screener.js`**

```javascript
  function reportDestination(row) { if (row.report_url) return row.report_url; if (/^[A-Za-z0-9-]{1,80}$/.test(String(row.instrument_id || ""))) return `/company/${row.instrument_id}.html`; return "/"; }
```

- [ ] **Step 5: Add Universal Score fields to the search result object in `staticSearch()` (`app.js`)**

In the `matches.push({...})` object literal (the one the audit quoted in
full), add these four lines alongside the existing
`research_coverage_level`/`coverage_label` fields:

```javascript
        universal_score_available: Boolean(item.universal_score_available),
        universal_score: item.universal_score == null ? null : Number(item.universal_score),
        universal_confidence: item.universal_confidence || null,
        universal_data_coverage_pct: item.universal_data_coverage_pct == null ? null : Number(item.universal_data_coverage_pct),
```

- [ ] **Step 6: Show a Universal Score badge in `renderItems()`'s result row (`app.js`)**

Immediately after the existing `main.append(create("span", "search-name", ...), researchBadge(item));`
line, add:

```javascript
        if (item.universal_score_available) {
          const label = `Universal ${Math.round(item.universal_score)} · ${item.universal_confidence}`;
          main.append(create("span", "badge badge-info", label));
        }
```

- [ ] **Step 7: Run test to verify it passes**

Run: `npm run check`
Expected: PASS — ESLint, TypeScript `checkJs`, and every Node test
(including the two new ones) pass

- [ ] **Step 8: Commit**

```bash
git add src/mbe/frontend/assets/app.js src/mbe/frontend/assets/screener.js tests/frontend/app.test.js tests/frontend/screener.test.js
git commit -m "feat(universal): resolve search results to the canonical route and surface Universal Score badges"
```

---

## Task 17: Release-artifact tracking — `offline.py` and `verify_release.py`

The universal-scores artifact directory is a variable-size, incrementally-
grown set (unlike every other fixed-count artifact in
`scripts/verify_release.py`'s `EXPECTED` dict), so it needs its own
consistency check rather than being folded into the generic `json` file
count.

**Files:**
- Modify: `src/mbe/builds/offline.py` (`_output_hashes()`)
- Modify: `scripts/verify_release.py`
- Test: `tests/test_deterministic_build.py` (existing file)

- [ ] **Step 1: Read `_output_hashes()` in full in `src/mbe/builds/offline.py`**

Confirm how it currently handles a `candidates` entry whose path may not
exist in every build (e.g. `financials`/`research`) before adding a new
entry, so the new entry follows the same existence-handling.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_deterministic_build.py — add near the existing
# test_quote_refresh_ui_does_not_change_score_financial_or_membership_hashes
def test_verify_release_excludes_universal_scores_from_the_fixed_json_count(tmp_path):
    from scripts.verify_release import EXPECTED
    # universal-scores is a variable-size, incrementally-grown artifact set —
    # it must never be folded into the fixed EXPECTED["json"] literal, or
    # every refresh run would break the release verifier.
    out = tmp_path / "site"
    render_site_from_manifest(MANIFEST, out)
    build_search_only(MANIFEST, out, write_manifest=False)
    build_coverage_only(MANIFEST, out)
    (out / "api/v1/universal-scores").mkdir(parents=True)
    (out / "api/v1/universal-scores/some-id.json").write_text("{}")
    json_paths = [p for p in out.rglob("*.json") if "universal-scores" not in p.parts]
    assert len(json_paths) == EXPECTED["json"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_deterministic_build.py -v -k universal_scores_from_the_fixed`
Expected: FAIL if `scripts/verify_release.py`'s json-counting `rglob`
call doesn't yet exclude `universal-scores` (confirms the gap exists
before fixing it)

- [ ] **Step 4: Update `scripts/verify_release.py`'s JSON-count check**

Find the line computing `json_paths` (around line 63-66, using
`site.rglob("*.json")`) and exclude the new directory:

```python
    json_paths = [p for p in site.rglob("*.json") if "universal-scores" not in p.parts]
```

Add a new, separate consistency check (not a fixed count) right after the
existing `EXPECTED` comparison block:

```python
    universal_dir = site / "api/v1/universal-scores"
    if universal_dir.exists():
        manifest_path = universal_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            artifact_count = len([p for p in universal_dir.glob("*.json") if p.name != "manifest.json"])
            if artifact_count != manifest["succeeded_count"]:
                errors.append(
                    f"universal-scores artifact count {artifact_count} does not match "
                    f"manifest succeeded_count {manifest['succeeded_count']}"
                )
```

- [ ] **Step 5: Add a `universal_scores` entry to `_output_hashes()` in `src/mbe/builds/offline.py`**, following whatever existence-handling pattern Step 1 found for optional directories like `financials`/`research`.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_deterministic_build.py -v`
Expected: PASS, including every pre-existing determinism/hash test in the
file (this is the critical regression gate — any failure here means a
compatibility guarantee broke)

- [ ] **Step 7: Commit**

```bash
git add src/mbe/builds/offline.py scripts/verify_release.py tests/test_deterministic_build.py
git commit -m "fix(universal): exclude variable-size universal-scores artifacts from the fixed release-verifier JSON count"
```

---

## Task 18: Compatibility guard — pin the verification-set Universal scores

**Files:**
- Create: `tests/fixtures/phase11-m3-universal-score-hash.json` (written
  by the test itself on first run, exactly like
  `tests/fixtures/phase11-m2b-membership-hash.json` already does)
- Modify: `tests/test_deterministic_build.py`

- [ ] **Step 1: Write the failing test**

```python
def test_universal_score_engine_output_is_pinned_for_the_verification_set():
    """Guards against silent scoring-policy drift. Not a network test —
    uses the mbe.universal.pipeline.analyze_universal path with a fixed,
    checked-in stub provider fixture (see conftest or a small inline stub),
    matching the tests/test_universal_pipeline.py::_StubProvider pattern
    from Task 8, so this test never touches the network and stays fast
    and deterministic in CI."""
    from mbe.universal.pipeline import analyze_universal
    # Reuse the exact _StubProvider class from tests/test_universal_pipeline.py
    # (import it directly rather than redefining) for a small fixed set of
    # tickers standing in for the verification set.
    from tests.test_universal_pipeline import _StubProvider
    tickers = ["AAA.NS", "BBB.NS", "CCC.NS"]
    results = {
        t: {
            "overall_score": analyze_universal(t, _StubProvider()).overall_score,
            "confidence": analyze_universal(t, _StubProvider()).confidence,
            "report_state": analyze_universal(t, _StubProvider()).report_state.value,
        }
        for t in tickers
    }
    fixture_path = ROOT / "tests/fixtures/phase11-m3-universal-score-hash.json"
    if not fixture_path.exists():
        fixture_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    assert results == json.loads(fixture_path.read_text())
```

- [ ] **Step 2: Run test to verify it fails, then passes on the second run**

Run: `.venv/bin/python -m pytest tests/test_deterministic_build.py -v -k universal_score_engine_output`
Expected: first run creates the fixture and passes (matching the existing
membership-hash test's self-seeding pattern); rerun to confirm stability:
`.venv/bin/python -m pytest tests/test_deterministic_build.py -v -k universal_score_engine_output`
Expected: PASS on rerun too

- [ ] **Step 3: Commit**

```bash
git add tests/test_deterministic_build.py tests/fixtures/phase11-m3-universal-score-hash.json
git commit -m "test(universal): pin Universal Research Score engine output against drift"
```

---

## Task 19: Run the bounded refresh for the verification set, update docs, final verification

**Files:**
- Create: `universes/universal-score-verification-set.json`
- Modify: `docs/HANDOVER.md`
- Create: `docs/universal-research-score-architecture.md`

- [ ] **Step 1: Build the verification-set instrument list**

Using the real `site/api/v1/search-index.json` (or the DB, if provisioned
locally), resolve `instrument_id`/`provider_symbol` pairs for: Reliance
Industries, TCS, Infosys, HDFC Bank, ICICI Bank, HAL, BEL, Dixon
Technologies, Polycab India, one SME-listed security, one company with
materially incomplete fundamentals (a thinly-covered small/micro-cap), and
one inactive/unmapped listing (`listing_status` not `active`/`unknown`, or
no `provider_symbol` at all — this one is expected to fail cleanly, not
silently). Write these ~12 records plus roughly 40-90 more (arbitrary
non-Level-3 search-universe companies, for scale) to
`universes/universal-score-verification-set.json` as a JSON list of
`{"instrument_id": ..., "provider_symbol": ...}` objects.

- [ ] **Step 2: Run the refresh CLI**

Run:
```bash
.venv/bin/python scripts/build_universal_scores.py \
  --instruments universes/universal-score-verification-set.json \
  --output site/api/v1/universal-scores
```

Expected: prints a JSON summary with `succeeded`/`skipped_cached`/`failed`
counts; the inactive/unmapped listing should appear in `failed` with an
honest reason, not silently in `succeeded`. Record the exact printed
numbers — they go into the completion report.

- [ ] **Step 3: Rebuild the search index with the new universal-scores summary and rerun the full offline build sequence**

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
from mbe.universal.cache import load_universal_scores_summary
summary = load_universal_scores_summary(Path("site/api/v1/universal-scores"))
print(f"{len(summary)} companies have a fresh Universal Research Score")
EOF
```

Then wire `universal_scores=summary` into whatever calls
`build_search_index(...)` for the real site build (find the call site with
`grep -rn "build_search_index(" scripts/ src/mbe/builds/`), rerun
`scripts/build_search_assets.py` and `scripts/build_coverage_artifact.py`,
and confirm `site/api/v1/search-index.json` now carries
`universal_score_available: true` for the refreshed companies.

- [ ] **Step 4: Run the full verification suite**

```bash
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q src api scripts tests migrations
git diff --check
npm run check
.venv/bin/python scripts/verify_release.py
```

Expected: all pass. If any pre-existing test fails because of this
milestone's changes, fix the root cause before proceeding — do not skip
or weaken a test to make it pass.

- [ ] **Step 5: Write `docs/universal-research-score-architecture.md`**

Following the same documentation shape as `docs/coverage-architecture.md`
and `docs/quote-refresh-architecture.md`: policy version, factor
taxonomy and weights table, company-type policy table, missing-data/
coverage-threshold rules, report-state definitions, routing/caching
decision, refresh-pipeline contract, and the exact
verification-set results from Steps 2-4 (counts, not prose summaries).

- [ ] **Step 6: Update `docs/HANDOVER.md`**

Add a new "Phase 11 Milestone 3 — Universal Research Score" entry using
the file's existing "End-of-phase update template" (near the end of the
file), following the exact structure of the Milestone 2A/2B entries
already in the phase ledger and detail sections. Include: status, date,
objective achieved, main implementation, architecture decisions (link to
the design doc and the new architecture doc), files/modules changed,
database migrations (none), new/changed environment variables (none),
provider/data limitations (per the design doc's "Known limitations"
section), tests run and results (exact numbers from Step 4), build/
deployment result, known limitations, working-tree/commit/deployment
state (local only, not pushed/deployed), and next phase.

- [ ] **Step 7: Final commit**

```bash
git add universes/universal-score-verification-set.json site/api/v1/universal-scores site/api/v1/search-index.json site/data/research-coverage.json docs/universal-research-score-architecture.md docs/HANDOVER.md
git commit -m "docs(universal): record Milestone 3 verification results and architecture"
```

