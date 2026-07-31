"""Report charts: peers, ownership, financial trend, forecast scenarios.

Each chart is a pure function returning an SVG string, or `None` when the
data cannot support it. `None` is not an error and never a zero — it means
the template falls back to a table or to text naming what is missing, which
is the same contract the rest of this engine uses for absent data.

Nothing here is scored. These render values the engine already computed.
"""

from __future__ import annotations

from dataclasses import dataclass

from mbe.models.company import FinancialHistory
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
