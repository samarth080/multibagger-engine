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

from datetime import date
from statistics import median

from mbe.backtest.pointintime import availability_date
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.forecast import MultipleAnchor

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
        raw = min(own_pe, ANCHOR_MAX)
        notes.append("no peer P/E available — anchored on own history alone")
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
