"""Sector rotation & tailwind engine (P2.4).

Cross-sectional by nature: computed as a post-pass over a screened universe,
never inside per-ticker analysis. The per-stock pillar uses leave-one-out
medians so a stock's own momentum can't masquerade as its industry's tailwind
(that is already paid by the Momentum pillar). Signals are relative to the
screened peer set: the same stock gets different sector scores in different
universes, by design.
"""

from __future__ import annotations

from statistics import median
from typing import TYPE_CHECKING

from mbe.models.company import FinancialHistory
from mbe.models.sector import MemberComponents, SectorContext, SectorScore

if TYPE_CHECKING:  # avoid a runtime cycle: pipeline imports this module
    from mbe.pipeline import AnalysisBundle


def revenue_acceleration(fin: FinancialHistory) -> float | None:
    """Latest YoY revenue growth minus prior YoY growth; positive = demand
    accelerating. Needs 3 consecutive fiscal years — a gap year means no
    valid YoY comparison, not a skippable one."""
    by_year = dict(fin.series("revenue"))
    if not by_year:
        return None
    latest = max(by_year)
    y1, y0 = latest - 1, latest - 2
    if y1 not in by_year or y0 not in by_year:
        return None
    r2, r1, r0 = by_year[latest], by_year[y1], by_year[y0]
    if r0 <= 0 or r1 <= 0:
        return None
    return (r2 / r1 - 1) - (r1 / r0 - 1)


def member_components(bundle: "AnalysisBundle") -> MemberComponents:
    return MemberComponents(
        ret_6m=bundle.tech.return_126d,
        ret_12m=bundle.tech.return_252d,
        rev_accel=revenue_acceleration(bundle.fin),
        margin_delta=bundle.fund.margin_trend,
    )


MIN_GROUP = 4  # leave-one-out needs >= 3 peers


def group_bundles(bundles: list["AnalysisBundle"]) -> dict[str, list["AnalysisBundle"]]:
    """Industry groups; members of too-small industries pool into
    '<Sector> (other)'; pools still under MIN_GROUP are dropped (their
    stocks get no sector pillar — honest absence over fake context)."""
    by_industry: dict[str, list["AnalysisBundle"]] = {}
    unassigned: list["AnalysisBundle"] = []
    for b in bundles:
        if b.info.industry:
            by_industry.setdefault(b.info.industry, []).append(b)
        else:
            unassigned.append(b)
    groups: dict[str, list["AnalysisBundle"]] = {}
    for industry, members in by_industry.items():
        if len(members) >= MIN_GROUP:
            groups[industry] = members
        else:
            unassigned.extend(members)
    pools: dict[str, list["AnalysisBundle"]] = {}
    for b in unassigned:
        if b.info.sector:
            pools.setdefault(f"{b.info.sector} (other)", []).append(b)
    for name, members in pools.items():
        if len(members) >= MIN_GROUP:
            groups[name] = members
    return groups
