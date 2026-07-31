"""Report charts: peers, ownership, financial trend, forecast scenarios.

Each chart is a pure function returning an SVG string, or `None` when the
data cannot support it. `None` is not an error and never a zero — it means
the template falls back to a table or to text naming what is missing, which
is the same contract the rest of this engine uses for absent data.

Nothing here is scored. These render values the engine already computed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.report import svg

TREND_FIELDS = (
    ("revenue", "Revenue"),
    ("net_income", "Net income"),
    ("fcf", "Free cash flow"),
)
PANEL_W, PANEL_H = 220, 190
TREND_YEARS = 5          # Yahoo supplies 4-5; more would just be padding


def _compact(value: float, currency: str | None) -> str:
    """Bar label. The unit is stated once in the panel header, not per bar."""
    return f"{value / 1e7:,.0f}" if currency == "INR" else f"{value / 1e9:,.1f}"


def _trend_panel(series: list[tuple[int, float]], label: str,
                 currency: str | None) -> str:
    unit = "Rs cr" if currency == "INR" else "$bn"
    values = [v for _, v in series]
    top, plot_h, left, right = 34.0, 116.0, 12.0, PANEL_W - 12.0
    # 0.0 is always in the domain so the zero line is real, not implied
    hi, lo = max(values + [0.0]), min(values + [0.0])
    zero_y = svg.scale(0.0, lo, hi, top + plot_h, top)
    slot = (right - left) / len(series)
    bar_w = min(slot * 0.6, 34.0)

    parts = [
        svg.text(12, 16, label, size=10, weight="600"),
        svg.text(12, 27, unit, fill=svg.MUTED, size=8),
        svg.line(left, zero_y, right, zero_y),
    ]
    for i, (year, value) in enumerate(series):
        cx = left + slot * (i + 0.5)
        y = svg.scale(value, lo, hi, top + plot_h, top)
        parts.append(svg.rect(cx - bar_w / 2, min(y, zero_y), bar_w,
                              abs(zero_y - y),
                              svg.GAIN if value >= 0 else svg.LOSS))
        parts.append(svg.text(cx, top + plot_h + 16, f"FY{year % 100:02d}",
                              fill=svg.MUTED, size=8, anchor="middle"))
        # label above a positive bar, below a negative one, so it never
        # overlaps the bar it describes
        label_y = min(y, zero_y) - 4 if value >= 0 else max(y, zero_y) + 10
        parts.append(svg.text(cx, label_y, _compact(value, currency),
                              size=8, anchor="middle"))
    return "\n".join(parts)


def trend_bars(fin: FinancialHistory, currency: str | None) -> str | None:
    """Revenue, net income and free cash flow as small multiples.

    A field with fewer than two years is skipped rather than drawn: one bar
    is a dot, not a trend. All three skipped -> None."""
    panels = [
        _trend_panel(series, label, currency)
        for field, label in TREND_FIELDS
        if len(series := fin.series(field)[-TREND_YEARS:]) >= 2
    ]
    if not panels:
        return None
    parts = [f'<g transform="translate({i * PANEL_W},0)">{p}</g>'
             for i, p in enumerate(panels)]
    return svg.document(
        PANEL_W * len(panels), PANEL_H,
        "Revenue, net income and free cash flow by fiscal year", parts,
    )


OWNERSHIP_TOLERANCE = 0.10   # see ownership_conflict for where this comes from


def _ring(cx: float, cy: float, r: float, width: float,
          slices: list[tuple[float, str]]) -> list[str]:
    """Donut segments as dash-patterned circles.

    Stroke dashes rather than arc paths: an arc whose sweep is a full circle
    degenerates (start point == end point) and silently disappears, which is
    exactly the 100%-single-holder case."""
    circumference = 2 * math.pi * r
    out, offset = [], 0.0
    for fraction, colour in slices:
        segment = max(fraction, 0.0) * circumference
        out.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
            f'stroke="{colour}" stroke-width="{width:.1f}" '
            f'stroke-dasharray="{segment:.2f} {circumference - segment:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx:.1f} {cy:.1f})"/>'
        )
        offset += segment
    return out


def shareholding(info: CompanyInfo) -> str | None:
    """Insider/promoter, institutions and the public remainder.

    Both reported figures are required. Filling a missing one with 0 would
    draw a confident chart out of an absent number, which is the imputation
    this engine refuses everywhere else."""
    insider, institution = info.insider_pct, info.institution_pct
    if insider is None or institution is None:
        return None

    slices = [("Insider / promoter", insider, svg.SUBJECT),
              ("Institutions", institution, svg.PEER)]
    public = 1.0 - insider - institution
    if public > 0.001:
        slices.append(("Public / other", public, svg.MUTED))
    # else the two reported holdings already exhaust (or exceed) the register;
    # a negative slice would be a picture of an impossibility

    cx, cy, r = 90.0, 100.0, 52.0
    parts = _ring(cx, cy, r, 26.0, [(f, c) for _, f, c in slices])
    for i, (label, fraction, colour) in enumerate(slices):
        y = 62.0 + i * 22.0
        parts.append(svg.rect(190.0, y - 8, 10, 10, colour))
        parts.append(svg.text(208.0, y, f"{label} — {fraction * 100:.1f}%", size=10))
    return svg.document(430, 200, "Shareholding split", parts)


def ownership_conflict(info: CompanyInfo) -> str | None:
    """Whether Yahoo's two ownership fields contradict each other.

    `insider_pct` and `float_shares` are independent fields from the same
    source and should agree: whatever insiders hold is not free-floating.
    Measured across the 25 live picks (2026-08-01), 21 agree within 7.4pp and
    4 do not — HBL by 54pp, claiming 8.1% insider while its own float implies
    ~62%. The 10pp threshold sits in the empty band between those groups.

    Returns the text to show, or None when the fields agree."""
    if info.insider_pct is None:
        return None
    if not info.float_shares or not info.shares_outstanding:
        return ("float not reported, so the insider figure "
                "could not be cross-checked")
    implied = 1.0 - info.float_shares / info.shares_outstanding
    if abs(info.insider_pct - implied) <= OWNERSHIP_TOLERANCE:
        return None
    return (f"Yahoo reports {info.insider_pct * 100:.1f}% insider, but its own "
            f"float figure implies {implied * 100:.0f}% — the source "
            f"contradicts itself and neither number is verified here")


@dataclass(frozen=True)
class PeerRow:
    """One company's line in its industry group. `None` means not computable."""

    ticker: str
    name: str
    roce: float | None
    growth: float | None
    pe: float | None
    score: float
    market_cap: float | None
    is_subject: bool


