"""Business-Quality / Franchise-Durability engine.

Phase 2: reason about the whole business trajectory, not one year. These are the
signals long-term investors actually weigh — has this franchise compounded
capital at high rates *consistently*, held pricing power, converted profit to
cash, reinvested at high incremental returns, and survived downturns — over
years. Pure function of the multi-year statement history; nothing imputed.
"""

from __future__ import annotations

import statistics

from mbe.models.analysis import BusinessProfile, FundamentalMetrics
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.scoring import Evidence
from mbe.scoring.benchmarks import score_metric

TAX_RATE = 0.25
ROCE_BAR = 0.15  # "high return on capital" threshold for durability counting


def coefficient_of_variation(values: list[float]) -> float:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0
    mean = statistics.mean(vals)
    if mean == 0:
        return 0.0
    return statistics.pstdev(vals) / abs(mean)


def worst_drawdown(series: list[float]) -> float:
    """Largest peak-to-trough decline (<= 0) across the series."""
    peak = None
    worst = 0.0
    for v in series:
        if peak is None or v > peak:
            peak = v
        if peak and peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def ols_slope(pairs: list[tuple[float, float]]) -> float:
    if len(pairs) < 2:
        return 0.0
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def _roce_series(fin: FinancialHistory) -> list[tuple[int, float]]:
    out = []
    for year, ebit in fin.series("operating_income"):
        equity = fin.value("total_equity", year)
        debt = fin.value("total_debt", year)
        if equity is None or debt is None:
            continue
        cap = equity + debt
        if cap > 0:
            out.append((year, ebit / cap))
    return out


def _op_margin_series(fin: FinancialHistory) -> list[tuple[int, float]]:
    rev = dict(fin.series("revenue"))
    out = []
    for year, op in fin.series("operating_income"):
        if rev.get(year):
            out.append((year, op / rev[year]))
    return out


def incremental_roic(fin: FinancialHistory) -> float | None:
    """Return earned on capital reinvested over the window:
    ΔEBIT·(1-tax) / ΔInvestedCapital, using first & last fully-specified years."""
    usable = []
    for year, ebit in fin.series("operating_income"):
        equity = fin.value("total_equity", year)
        debt = fin.value("total_debt", year)
        cash = fin.value("cash", year)
        if None in (equity, debt, cash):
            continue
        usable.append((year, ebit, equity + debt - cash))
    if len(usable) < 2:
        return None
    _, ebit0, ic0 = usable[0]
    _, ebit1, ic1 = usable[-1]
    if ic1 - ic0 <= 0:
        return None
    return (ebit1 - ebit0) * (1 - TAX_RATE) / (ic1 - ic0)


def _earnings_quality_track(fin: FinancialHistory) -> float | None:
    ni = dict(fin.series("net_income"))
    cfo = dict(fin.series("cfo"))
    common = [y for y in sorted(set(ni) & set(cfo)) if ni[y] > 0]
    if not common:
        return None
    good = sum(1 for y in common if cfo[y] / ni[y] >= 0.8)
    return good / len(common)


def _growth_positive_fraction(fin: FinancialHistory) -> float | None:
    rev = fin.series("revenue")
    if len(rev) < 2:
        return None
    gains = sum(1 for i in range(1, len(rev)) if rev[i][1] > rev[i - 1][1])
    return gains / (len(rev) - 1)


def _classify(
    years: int,
    roce_median: float | None,
    roce_consistency: float | None,
    growth_pos: float | None,
    margin_traj: float | None,
    ever_loss: bool,
) -> str:
    if years < 4:
        return "Unproven"
    traj = margin_traj if margin_traj is not None else 0.0
    if (
        roce_median is not None and roce_median >= 0.18
        and roce_consistency is not None and roce_consistency >= 0.7
        and growth_pos is not None and growth_pos >= 0.6
        and traj >= -0.005
    ):
        return "Durable Compounder"
    if traj < -0.01:
        return "Deteriorating"
    if ever_loss and traj > 0.005:
        return "Turnaround"
    if (
        roce_median is not None and roce_median >= 0.12
        and growth_pos is not None and growth_pos >= 0.55
    ):
        return "Steady"
    return "Cyclical"


def _score_component(name: str, points: float, benchmark: str, weight: float,
                     value, rationale: str) -> Evidence:
    return Evidence(
        metric=name, value=value, benchmark=benchmark,
        points=round(points, 1), weight=weight, rationale=rationale,
    )


