"""Metric -> points mapping tables. Deliberately data, not code, so every
threshold is auditable and can be recalibrated by the backtesting harness
planned for v0.2. Points are 0-100.

Rationale sources: standard quality-investing heuristics — ROCE/ROE tiers per
Indian quality-compounder practice, leverage tiers per credit convention,
valuation tiers anchored on margin-of-safety discipline.
"""

from __future__ import annotations

# value >= threshold (scanning top-down) earns the points
HIGHER_BETTER: dict[str, list[tuple[float, int]]] = {
    "roce_3y": [(0.30, 95), (0.25, 90), (0.20, 75), (0.15, 60), (0.10, 40), (0.05, 20)],
    "roe_3y": [(0.30, 95), (0.25, 90), (0.20, 75), (0.15, 60), (0.10, 40), (0.05, 20)],
    "fcf_margin": [(0.15, 90), (0.10, 75), (0.05, 60), (0.0, 40)],
    "cash_conversion": [(1.2, 95), (1.0, 85), (0.8, 65), (0.6, 45)],
    "revenue_cagr_3y": [(0.25, 95), (0.20, 88), (0.15, 75), (0.10, 60), (0.05, 40), (0.0, 25)],
    "profit_cagr_3y": [(0.25, 95), (0.20, 88), (0.15, 75), (0.10, 60), (0.05, 40), (0.0, 25)],
    "fcf_cagr_3y": [(0.25, 95), (0.20, 88), (0.15, 75), (0.10, 60), (0.05, 40), (0.0, 25)],
    "margin_trend": [(0.03, 90), (0.01, 75), (-0.01, 55), (-0.03, 35)],
    "interest_coverage": [(15, 95), (10, 85), (6, 70), (4, 50), (2, 25)],
    "current_ratio": [(2.0, 90), (1.5, 75), (1.0, 55), (0.8, 30)],
    "margin_of_safety": [(0.5, 95), (0.3, 85), (0.15, 70), (0.0, 55), (-0.15, 35), (-0.3, 20)],
    "fcf_yield": [(0.06, 90), (0.04, 75), (0.02, 55), (0.0, 35)],
    "relative_strength_63d": [(0.15, 90), (0.05, 75), (0.0, 60), (-0.05, 40)],
    "dist_52w_high": [(-0.05, 90), (-0.15, 70), (-0.25, 50), (-0.40, 30)],
    "cmf20": [(0.15, 85), (0.05, 70), (0.0, 55), (-0.10, 35)],
}

# value <= threshold (scanning bottom-up) earns the points
LOWER_BETTER: dict[str, list[tuple[float, int]]] = {
    "accruals_ratio": [(0.0, 90), (0.05, 70), (0.10, 45)],
    "debt_to_equity": [(0.1, 95), (0.3, 85), (0.6, 70), (1.0, 50), (2.0, 25)],
    "net_debt_to_ebitda": [(0.0, 95), (1.0, 85), (2.0, 65), (3.0, 40)],
    "share_count_cagr_3y": [(0.0, 95), (0.02, 75), (0.05, 50), (0.08, 25)],
    "peg": [(0.8, 90), (1.2, 75), (2.0, 55), (3.0, 30)],
    # implied growth minus delivered growth: negative = market underestimates
    "implied_growth_gap": [(-0.05, 90), (0.0, 75), (0.05, 55), (0.10, 35)],
}

FLOOR_POINTS = {"higher": 5, "lower": 10}

TREND_POINTS = {
    "strong_up": 95,
    "up": 75,
    "sideways": 50,
    "down": 25,
    "strong_down": 10,
}


def score_metric(name: str, value: float) -> tuple[int, str]:
    """Points plus a human-readable benchmark string for the evidence trail."""
    if name in HIGHER_BETTER:
        for threshold, points in HIGHER_BETTER[name]:
            if value >= threshold:
                return points, f">= {threshold:.2f} earns {points}"
        return FLOOR_POINTS["higher"], f"below lowest threshold, floor {FLOOR_POINTS['higher']}"
    if name in LOWER_BETTER:
        for threshold, points in LOWER_BETTER[name]:
            if value <= threshold:
                return points, f"<= {threshold:.2f} earns {points}"
        return FLOOR_POINTS["lower"], f"above highest threshold, floor {FLOOR_POINTS['lower']}"
    raise KeyError(f"no benchmark table for metric {name!r}")


def score_rsi(rsi: float) -> tuple[int, str]:
    """Non-monotonic: healthy mid-range beats both extremes."""
    if 45 <= rsi <= 65:
        return 75, "45-65 healthy uptrend zone"
    if 65 < rsi <= 75:
        return 65, "65-75 strong but stretched"
    if 30 <= rsi < 45:
        return 40, "30-45 weak momentum"
    if rsi > 75:
        return 30, ">75 overbought"
    return 25, "<30 oversold / downtrend"


def score_trend(trend_state: str) -> tuple[int, str] | None:
    if trend_state in TREND_POINTS:
        return TREND_POINTS[trend_state], f"trend template: {trend_state}"
    return None


def score_size_runway(market_cap: float, is_india: bool) -> tuple[int, str]:
    """Smaller companies have longer re-rating runway (multibagger pillar)."""
    tiers = (
        [(5e10, 95, "< Rs 5,000 cr small cap"), (2e11, 75, "< Rs 20,000 cr mid cap"),
         (1e12, 50, "< Rs 1 lakh cr large cap"), (5e12, 30, "< Rs 5 lakh cr mega cap")]
        if is_india
        else [(2e9, 95, "< $2B small cap"), (1e10, 75, "< $10B mid cap"),
              (5e10, 50, "< $50B large cap"), (2e11, 30, "< $200B mega cap")]
    )
    for threshold, points, label in tiers:
        if market_cap < threshold:
            return points, label
    return 15, "mega cap — limited multiple-expansion runway"


def score_reinvestment(rate: float) -> tuple[int, str]:
    """Sweet spot: meaningful reinvestment without capex addiction."""
    if 0.3 <= rate <= 0.5:
        return 85, "30-50% of CFO reinvested — healthy growth capex"
    if 0.5 < rate <= 0.7:
        return 70, "50-70% of CFO reinvested — capex heavy"
    if 0.15 <= rate < 0.3:
        return 65, "15-30% reinvested — modest runway usage"
    if rate > 0.7:
        return 45, ">70% of CFO consumed by capex"
    return 40, "<15% reinvested — limited visible growth avenue"
