"""Pillar builders. Each pillar weight-averages its metric scores; missing
metrics are excluded and their weight renormalized, which lowers the pillar's
confidence proportionally. Every included metric leaves an Evidence row."""

from __future__ import annotations

from mbe.models.analysis import FundamentalMetrics, TechnicalState, ValuationResult
from mbe.models.scoring import Evidence, PillarScore
from mbe.scoring.benchmarks import score_metric, score_rsi, score_trend

# (metric, weight, rationale)
_QUALITY = [
    ("roce_3y", 0.30, "High return on capital employed is the engine of compounding"),
    ("roe_3y", 0.20, "Sustained return on equity shows durable shareholder economics"),
    ("fcf_margin", 0.20, "Free-cash-flow margin proves profits arrive as cash"),
    ("cash_conversion", 0.15, "CFO/NI near or above 1 validates earnings quality"),
    ("accruals_ratio", 0.15, "Low accruals mean accounting profit tracks cash reality"),
]
_GROWTH = [
    ("revenue_cagr_3y", 0.35, "Top-line growth is the rawest demand signal"),
    ("profit_cagr_3y", 0.35, "Profit growth shows demand converts to economics"),
    ("margin_trend", 0.15, "Expanding margins signal pricing power or operating leverage"),
    ("fcf_cagr_3y", 0.15, "Growing free cash funds growth without dilution"),
]
_STRENGTH = [
    ("debt_to_equity", 0.30, "Low leverage survives downturns and funds opportunity"),
    ("interest_coverage", 0.25, "Coverage headroom protects equity from creditors"),
    ("net_debt_to_ebitda", 0.25, "Deleveraging capacity in years of cash flow"),
    ("current_ratio", 0.10, "Short-term obligations comfortably met"),
    ("share_count_cagr_3y", 0.10, "No creeping dilution of the owner's stake"),
]
_VALUATION = [
    ("margin_of_safety", 0.40, "Price below conservatively-estimated intrinsic value"),
    ("peg", 0.20, "Price paid per unit of delivered growth"),
    ("implied_growth_gap", 0.20, "Market expectation vs delivered growth — the expectations gap"),
    ("fcf_yield", 0.20, "Cash return earned at today's price"),
]


def build_pillar(name: str, items: list[tuple[str, float, str]], values: dict[str, float | None]) -> PillarScore:
    evidence: list[Evidence] = []
    weighted_points = 0.0
    weight_present = 0.0
    for metric, weight, rationale in items:
        value = values.get(metric)
        if value is None:
            continue
        points, benchmark = score_metric(metric, value)
        evidence.append(
            Evidence(
                metric=metric,
                value=round(value, 6),
                benchmark=benchmark,
                points=points,
                weight=weight,
                rationale=rationale,
            )
        )
        weighted_points += weight * points
        weight_present += weight
    score = weighted_points / weight_present if weight_present > 0 else 0.0
    return PillarScore(
        name=name,
        score=score,
        confidence=weight_present,  # fraction of designed weight that had data
        evidence=evidence,
    )


def quality_pillar(fund: FundamentalMetrics) -> PillarScore:
    values = {m: getattr(fund, m) for m, _, _ in _QUALITY}
    # fall back to single-year ROCE/ROE when 3y averages are unavailable
    if values["roce_3y"] is None:
        values["roce_3y"] = fund.roce
    if values["roe_3y"] is None:
        values["roe_3y"] = fund.roe
    return build_pillar("Quality", _QUALITY, values)


def growth_pillar(fund: FundamentalMetrics) -> PillarScore:
    return build_pillar("Growth", _GROWTH, {m: getattr(fund, m) for m, _, _ in _GROWTH})


def strength_pillar(fund: FundamentalMetrics) -> PillarScore:
    return build_pillar("Financial Strength", _STRENGTH, {m: getattr(fund, m) for m, _, _ in _STRENGTH})


def valuation_pillar(val: ValuationResult, fund: FundamentalMetrics) -> PillarScore:
    delivered = fund.profit_cagr_3y if fund.profit_cagr_3y is not None else fund.revenue_cagr_3y
    gap = None
    if val.implied_growth is not None and delivered is not None:
        gap = val.implied_growth - delivered
    values = {
        "margin_of_safety": val.margin_of_safety,
        "peg": val.peg,
        "implied_growth_gap": gap,
        "fcf_yield": val.fcf_yield,
    }
    return build_pillar("Valuation", _VALUATION, values)


def momentum_pillar(tech: TechnicalState) -> PillarScore:
    evidence: list[Evidence] = []
    weighted_points = 0.0
    weight_present = 0.0

    def add(metric: str, weight: float, scored: tuple[int, str] | None, value, rationale: str):
        nonlocal weighted_points, weight_present
        if scored is None:
            return
        points, benchmark = scored
        evidence.append(
            Evidence(
                metric=metric,
                value=round(value, 6) if isinstance(value, float) else value,
                benchmark=benchmark,
                points=points,
                weight=weight,
                rationale=rationale,
            )
        )
        weighted_points += weight * points
        weight_present += weight

    add(
        "trend_state", 0.30, score_trend(tech.trend_state), tech.trend_state,
        "Stage-2 uptrends are where big moves happen (Minervini template)",
    )
    add(
        "rsi14", 0.15,
        score_rsi(tech.rsi14) if tech.rsi14 is not None else None,
        tech.rsi14, "Momentum health without chasing overbought extremes",
    )
    add(
        "relative_strength_63d", 0.25,
        score_metric("relative_strength_63d", tech.relative_strength_63d)
        if tech.relative_strength_63d is not None else None,
        tech.relative_strength_63d, "Leaders outperform their index before big runs",
    )
    add(
        "dist_52w_high", 0.15,
        score_metric("dist_52w_high", tech.dist_52w_high)
        if tech.dist_52w_high is not None else None,
        tech.dist_52w_high, "Strength near 52-week highs signals accumulation",
    )
    add(
        "cmf20", 0.15,
        score_metric("cmf20", tech.cmf20) if tech.cmf20 is not None else None,
        tech.cmf20, "Positive money flow confirms institutional buying",
    )

    score = weighted_points / weight_present if weight_present > 0 else 0.0
    return PillarScore(
        name="Momentum", score=score, confidence=weight_present, evidence=evidence
    )