def assess_business(
    fin: FinancialHistory, info: CompanyInfo, fund: FundamentalMetrics
) -> BusinessProfile:
    years = fin.years()
    n = len(years)

    roce_ser = _roce_series(fin)
    roce_vals = [r for _, r in roce_ser]
    roce_median = statistics.median(roce_vals) if roce_vals else None
    roce_min = min(roce_vals) if roce_vals else None
    roce_consistency = (
        sum(1 for r in roce_vals if r >= ROCE_BAR) / len(roce_vals) if roce_vals else None
    )

    margin_ser = _op_margin_series(fin)
    margin_stability = (
        max(0.0, 1 - coefficient_of_variation([m for _, m in margin_ser]))
        if len(margin_ser) >= 2 else None
    )
    margin_trajectory = ols_slope(margin_ser) if len(margin_ser) >= 2 else None

    growth_pos = _growth_positive_fraction(fin)
    eq_track = _earnings_quality_track(fin)
    inc_roic = incremental_roic(fin)

    rev_vals = [v for _, v in fin.series("revenue")]
    worst_dd = worst_drawdown(rev_vals) if len(rev_vals) >= 2 else None
    ni_ser = fin.series("net_income")
    ever_loss = any(v < 0 for _, v in ni_ser)
    had_rev_down = worst_dd is not None and worst_dd < -0.02
    survived = had_rev_down and not ever_loss

    classification = _classify(
        n, roce_median, roce_consistency, growth_pos, margin_trajectory, ever_loss
    )

    # ---- franchise score: weighted, evidence-backed, renormalized on gaps ----
    evidence: list[Evidence] = []
    weighted = 0.0
    weight_present = 0.0

    def add(name, weight, points, benchmark, value, rationale):
        nonlocal weighted, weight_present
        evidence.append(_score_component(name, points, benchmark, weight, value, rationale))
        weighted += weight * points
        weight_present += weight

    if roce_median is not None:
        pts, bench = score_metric("roce_3y", roce_median)
        add("roce_durability", 0.25, pts, bench, round(roce_median, 4),
            "Sustained high return on capital is the signature of a franchise")
    if roce_consistency is not None:
        add("roce_consistency", 0.20, 100 * roce_consistency,
            f"{roce_consistency:.0%} of years ROCE>=15%", round(roce_consistency, 3),
            "Compounding requires high returns held year after year, not once")
    if margin_stability is not None:
        add("margin_stability", 0.15, 100 * margin_stability,
            f"stability {margin_stability:.2f}", round(margin_stability, 3),
            "Stable margins signal pricing power and a defensible moat")
    if eq_track is not None:
        add("earnings_quality", 0.15, 100 * eq_track,
            f"{eq_track:.0%} of years CFO/NI>=0.8", round(eq_track, 3),
            "Real franchises turn accounting profit into cash consistently")
    if inc_roic is not None:
        pts, bench = score_metric("roce_3y", inc_roic)  # same tiering as ROCE
        add("incremental_roic", 0.15, pts, bench, round(inc_roic, 4),
            "High returns on reinvested capital are the engine of compounding")
    if worst_dd is not None:
        resilience = max(0.0, min(100.0, 100 + worst_dd * 150)) * (0.6 if ever_loss else 1.0)
        add("resilience", 0.10, resilience,
            f"worst revenue drawdown {worst_dd:.0%}", round(worst_dd, 3),
            "Durable businesses hold revenue and stay profitable through downturns")

    franchise_score = weighted / weight_present if weight_present > 0 else 0.0

    # Forward-looking haircut: a decaying moat is worth less than its history.
    # Great investors weight the trajectory, not just the level.
    if margin_trajectory is not None:
        mult = max(0.55, min(1.10, 1 + margin_trajectory * 10))
        if abs(mult - 1.0) > 0.01:
            evidence.append(_score_component(
                "trajectory_adjustment", franchise_score * mult,
                f"margin trend {margin_trajectory:+.3f}/yr -> x{mult:.2f}",
                0.0, round(margin_trajectory, 4),
                "Expanding margins strengthen a franchise; compressing margins erode it",
            ))
        franchise_score *= mult

    # weights of the 6 real components sum to 1.0, so coverage == completeness
    completeness = min(1.0, weight_present)

    return BusinessProfile(
        history_years=n,
        roce_median=roce_median,
        roce_min=roce_min,
        roce_consistency=roce_consistency,
        growth_positive_years=growth_pos,
        margin_stability=margin_stability,
        margin_trajectory=margin_trajectory,
        earnings_quality_track=eq_track,
        incremental_roic=inc_roic,
        worst_revenue_drawdown=worst_dd,
        ever_lossmaking=ever_loss,
        survived_downturn=survived,
        classification=classification,
        franchise_score=round(franchise_score, 1),
        evidence=evidence,
        completeness=completeness,
    )
