"""Living Investment Thesis + Self-Critique.

The thesis states, for a business, *why it might compound* and — crucially —
the falsifiable assumptions that must hold, each carrying a probability drawn
from the company's OWN track record. The critique then attempts to reject the
thesis before any recommendation is issued (the discipline the directive
demands: disprove first, recommend last). Deterministic throughout.
"""

from __future__ import annotations

from mbe.models.analysis import (
    BusinessProfile,
    FundamentalMetrics,
    RiskAssessment,
    ValuationResult,
)
from mbe.models.company import CompanyInfo
from mbe.models.thesis import Assumption, Critique, InvestmentThesis


def _level_support(value: float | None, good: float, ok: float, lower_better: bool) -> float:
    """Track-record proxy for metrics where we only have the current level."""
    if value is None:
        return 0.5
    if lower_better:
        if value <= good:
            return 0.9
        if value <= ok:
            return 0.65
        return 0.3
    if value >= good:
        return 0.9
    if value >= ok:
        return 0.65
    return 0.3


def _build_assumptions(
    fund: FundamentalMetrics, business: BusinessProfile
) -> list[Assumption]:
    out: list[Assumption] = []

    if business.roce_consistency is not None:
        out.append(Assumption(
            statement="Sustains a high return on capital (ROCE >= 15%)",
            historical_support=business.roce_consistency,
            currently_true=(fund.roce is not None and fund.roce >= 0.15)
            or (business.roce_median is not None and business.roce_median >= 0.15),
        ))
    if business.growth_positive_years is not None:
        out.append(Assumption(
            statement="Grows revenue over time",
            historical_support=business.growth_positive_years,
            currently_true=(fund.revenue_cagr_3y is not None and fund.revenue_cagr_3y > 0),
        ))
    if business.margin_trajectory is not None:
        traj = business.margin_trajectory
        support = 0.9 if traj >= 0.002 else 0.7 if traj >= -0.002 else 0.4 if traj >= -0.01 else 0.2
        out.append(Assumption(
            statement="Maintains or expands operating margins (pricing power)",
            historical_support=support,
            currently_true=(traj >= -0.005),
        ))
    if business.earnings_quality_track is not None:
        out.append(Assumption(
            statement="Converts accounting profit into cash (CFO/NI >= 0.8)",
            historical_support=business.earnings_quality_track,
            currently_true=(fund.cash_conversion is not None and fund.cash_conversion >= 0.8),
        ))
    if fund.share_count_cagr_3y is not None:
        out.append(Assumption(
            statement="Avoids shareholder dilution",
            historical_support=_level_support(fund.share_count_cagr_3y, 0.01, 0.03, lower_better=True),
            currently_true=(fund.share_count_cagr_3y <= 0.03),
        ))
    if fund.debt_to_equity is not None:
        out.append(Assumption(
            statement="Keeps leverage manageable (debt/equity <= 1)",
            historical_support=_level_support(fund.debt_to_equity, 0.5, 1.0, lower_better=True),
            currently_true=(fund.debt_to_equity <= 1.0),
        ))
    return out


def _bull_pillars(business: BusinessProfile) -> list[str]:
    pillars = []
    if business.roce_consistency is not None and business.roce_consistency >= 0.7:
        pillars.append(
            f"Consistently high returns on capital — ROCE >= 15% in "
            f"{business.roce_consistency:.0%} of the last {business.history_years} years"
        )
    if business.margin_stability is not None and business.margin_stability >= 0.85:
        pillars.append("Stable operating margins, indicating pricing power / a moat")
    if business.incremental_roic is not None and business.incremental_roic >= 0.15:
        pillars.append(
            f"Reinvests at a high incremental return on capital ({business.incremental_roic:.0%})"
        )
    if business.survived_downturn:
        pillars.append("Held revenue and stayed profitable through a past downturn")
    if business.margin_trajectory is not None and business.margin_trajectory > 0.003:
        pillars.append("Operating margins are expanding — improving unit economics")
    if not pillars:
        pillars.append("No standout durable-franchise strengths identified in the record")
    return pillars


def _trajectories(business: BusinessProfile, fund: FundamentalMetrics) -> tuple[str, str, str]:
    cls = business.classification
    g = fund.revenue_cagr_3y
    gtxt = f"{g:.0%}" if g is not None else "its historical rate"
    bull = (
        f"Assumptions hold: a {cls.lower()} that keeps compounding revenue near "
        f"{gtxt} at high incremental returns, widening the moat over a decade."
    )
    base = (
        "Growth moderates toward the industry rate and margins hold; the business "
        "compounds intrinsic value steadily but without multiple re-rating."
    )
    bear = (
        "Key assumptions break — returns on capital fade, margins compress, or "
        "leverage/dilution rises — and the franchise erodes toward a commodity."
    )
    return bull, base, bear