def peer_rows(subject_ticker: str, group: list) -> list[PeerRow]:
    """Build comparison rows from a group of AnalysisBundles.

    Takes bundles rather than pre-extracted numbers because the caller
    (`publish.render_report_page`) has them and nothing else needs the
    extraction. Sorted best-score-first, which is how the site ranks."""
    rows = [
        PeerRow(
            ticker=b.card.ticker,
            name=(b.info.name or b.card.ticker)[:22],
            roce=b.fund.roce_3y,
            growth=b.fund.revenue_cagr_3y,
            pe=b.info.trailing_pe,
            score=b.card.multibagger_score,
            market_cap=b.info.market_cap,
            is_subject=b.card.ticker == subject_ticker,
        )
        for b in group
    ]
    return sorted(rows, key=lambda r: -r.score)


_PEER_COLUMNS = (
    ("ROCE 3y", "roce", True),
    ("Rev CAGR 3y", "growth", True),
    ("P/E (lower is cheaper)", "pe", False),
)
ROW_H = 20.0


def _cell(value: float | None, best: float, x: float, y: float,
          colour: str, as_pct: bool) -> list[str]:
    if value is None:
        return [svg.text(x, y, "n/a", fill=svg.MUTED, size=8)]
    width = 0.0 if best <= 0 else max(0.0, min(1.0, value / best)) * 78.0
    label = f"{value * 100:.1f}%" if as_pct else f"{value:.1f}x"
    return [svg.rect(x, y - 8, width, 8, colour), svg.text(x + 82, y, label, size=8)]


