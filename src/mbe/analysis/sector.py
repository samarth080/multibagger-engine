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
    """Latest YoY revenue growth minus prior YoY growth. Needs 3 years."""
    rev = fin.series("revenue")
    if len(rev) < 3:
        return None
    (_, r0), (_, r1), (_, r2) = rev[-3], rev[-2], rev[-1]
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
