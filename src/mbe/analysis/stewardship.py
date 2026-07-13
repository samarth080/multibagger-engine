"""Management & Capital-Allocation Intelligence (stewardship).

Judges management by what it *did* with owners' money over the full history:
dilution vs buybacks, whether capital was routed to where returns are
(allocation fit), leverage discipline, and cash actually returned. No
narrative inputs — only the auditable capital-allocation record.
"""

from __future__ import annotations

from mbe.models.analysis import BusinessProfile, FundamentalMetrics
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.scoring import Evidence
from mbe.models.stewardship import StewardshipProfile

DILUTION_YEAR = 0.02   # >2% YoY share growth counts as a diluting year
BUYBACK_YEAR = -0.005  # >0.5% shrink counts as a buyback year


def dilution_track(fin: FinancialHistory) -> dict:
    shares = fin.series("shares_diluted")
    if len(shares) < 2:
        return {"share_cagr_full": None, "dilution_years_frac": None,
                "buyback_years_frac": None}
    (y0, s0), (y1, s1) = shares[0], shares[-1]
    cagr = (s1 / s0) ** (1 / (y1 - y0)) - 1 if s0 > 0 and y1 > y0 else None
    changes = [
        shares[i][1] / shares[i - 1][1] - 1
        for i in range(1, len(shares))
        if shares[i - 1][1] > 0
    ]
    return {
        "share_cagr_full": cagr,
        "dilution_years_frac": sum(1 for c in changes if c > DILUTION_YEAR) / len(changes),
        "buyback_years_frac": sum(1 for c in changes if c < BUYBACK_YEAR) / len(changes),
    }


def debt_ebit_gap(fin: FinancialHistory) -> float | None:
    """CAGR(debt) - CAGR(EBIT) over the common window. Positive = leverage
    growing faster than the earnings that must service it."""
    debt = fin.series("total_debt")
    ebit = fin.series("operating_income")
    if len(debt) < 2 or len(ebit) < 2:
        return None
    common = sorted(set(dict(debt)) & set(dict(ebit)))
    if len(common) < 2:
        return None
    d, e = dict(debt), dict(ebit)
    y0, y1 = common[0], common[-1]
    span = y1 - y0
    if min(d[y0], d[y1], e[y0], e[y1]) <= 0 or span == 0:
        return None
    return (d[y1] / d[y0]) ** (1 / span) - 1 - ((e[y1] / e[y0]) ** (1 / span) - 1)


def _coverage_stress_frac(fin: FinancialHistory) -> float | None:
    ebit = dict(fin.series("operating_income"))
    interest = dict(fin.series("interest_expense"))
    common = [y for y in sorted(set(ebit) & set(interest)) if interest[y] > 0]
    if not common:
        return None
    return sum(1 for y in common if ebit[y] / interest[y] < 2) / len(common)


def _dividend_consistency(fin: FinancialHistory) -> float | None:
    divs = fin.series("dividends_paid")
    if not divs:
        return None
    return sum(1 for _, v in divs if v > 0) / len(divs)


def _allocation_fit(
    inc_roic: float | None, reinvest: float | None,
    dividend_frac: float | None, buyback_frac: float | None,
) -> tuple[float, str]:
    returns_cash = (dividend_frac or 0) >= 0.6 or (buyback_frac or 0) >= 0.3
    if inc_roic is None or reinvest is None:
        return 50.0, "insufficient data to judge allocation fit"
    if inc_roic >= 0.15 and reinvest >= 0.30:
        return 90.0, "compounding machine: heavy reinvestment at high incremental returns"
    if inc_roic >= 0.15 and reinvest < 0.30:
        return 65.0, "under-reinvesting relative to the returns available"
    if inc_roic < 0.08 and reinvest >= 0.50:
        return 20.0, "empire building: heavy reinvestment at poor incremental returns"
    if inc_roic < 0.08 and reinvest < 0.30 and returns_cash:
        return 70.0, "disciplined: low-return business returning cash to owners"
    return 50.0, "mixed allocation record"


def assess_stewardship(
    fin: FinancialHistory,
    info: CompanyInfo,
    fund: FundamentalMetrics,
    business: BusinessProfile,
) -> StewardshipProfile:
    years = len(fin.years())
    track = dilution_track(fin)
    gap = debt_ebit_gap(fin)
    stress = _coverage_stress_frac(fin)
    div_frac = _dividend_consistency(fin)
    fit_score, fit_label = _allocation_fit(
        business.incremental_roic, fund.reinvestment_rate,
        div_frac, track["buyback_years_frac"],
    )

    evidence: list[Evidence] = []
    weighted = 0.0
    weight_present = 0.0

    def add(name, weight, points, benchmark, value, rationale):
        nonlocal weighted, weight_present
        evidence.append(Evidence(
            metric=name, value=value, benchmark=benchmark,
            points=round(max(0.0, min(100.0, points)), 1),
            weight=weight, rationale=rationale,
        ))
        weighted += weight * max(0.0, min(100.0, points))
        weight_present += weight

    if track["share_cagr_full"] is not None:
        cagr = track["share_cagr_full"]
        pts = 95 if cagr <= 0 else 75 if cagr <= 0.02 else 45 if cagr <= 0.05 else 10
        add("dilution_discipline", 0.30, pts,
            f"full-history share CAGR {cagr:+.1%}", round(cagr, 4),
            "Owners should not be quietly diluted out of their compounding")
    add("allocation_fit", 0.30, fit_score, fit_label,
        round(business.incremental_roic, 4) if business.incremental_roic is not None else None,
        "Capital should flow to where the returns are — and only there")
    if gap is not None:
        pts = 90 if gap <= 0 else 60 if gap <= 0.05 else 30 if gap <= 0.15 else 10
        add("debt_discipline", 0.25, pts, f"debt CAGR minus EBIT CAGR {gap:+.1%}",
            round(gap, 4), "Debt growing faster than earnings masks decay with leverage")
    # coverage_stress_frac is reported on the profile (risk context) but not
    # double-counted in the score: debt_discipline already prices leverage.
    if div_frac is not None or track["buyback_years_frac"] is not None:
        consistency = max(div_frac or 0.0, track["buyback_years_frac"] or 0.0)
        add("shareholder_returns", 0.15, 100 * consistency,
            f"cash returned in {consistency:.0%} of years",
            round(consistency, 3), "Real stewardship eventually returns real cash")

    score = weighted / weight_present if weight_present > 0 else 0.0

    if years < 4:
        classification = "Unproven"
    elif (track["share_cagr_full"] is not None and track["share_cagr_full"] > 0.05) or (
        (track["dilution_years_frac"] or 0) > 0.5
    ):
        classification = "Serial Diluter"
    elif fit_score <= 25:
        classification = "Empire Builder"
    elif score >= 75:
        classification = "Owner-Operator Discipline"
    else:
        classification = "Balanced"

    return StewardshipProfile(
        history_years=years,
        share_cagr_full=track["share_cagr_full"],
        dilution_years_frac=track["dilution_years_frac"],
        buyback_years_frac=track["buyback_years_frac"],
        debt_ebit_gap=gap,
        coverage_stress_frac=stress,
        dividend_consistency=div_frac,
        allocation_fit_label=fit_label,
        stewardship_score=round(score, 1),
        classification=classification,
        evidence=evidence,
        completeness=min(1.0, weight_present),
    )