def peer_table(rows: list[PeerRow]) -> str | None:
    """One row per peer, a proportional bar per metric.

    Bar length is the value relative to the group's best, so a missing metric
    has no bar at all — it renders "n/a" rather than a zero-length bar that
    reads as "worst in group"."""
    if not rows:
        return None
    height = int(46 + ROW_H * len(rows))
    parts = [svg.text(8, 14, "Peer group", size=10, weight="600")]
    for i, (title, _attr, _pct) in enumerate(_PEER_COLUMNS):
        parts.append(svg.text(120 + i * 120, 14, title, fill=svg.MUTED, size=8))
    parts.append(svg.line(8, 22, 460, 22))

    for r, row in enumerate(rows):
        y = 40.0 + r * ROW_H
        colour = svg.SUBJECT if row.is_subject else svg.PEER
        parts.append(svg.text(8, y, row.name, fill=colour, size=9,
                              weight="600" if row.is_subject else "normal"))
        for i, (_title, attr, as_pct) in enumerate(_PEER_COLUMNS):
            values = [getattr(p, attr) for p in rows if getattr(p, attr) is not None]
            best = max(values) if values else 0.0
            parts.extend(_cell(getattr(row, attr), best, 120 + i * 120, y,
                               colour, as_pct))
    return svg.document(470, height, "Peer group comparison", parts)


def peer_scatter(rows: list[PeerRow]) -> str | None:
    """Quality against growth, bubble area by market cap.

    Needs three plottable points: two make a line and one makes a dot, and
    neither says anything about where a company sits in its group."""
    points = [r for r in rows if r.roce is not None and r.growth is not None]
    if len(points) < 3:
        return None

    xs = [p.roce for p in points]
    ys = [p.growth for p in points]
    x_lo, x_hi = min(xs + [0.0]), max(xs)
    y_lo, y_hi = min(ys + [0.0]), max(ys)
    caps = [p.market_cap for p in points if p.market_cap]
    cap_max = max(caps) if caps else 0.0

    left, right, top, bottom = 44.0, 300.0, 22.0, 158.0
    parts = [
        svg.text(8, 14, "Quality vs growth", size=10, weight="600"),
        svg.line(left, bottom, right, bottom),
        svg.line(left, top, left, bottom),
        svg.text((left + right) / 2, 176, "ROCE 3y",
                 fill=svg.MUTED, size=8, anchor="middle"),
        svg.text(12, (top + bottom) / 2, "Revenue CAGR",
                 fill=svg.MUTED, size=8, anchor="middle"),
    ]
    if y_lo < 0:
        zero = svg.scale(0.0, y_lo, y_hi, bottom, top)
        parts.append(svg.line(left, zero, right, zero, dash="3 3"))

    for p in points:
        cx = svg.scale(p.roce, x_lo, x_hi, left, right)
        cy = svg.scale(p.growth, y_lo, y_hi, bottom, top)
        r = 5.0 if not cap_max or not p.market_cap else 4.0 + 6.0 * (p.market_cap / cap_max)
        parts.append(svg.circle(cx, cy, r,
                                svg.SUBJECT if p.is_subject else svg.PEER,
                                1.0 if p.is_subject else 0.7))
        if p.is_subject:
            parts.append(svg.text(cx, cy - r - 4, p.name, fill=svg.SUBJECT,
                                  size=8, anchor="middle"))
    return svg.document(320, 190, "Quality versus growth against peers", parts)
