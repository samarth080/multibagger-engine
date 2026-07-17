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
from mbe.scoring.pillars import build_pillar

if TYPE_CHECKING:  # avoid a runtime cycle: pipeline imports this module
    from mbe.pipeline import AnalysisBundle


_OTHER_SUFFIX = " (other)"  # marks a sector-level fallback pool (vs a real industry)


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
            pools.setdefault(f"{b.info.sector}{_OTHER_SUFFIX}", []).append(b)
    for name, members in pools.items():
        if len(members) >= MIN_GROUP:
            groups[name] = members
    return groups


_SECTOR_ITEMS = [
    ("sector_rel_strength_6m", 0.30, "Money moving into the industry over 6 months"),
    ("sector_rel_strength_12m", 0.20, "Sustained 12-month industry leadership"),
    ("sector_rev_accel", 0.30, "Peer revenue growth accelerating: industry demand turning up"),
    ("sector_margin_delta", 0.20, "Peer margins expanding: industry-wide pricing power"),
]


def _median_of(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return float(median(present)) if present else None


def _group_values(
    comps: list[MemberComponents],
    uni_ret_6m: float | None,
    uni_ret_12m: float | None,
) -> dict[str, float | None]:
    med_6m = _median_of([c.ret_6m for c in comps])
    med_12m = _median_of([c.ret_12m for c in comps])
    return {
        "sector_rel_strength_6m": (
            med_6m - uni_ret_6m
            if med_6m is not None and uni_ret_6m is not None else None
        ),
        "sector_rel_strength_12m": (
            med_12m - uni_ret_12m
            if med_12m is not None and uni_ret_12m is not None else None
        ),
        "sector_rev_accel": _median_of([c.rev_accel for c in comps]),
        "sector_margin_delta": _median_of([c.margin_delta for c in comps]),
    }


def compute_sector_scores(bundles: list["AnalysisBundle"]) -> SectorContext:
    """Full-group scores for the sector ranking table, plus everything the
    leave-one-out per-stock pillar needs later."""
    member_data = {b.info.ticker: member_components(b) for b in bundles}
    uni_6m = _median_of([m.ret_6m for m in member_data.values()])
    uni_12m = _median_of([m.ret_12m for m in member_data.values()])
    groups: dict[str, SectorScore] = {}
    membership: dict[str, str] = {}
    for name, members in group_bundles(bundles).items():
        comps = [member_data[b.info.ticker] for b in members]
        pillar = build_pillar(
            "Sector Momentum", _SECTOR_ITEMS, _group_values(comps, uni_6m, uni_12m)
        )
        ranked = sorted(members, key=lambda b: b.card.multibagger_score, reverse=True)
        groups[name] = SectorScore(
            name=name,
            level="sector" if name.endswith(_OTHER_SUFFIX) else "industry",
            n=len(members),
            score=pillar.score,
            confidence=pillar.confidence,
            evidence=pillar.evidence,
            members=[b.info.ticker for b in ranked],
        )
        for b in members:
            membership[b.info.ticker] = name
    return SectorContext(
        groups=groups, membership=membership, member_data=member_data,
        universe_median_ret_6m=uni_6m, universe_median_ret_12m=uni_12m,
    )