def build_thesis(
    info: CompanyInfo,
    fund: FundamentalMetrics,
    business: BusinessProfile,
    val: ValuationResult,
    risk: RiskAssessment,
) -> InvestmentThesis:
    assumptions = _build_assumptions(fund, business)

    summary = (info.description or "").strip()
    if summary:
        summary = summary[:400] + ("…" if len(summary) > 400 else "")
    else:
        summary = (
            f"{info.name or info.ticker}"
            + (f" — {info.industry}" if info.industry else "")
            + " (no business description available from the data source)."
        )

    falsifiers = [
        f"FALSE if it stops: {a.statement.lower()}"
        for a in assumptions
        if a.historical_support >= 0.5
    ] or ["FALSE if the core economics deteriorate materially"]

    bull, base, bear = _trajectories(business, fund)

    if assumptions:
        mean_support = sum(a.historical_support for a in assumptions) / len(assumptions)
    else:
        mean_support = 0.0
    history_factor = min(business.history_years / 8, 1.0)
    confidence = mean_support * (0.35 + 0.65 * history_factor) * (0.5 + 0.5 * business.completeness)

    return InvestmentThesis(
        ticker=info.ticker,
        business_summary=summary,
        classification=business.classification,
        bull_pillars=_bull_pillars(business),
        assumptions=assumptions,
        falsifiers=falsifiers,
        trajectory_bull=bull,
        trajectory_base=base,
        trajectory_bear=bear,
        thesis_confidence=round(min(1.0, confidence), 3),
    )


def critique_thesis(
    thesis: InvestmentThesis,
    fund: FundamentalMetrics,
    business: BusinessProfile,
    val: ValuationResult,
    risk: RiskAssessment,
) -> Critique:
    """Devil's advocate: enumerate disconfirming evidence, then decide veto."""
    dis: list[str] = []

    for a in thesis.assumptions:
        if not a.currently_true and a.historical_support >= 0.5:
            dis.append(f"A load-bearing assumption is currently false: {a.statement.lower()}")

    if business.classification == "Deteriorating":
        dis.append("Business classified 'Deteriorating' — margins/returns trending down")
    if business.margin_trajectory is not None and business.margin_trajectory < -0.01:
        dis.append(f"Operating margins compressing ({business.margin_trajectory:+.3f}/yr) — moat erosion")
    if fund.debt_to_equity is not None and fund.debt_to_equity > 1.5:
        dis.append(f"Elevated leverage (debt/equity {fund.debt_to_equity:.1f})")
    if fund.share_count_cagr_3y is not None and fund.share_count_cagr_3y > 0.05:
        dis.append(f"Ongoing dilution ({fund.share_count_cagr_3y:.0%}/yr)")
    if fund.accruals_ratio is not None and fund.accruals_ratio > 0.10:
        dis.append(f"Weak earnings quality (accruals ratio {fund.accruals_ratio:.2f})")
    if (
        val.implied_growth is not None and fund.profit_cagr_3y is not None
        and val.implied_growth > 0.20 and val.implied_growth > 2 * max(fund.profit_cagr_3y, 0.01)
    ):
        dis.append(
            f"Valuation demands ~{val.implied_growth:.0%} growth vs {fund.profit_cagr_3y:.0%} delivered"
        )
    if risk.risk_score >= 50:
        dis.append(f"High composite risk score ({risk.risk_score:.0f}/100)")

    veto = (
        business.classification == "Deteriorating"
        or risk.permanent_loss_bucket == "high"
        or (fund.accruals_ratio is not None and fund.accruals_ratio > 0.12)
        or len(dis) >= 4
    )

    if veto:
        reason = dis[0] if dis else "franchise evidence insufficient"
        rec = f"Pass — thesis rejected: {reason}"
    elif thesis.thesis_confidence >= 0.55 and business.franchise_score >= 65 and len(dis) <= 1:
        rec = "Research further — durable-franchise candidate that survived critique"
    elif thesis.thesis_confidence >= 0.4 and len(dis) <= 2:
        rec = "Watch — thesis intact but unproven or awaiting a better price"
    else:
        rec = "Pass — insufficient franchise evidence to underwrite a decade"

    return Critique(disconfirmers=dis, veto=veto, recommendation=rec)
