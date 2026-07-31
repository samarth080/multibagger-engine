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
