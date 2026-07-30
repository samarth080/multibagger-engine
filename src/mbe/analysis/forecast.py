"""3-year scenario forecast: what could this stock be worth in three years?

The v0.1 valuation moved exactly one knob between bull, base and bear (growth,
by a factor of 1.2) while sharing a deliberately-haircut base cash flow, so
every scenario told the same pessimistic story. This module instead projects
revenue and net margin separately, applies an exit multiple anchored to what
peers and the stock's own history actually trade at, and guards both ends:
neither the input nor any single scenario is allowed to carry all the
conservatism or all the optimism.

Cross-sectional by nature — the peer anchor needs a screened universe — so it
runs as a post-pass over completed bundles, the same contract as
analysis/sector.py. On the single-ticker path the peer term is simply absent
and PriceForecast.completeness records it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median, quantiles
from typing import TYPE_CHECKING

from mbe.analysis.valuation import spike_ratio
from mbe.backtest.pointintime import availability_date
from mbe.models.analysis import RiskFlag
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath

if TYPE_CHECKING:  # avoid a runtime cycle: pipeline imports this module
    from mbe.models.sector import SectorContext
    from mbe.pipeline import AnalysisBundle

HORIZON_YEARS = 3
GROWTH_CAP = 0.40             # cap on the starting revenue growth rate
TERMINAL_GROWTH_MIN = 0.04
TERMINAL_GROWTH_MAX = 0.15
TERMINAL_GROWTH_FALLBACK = 0.10
PEER_PE_MIN, PEER_PE_MAX = 5.0, 80.0   # sanity filter on peer P/E inputs
OWN_PE_CAP_VS_PEER = 1.5
ANCHOR_MIN, ANCHOR_MAX = 8.0, 45.0
MULT_BEAR, MULT_BASE, MULT_BULL = 0.6, 1.0, 1.4
BULL_CAGR_CAP = 0.45          # ~3x in 3 years; the optimism-side guard
SPIKE_THRESHOLD = 1.5
BEAR_GROWTH_MULT = 0.4
BEAR_GROWTH_MULT_SPIKED = 0.2


def own_pe_series(
    prices: PriceHistory, fin: FinancialHistory, info: CompanyInfo
) -> list[float]:
    """Trailing P/E for each trading day, using only earnings published by that
    date. Yahoo labels an Indian fiscal year by its March end-year, so the
    90-day filing lag in pointintime.availability_date is what stops this from
    looking ahead; fin.filed overrides it whenever a real date is known.
    """
    ni = dict(fin.series("net_income"))
    shares = dict(fin.series("shares_diluted"))
    if not ni or prices.df.empty:
        return []
    fy_end_month = 3 if info.ticker.endswith((".NS", ".BO")) else 12
    visible_from: list[tuple[date, int]] = sorted(
        (fin.filed.get(year) or availability_date(year, fy_end_month), year)
        for year in ni
    )
    out: list[float] = []
    for timestamp, close in prices.df["close"].items():
        as_of = timestamp.date()
        published = [year for avail, year in visible_from if avail <= as_of]
        if not published:
            continue
        year = max(published)
        earnings, count = ni[year], shares.get(year)
        if earnings <= 0 or count is None or count <= 0:
            continue
        out.append(float(close) * count / earnings)
    return out


def percentile_of(values: list[float], x: float) -> float | None:
    """Share of `values` at or below x. None when there is no distribution."""
    if not values:
        return None
    return sum(1 for v in values if v <= x) / len(values)


def build_anchor(
    peer_pes: list[float],
    own_pes: list[float],
    current_pe: float | None,
    franchise_score: float,
) -> MultipleAnchor:
    """Base-case exit multiple, blended from what peers trade at, what this
    stock has traded at, and how good the business is.

    The own-history term is capped against the peer median because our price
    window is short and regime-bound: a name whose own median is 74x in a
    three-year bull run has not earned a 74x exit assumption.
    """
    notes: list[str] = []
    usable = [p for p in peer_pes if PEER_PE_MIN <= p <= PEER_PE_MAX]
    peer_pe = float(median(usable)) if usable else None
    own_pe = float(median(own_pes)) if own_pes else None
    pctile = percentile_of(own_pes, current_pe) if current_pe is not None else None
    quality_multiplier = 0.85 + 0.35 * (franchise_score / 100.0)

    own_capped: float | None = None
    if peer_pe is not None and own_pe is not None:
        own_capped = min(own_pe, OWN_PE_CAP_VS_PEER * peer_pe)
        if own_capped < own_pe:
            notes.append(
                f"own-history P/E median {own_pe:.1f}x capped to {own_capped:.1f}x "
                f"({OWN_PE_CAP_VS_PEER:g}x the peer median) — our price window is "
                "short and covers one regime"
            )
        raw = 0.6 * peer_pe + 0.4 * own_capped
    elif peer_pe is not None:
        raw = peer_pe
        notes.append("no own-history P/E available — anchored on peers alone")
    elif own_pe is not None:
        # No peer median to cap the own history against, so take the lower
        # quartile rather than the median. Our price window is short and covers
        # one regime: a stock that spent three years re-rating has a median
        # multiple describing that re-rating, not a defensible exit assumption,
        # and on this path there is nothing else to check it against. The
        # quartile is the one conservatism still available.
        # method="inclusive": we want a multiple this stock demonstrably traded
        # at, not an extrapolated population quantile, which on a short series
        # can fall below anything ever observed.
        own_low = (
            float(quantiles(own_pes, n=4, method="inclusive")[0])
            if len(own_pes) >= 4
            else min(own_pes)
        )
        raw = min(own_low, ANCHOR_MAX)
        notes.append(
            f"no peer P/E available — anchored on the lower quartile of own "
            f"history ({own_low:.1f}x, against a median of {own_pe:.1f}x), the "
            f"only check available without peers"
        )
    else:
        notes.append("neither peer nor own-history P/E available — no anchor")
        return MultipleAnchor(
            own_pe_percentile_now=pctile,
            quality_multiplier=quality_multiplier,
            notes=notes,
        )

    anchor = raw * quality_multiplier
    clamped = min(max(anchor, ANCHOR_MIN), ANCHOR_MAX)
    if clamped != anchor:
        notes.append(
            f"anchor {anchor:.1f}x clamped to {clamped:.1f}x "
            f"(bounds {ANCHOR_MIN:g}x-{ANCHOR_MAX:g}x)"
        )
    return MultipleAnchor(
        peer_pe=peer_pe,
        peer_n=len(usable),
        own_pe_median=own_pe,
        own_pe_percentile_now=pctile,
        own_pe_capped=own_capped,
        quality_multiplier=quality_multiplier,
        anchor=clamped,
        notes=notes,
    )


def fade(start: float, end: float, years: int) -> list[float]:
    """Linear fade from start to end, inclusive of both endpoints."""
    if years <= 1:
        return [end]
    return [start + (end - start) * i / (years - 1) for i in range(years)]


def terminal_growth(peer_growths: list[float]) -> float:
    """The rate growth fades toward: the peer median, clamped to a plausible
    band. Falls back to a fixed rate when there is no peer set (single-ticker
    path), which is why the fallback is stated rather than silently zero.
    """
    present = [g for g in peer_growths if g is not None]
    if not present:
        return TERMINAL_GROWTH_FALLBACK
    return min(max(float(median(present)), TERMINAL_GROWTH_MIN), TERMINAL_GROWTH_MAX)


def growth_paths(
    g0: float, g_term: float, spiked: bool
) -> dict[str, tuple[float, float]]:
    """(start, end) revenue growth per scenario.

    Driven by delivered revenue CAGR alone. v0.1 took a median across
    revenue/profit/FCF CAGRs — non-comparable series whose median then had to
    be clipped to 25%, which made the report's "delivered-growth median" label
    false and capped every bull case at 30%.
    """
    start = min(max(g0, 0.0), GROWTH_CAP)
    bear_mult = BEAR_GROWTH_MULT_SPIKED if spiked else BEAR_GROWTH_MULT
    return {
        "bull": (start, max(start * 0.7, g_term)),
        "base": (start, g_term),
        "bear": (start * bear_mult, g_term * 0.5),
    }


def margin_paths(m0: float, m3: float, m_best: float) -> dict[str, float]:
    """Terminal net margin per scenario.

    This is where "was the latest year a peak, or the new normal?" is argued
    explicitly: bull treats it as the new normal, base splits the difference
    with the 3-year mean, bear reverts fully.

    The bull leg is the current margin plus a little *or* a recovery to the
    3-year average, whichever is higher, capped by the best year the business
    has actually delivered. Without the recovery term, a company that has
    slipped below its own average gets a bull margin beneath its own base case
    — a scenario table that reads as broken, and a bull case that assumes the
    worst stretch of the record is permanent.
    """
    return {
        "bull": min(max(m0 * 1.05, m3), m_best),
        "base": (m0 + m3) / 2,
        "bear": min(m0, m3),
    }


@dataclass(frozen=True)
class Projection:
    revenue_fy3: float
    eps_fy3: float
    target_price: float
    cagr_3y: float


def project(
    revenue_0: float,
    growth_path: list[float],
    margin: float,
    shares_0: float,
    share_cagr: float,
    exit_multiple: float,
    price: float,
) -> Projection:
    """Compound revenue along the growth path, apply the terminal margin and
    projected share count, then the exit multiple.

    A bear path can legitimately project a loss-making terminal year — the bear
    margin is min(latest, 3y mean), so one loss year in the window is enough —
    and a P/E on negative earnings gives a negative target. Equity has limited
    liability, the same reason compute_valuation floors a debt-overhang DCF at
    zero: the honest expression of "this scenario is a wipeout" is a target of
    zero and a total loss over the horizon, not a negative share price and not
    the imaginary number that (negative) ** (1/3) actually returns. EPS is left
    negative, because that is the projection talking.
    """
    revenue = revenue_0
    for g in growth_path:
        revenue *= 1 + g
    shares = shares_0 * (1 + max(share_cagr, 0.0)) ** HORIZON_YEARS
    eps = revenue * margin / shares
    target = eps * exit_multiple
    if target <= 0:
        return Projection(
            revenue_fy3=revenue, eps_fy3=eps, target_price=0.0, cagr_3y=-1.0
        )
    return Projection(
        revenue_fy3=revenue,
        eps_fy3=eps,
        target_price=target,
        cagr_3y=(target / price) ** (1 / HORIZON_YEARS) - 1 if price > 0 else 0.0,
    )


def apply_bull_guard(
    eps_fy3: float, exit_multiple: float, base_exit_multiple: float, price: float
) -> tuple[float, list[str]]:
    """Keep the bull case from stacking every knob at its optimum.

    Sustained growth AND expanded margins AND a full re-rating compound into
    fantasy (5x in three years, measured on HBLENGINE.NS) — the mirror image of
    the v0.1 failure. One knob is trimmed, the exit multiple, and the trim is
    reported. It never goes below the base case's multiple: that would invert
    the scenario ordering, and a bull case still above the cap at the base
    multiple is a finding about the earnings path, not something to hide.
    """
    if price <= 0 or eps_fy3 <= 0:
        return exit_multiple, []
    cagr = (eps_fy3 * exit_multiple / price) ** (1 / HORIZON_YEARS) - 1
    if cagr <= BULL_CAGR_CAP:
        return exit_multiple, []
    needed = price * (1 + BULL_CAGR_CAP) ** HORIZON_YEARS / eps_fy3
    if needed < base_exit_multiple:
        return base_exit_multiple, [
            f"bull {cagr:.0%}/yr exceeds the {BULL_CAGR_CAP:.0%}/yr sanity bound and "
            f"could not be trimmed to it without dropping the bull exit multiple "
            f"below the base case's {base_exit_multiple:.1f}x — the earnings path "
            f"alone implies this move"
        ]
    return needed, [
        f"bull exit multiple trimmed {exit_multiple:.1f}x -> {needed:.1f}x to respect "
        f"the {BULL_CAGR_CAP:.0%}/yr sanity bound"
    ]


VETO_SHIFT = 0.15


def scenario_probabilities(
    mean_assumption_support: float, franchise_score: float, veto: bool
) -> dict[str, float]:
    """Weights drawn from evidence the engine already computes: how often this
    company's own assumptions have held, and how durable the franchise looks.
    A vetoed thesis moves weight from bull to bear.
    """
    quality = 0.5 * mean_assumption_support + 0.5 * (franchise_score / 100.0)
    p_bull = 0.10 + 0.30 * quality
    p_bear = 0.40 - 0.25 * quality
    if veto:
        shift = min(VETO_SHIFT, p_bull)
        p_bull -= shift
        p_bear += shift
    return {"bull": p_bull, "base": 1.0 - p_bull - p_bear, "bear": p_bear}


def expected_outcome(
    targets: dict[str, float], probs: dict[str, float], price: float
) -> tuple[float | None, float | None, float]:
    """Returns (expected_target, expected_cagr_3y, downside_probability).

    The expectation is taken over *prices* and only then annualised. Averaging
    the scenario CAGRs directly would be a different — and wrong — number,
    because CAGR is non-linear in price.
    """
    expected_target = sum(probs[name] * targets[name] for name in targets)
    downside = sum(probs[name] for name in targets if targets[name] < price)
    if price <= 0 or expected_target <= 0:
        return expected_target or None, None, downside
    return (
        expected_target,
        (expected_target / price) ** (1 / HORIZON_YEARS) - 1,
        downside,
    )


def _mean_assumption_support(bundle: "AnalysisBundle") -> float:
    """Mean historical support across the thesis assumptions — the same
    quantity build_thesis uses for thesis_confidence. 0.5 when unknown, so an
    unmeasurable company sits at the midpoint rather than at either extreme."""
    if bundle.thesis is None or not bundle.thesis.assumptions:
        return 0.5
    supports = [a.historical_support for a in bundle.thesis.assumptions]
    return sum(supports) / len(supports)


def _net_margins(fin: FinancialHistory) -> list[tuple[int, float]]:
    revenue = dict(fin.series("revenue"))
    return [
        (year, ni / revenue[year])
        for year, ni in fin.series("net_income")
        if revenue.get(year) not in (None, 0)
    ]


def earnings_spiked(fin: FinancialHistory) -> bool:
    """Did the latest year stand far enough above its own recent record that
    "it does not repeat" is the real bear case?

    True when either cash flow or accounting profit spiked, because either one
    carrying the latest year is enough to make the bear path load-bearing.
    """
    return any(
        (ratio := spike_ratio(fin, field)) is not None and ratio >= SPIKE_THRESHOLD
        for field in ("fcf", "net_income")
    )


def build_forecast(
    bundle: "AnalysisBundle", peer_pes: list[float], peer_growths: list[float]
) -> PriceForecast | None:
    """Three-year bull/base/bear target prices for one company.

    Returns None when no exit multiple can be anchored — neither peers nor a
    usable own-P/E history. A forecast without an anchor would be arithmetic
    dressed up as a view.
    """
    fin, info, fund, val = bundle.fin, bundle.info, bundle.fund, bundle.val
    price = val.price
    margins = _net_margins(fin)
    revenue_0 = fin.latest("revenue")
    shares_0 = fin.latest("shares_diluted") or info.shares_outstanding
    if not margins or not revenue_0 or not shares_0 or price <= 0:
        return None

    base_year, m0 = margins[-1]
    if m0 <= 0:
        # The exit multiple is a P/E, so a target price built on negative
        # earnings is not conservative, it is meaningless. Decline rather than
        # emit a number, the same contract as a missing anchor below.
        return None
    recent = [m for _, m in margins[-3:]]
    m3 = sum(recent) / len(recent)
    m_best = max(m for _, m in margins)

    own_pes = (
        own_pe_series(bundle.prices, fin, info) if bundle.prices is not None else []
    )
    franchise = bundle.business.franchise_score if bundle.business else 0.0
    anchor = build_anchor(peer_pes, own_pes, val.pe, franchise)
    if anchor.anchor is None:
        return None

    spiked = earnings_spiked(fin)

    g_term = terminal_growth(peer_growths)
    growth = growth_paths(fund.revenue_cagr_3y or 0.0, g_term, spiked)
    margin = margin_paths(m0, m3, m_best)
    probs = scenario_probabilities(
        _mean_assumption_support(bundle),
        franchise,
        veto=bool(bundle.critique and bundle.critique.veto),
    )
    multiples = {
        "bull": anchor.anchor * MULT_BULL,
        "base": anchor.anchor * MULT_BASE,
        "bear": anchor.anchor * MULT_BEAR,
    }
    share_cagr = fund.share_count_cagr_3y or 0.0

    scenarios: list[ScenarioPath] = []
    targets: dict[str, float] = {}
    for name in ("bull", "base", "bear"):
        start, end = growth[name]
        path = fade(start, end, HORIZON_YEARS)
        exit_multiple = multiples[name]
        p = project(revenue_0, path, margin[name], shares_0, share_cagr,
                    exit_multiple, price)
        evidence = [
            f"revenue grows {start:.0%} fading to {end:.0%} over {HORIZON_YEARS} years",
            f"net margin ends at {margin[name]:.1%} (latest {m0:.1%}, "
            f"3y mean {m3:.1%})",
            f"exits at {exit_multiple:.1f}x earnings "
            f"({exit_multiple / anchor.anchor:.1f}x the {anchor.anchor:.1f}x anchor)",
        ]
        if name == "bull":
            exit_multiple, guard_notes = apply_bull_guard(
                p.eps_fy3, exit_multiple, multiples["base"], price
            )
            if guard_notes:
                p = project(revenue_0, path, margin[name], shares_0, share_cagr,
                            exit_multiple, price)
                evidence[-1] = f"exits at {exit_multiple:.1f}x earnings"
                evidence.extend(guard_notes)
        if spiked and name == "bear":
            evidence.append(
                "the latest year stands well above its own 3y record, so this bear "
                "path assumes the step change does not repeat"
            )
        scenarios.append(ScenarioPath(
            name=name, probability=probs[name], growth_start=start, growth_end=end,
            terminal_net_margin=margin[name], exit_multiple=exit_multiple,
            revenue_fy3=p.revenue_fy3, eps_fy3=p.eps_fy3,
            target_price=p.target_price, cagr_3y=p.cagr_3y, evidence=evidence,
        ))
        targets[name] = p.target_price

    expected_target, expected_cagr, downside = expected_outcome(targets, probs, price)
    present = [
        anchor.peer_pe is not None,
        bool(own_pes),
        fund.revenue_cagr_3y is not None,
        True,                                   # net margin, guaranteed above
        fin.latest("shares_diluted") is not None,
        bundle.business is not None,
        bundle.thesis is not None and bool(bundle.thesis.assumptions),
    ]
    return PriceForecast(
        ticker=info.ticker, base_fiscal_year=base_year, price=price, anchor=anchor,
        scenarios=scenarios, expected_target=expected_target,
        expected_cagr_3y=expected_cagr, downside_probability=downside,
        completeness=sum(present) / len(present),
    )


MULTIPLE_LOW_PERCENTILE = 0.10


def forecast_flags(
    bundle: "AnalysisBundle", forecast: PriceForecast | None
) -> list[RiskFlag]:
    """Coherence checks on the forecast against observable market facts.

    Reported, never scored: risk_score is already computed by the time these
    are known, and the spec keeps the only scoring change confined to
    margin_of_safety. FORECAST_INCOHERENT exists so the v0.1 failure — the
    model's bull case sitting below the growth the market already pays for —
    cannot recur without saying so out loud.
    """
    if forecast is None:
        return []
    flags: list[RiskFlag] = []

    pctile = forecast.anchor.own_pe_percentile_now
    if pctile is not None and pctile <= MULTIPLE_LOW_PERCENTILE:
        flags.append(RiskFlag(
            code="MULTIPLE_AT_LOW", severity=1,
            detail=(
                f"Trades at the {pctile:.0%} percentile of its own multiple history "
                f"(median {forecast.anchor.own_pe_median:.1f}x) — cheap relative to "
                "its own past, not just to peers"
            ),
        ))

    ni_ratio = spike_ratio(bundle.fin, "net_income")
    if ni_ratio is not None and ni_ratio >= SPIKE_THRESHOLD:
        flags.append(RiskFlag(
            code="EARNINGS_SPIKE", severity=1,
            detail=(
                f"Latest earnings are {ni_ratio:.1f}x their 3y mean — the bear "
                "scenario is load-bearing here"
            ),
        ))

    bull = next((s for s in forecast.scenarios if s.name == "bull"), None)
    implied = bundle.val.implied_growth
    if bull is not None and implied is not None and bull.growth_start < implied:
        flags.append(RiskFlag(
            code="FORECAST_INCOHERENT", severity=2,
            detail=(
                f"Bull case assumes {bull.growth_start:.0%} growth but the market "
                f"already prices {implied:.0%} — the model's most optimistic case is "
                "below consensus, so treat the forecast as understated"
            ),
        ))
    return flags


# Every code forecast_flags can emit. Kept beside it so the two cannot drift:
# apply_forecasts needs to know which of a bundle's flags it owns in order to
# replace rather than duplicate them.
FORECAST_FLAG_CODES = frozenset(
    {"MULTIPLE_AT_LOW", "EARNINGS_SPIKE", "FORECAST_INCOHERENT"}
)


def apply_forecasts(
    bundles: list["AnalysisBundle"], context: "SectorContext"
) -> None:
    """Post-pass: give every bundle a forecast with a leave-one-out peer anchor.

    Cross-sectional by nature, the same contract as analysis/sector.py — the
    same stock legitimately gets a different peer anchor in a different
    universe. Mutates bundles in place and appends coherence flags.

    Replace-not-append: analyze_ticker has already attached a peerless solo
    forecast and its flags by the time this runs, so the flags this pass owns
    are dropped first. Appending would put a second MULTIPLE_AT_LOW in every
    screened report, and skipping bundles that already have a forecast would
    keep the solo anchor — the worse of the two, since the peer term is the
    whole reason this pass exists. Only codes in FORECAST_FLAG_CODES are
    touched; flags from assess_risk are none of this function's business.
    """
    by_group: dict[str, list["AnalysisBundle"]] = {}
    for bundle in bundles:
        group = context.membership.get(bundle.info.ticker)
        if group is not None:
            by_group.setdefault(group, []).append(bundle)

    for bundle in bundles:
        group = context.membership.get(bundle.info.ticker)
        peers = [
            b for b in by_group.get(group, [])
            if b.info.ticker != bundle.info.ticker
        ] if group is not None else []
        peer_pes = [b.val.pe for b in peers if b.val.pe is not None]
        peer_growths = [
            b.fund.revenue_cagr_3y for b in peers
            if b.fund.revenue_cagr_3y is not None
        ]
        bundle.forecast = build_forecast(bundle, peer_pes, peer_growths)
        bundle.risk.flags = [
            f for f in bundle.risk.flags if f.code not in FORECAST_FLAG_CODES
        ]
        bundle.risk.flags.extend(forecast_flags(bundle, bundle.forecast))
