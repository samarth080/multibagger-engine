# Report Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add peer-comparison, ownership, financial-trend and forecast-scenario charts to per-stock report pages as server-rendered inline SVG — no JavaScript, no dependency, nothing scored.

**Architecture:** `svg.py` holds dumb primitives that know nothing about stocks; `charts.py` holds four domain charts that know nothing about SVG syntax. Each chart is a pure function returning an SVG string or `None`. `render_report` gains an optional `charts` dict exactly as it gained `news`/`policy` in v0.14; `publish.render_report_page` builds the SVGs and passes them, so the CLI markdown path is untouched.

**Tech Stack:** Python 3.12, jinja2, python-markdown, pytest. Run tests with `.venv/bin/python -m pytest` (the config already includes `-q`; do not add another).

**Spec:** `docs/superpowers/specs/2026-08-01-report-charts-design.md`

---

## Two constraints that drive every design choice here

**1. Never emit a blank line inside an SVG.** Chart SVGs are interpolated into the markdown report and then run through python-markdown. Verified behaviour:

```python
>>> markdown.markdown('<svg viewBox="0 0 10 10">\n\n<text>A</text>\n</svg>')
'<p><svg viewBox="0 0 10 10"></p>\n<p><text>A</text>\n</svg></p>'
```

A blank line turns one chart into two broken paragraphs. Every builder joins with single `\n`, and Task 1 pins it with a test.

**2. Never emit a literal colour.** `src/mbe/publish.py:55-62` defines the palette twice — `:root` for dark, `[data-theme="light"]` for light — behind a live toggle. A hardcoded `#5b6472` is invisible in one of them. Charts reference `var(--accent)`, `var(--muted)`, `var(--gain)`, `var(--loss)`, `var(--border)`, `var(--text)`.

---

## Deviation from the spec, decided while planning

The spec says "chart replaces the table". Reading `src/mbe/report/markdown.py` shows there is almost nothing to replace:

| chart | table it would replace | verdict |
|---|---|---|
| trend bars | `## Financial Analysis` holds **ratios** (ROCE, margins, coverage), not revenue/profit history | no overlap — chart is additive |
| ownership donut | no ownership table exists | additive |
| peer scatter + table | no peer table exists | additive |
| scenario chart | the scenario table — **kept** by explicit decision (it carries the assumptions) | partial |

So the only honest replacement available is narrow: **when the scenario chart renders, the scenario table drops its `Target` and `3y CAGR` columns**, because the chart labels both directly. Assumptions (growth, margin, exit multiple, probability) stay in the table. Everything else is additive and report pages do get longer.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/mbe/report/svg.py` | new — SVG primitives: escaping, scaling, rect/line/text/circle/ring, document wrapper. No domain knowledge. |
| `src/mbe/report/charts.py` | new — four domain charts + `build_charts` entry point. No raw SVG syntax. |
| `src/mbe/report/markdown.py` | `charts` param; two new sections; trend + scenario chart slots; scenario table column trim |
| `src/mbe/publish.py` | peer-group lookup; build and pass charts in `render_report_page` |
| `tests/test_svg.py` | new — primitives |
| `tests/test_charts.py` | new — the four charts |
| `tests/test_pipeline.py` | report rendering with and without charts |
| `tests/test_publish.py` | peer lookup + end-to-end page |

---

## Task 1: SVG primitives

**Files:**
- Create: `src/mbe/report/svg.py`
- Test: `tests/test_svg.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_svg.py`:

```python
"""Primitives are dumb on purpose: no stock knowledge, two hard rules."""

import re

from mbe.report import svg


def test_esc_neutralises_markup_and_ampersands():
    # company names come from Yahoo; "AT&T" alone breaks an unescaped SVG
    assert svg.esc("AT&T") == "AT&amp;T"
    out = svg.esc('<script>alert(1)</script>')
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert svg.esc('a"b') == "a&quot;b"


def test_scale_maps_clamps_and_survives_a_flat_domain():
    assert svg.scale(0, 0, 10, 0, 100) == 0
    assert svg.scale(10, 0, 10, 0, 100) == 100
    assert svg.scale(5, 0, 10, 0, 100) == 50
    assert svg.scale(99, 0, 10, 0, 100) == 100     # clamped, not extrapolated
    assert svg.scale(-99, 0, 10, 0, 100) == 0
    # every value identical: midpoint beats ZeroDivisionError
    assert svg.scale(7, 7, 7, 0, 100) == 50


def test_document_never_contains_a_blank_line():
    """python-markdown splits a blank line inside a tag into paragraphs,
    turning one chart into '<p><svg></p>'. This is the load-bearing test."""
    doc = svg.document(100, 50, "T", [svg.text(1, 2, "a"), "", svg.rect(0, 0, 5, 5, svg.PEER)])
    assert "\n\n" not in doc
    assert doc.startswith("<svg") and doc.endswith("</svg>")


def test_document_is_labelled_for_screen_readers():
    doc = svg.document(100, 50, "Revenue by year", [])
    assert 'role="img"' in doc
    assert "<title>Revenue by year</title>" in doc
    assert 'aria-label="Revenue by year"' in doc


def test_document_escapes_its_title():
    assert "<script>" not in svg.document(10, 10, "<script>x</script>", [])


def test_no_primitive_emits_a_literal_colour():
    """The site has dark and light palettes; a hex literal is invisible in one."""
    out = "".join([
        svg.text(1, 2, "a"), svg.rect(0, 0, 1, 1, svg.SUBJECT),
        svg.line(0, 0, 1, 1), svg.circle(1, 1, 1, svg.GAIN),
        svg.document(10, 10, "t", []),
    ])
    assert not re.search(r"#[0-9a-fA-F]{3,6}", out)


def test_rect_never_gets_a_negative_dimension():
    assert 'width="0.0"' in svg.rect(0, 0, -5, 10, svg.PEER)
    assert 'height="0.0"' in svg.rect(0, 0, 10, -5, svg.PEER)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_svg.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mbe.report.svg'`.

- [ ] **Step 3: Implement the primitives**

Create `src/mbe/report/svg.py`:

```python
"""SVG primitives for report charts — no domain knowledge, no I/O.

Two rules this module exists to enforce:

1. **Never emit a blank line.** Chart SVGs are interpolated into the markdown
   report and then run through python-markdown, which splits a blank line
   inside a tag into paragraphs — turning `<svg>...</svg>` into
   `<p><svg ...></p><p>...</svg></p>`. The chart is destroyed while the
   source still looks fine.
2. **Never emit a literal colour.** `publish.THEME_CSS` defines the palette
   twice, for dark and light, behind a live toggle. A hardcoded hex is
   invisible in one of them, so charts reference the same CSS custom
   properties the rest of the page uses and follow the theme for free.
"""

from __future__ import annotations

from html import escape as _escape

# CSS custom properties defined for both palettes in publish.THEME_CSS.
SUBJECT = "var(--accent)"
PEER = "var(--muted)"
GAIN = "var(--gain)"
LOSS = "var(--loss)"
AXIS = "var(--border)"
TEXT = "var(--text)"
MUTED = "var(--muted)"


def esc(value: object) -> str:
    """Escape untrusted text before it enters an SVG node.

    Company names, tickers and industry labels come from Yahoo. An
    unescaped `&` breaks the document outright, and the reflected XSS fixed
    in v0.11 is the same class of problem one step further along."""
    return _escape(str(value), quote=True)


def scale(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    """Map `value` from [lo, hi] onto [out_lo, out_hi], clamped.

    A degenerate domain — every observation identical, which happens with a
    single-year series or a flat peer group — maps to the midpoint instead of
    dividing by zero."""
    if hi == lo:
        return (out_lo + out_hi) / 2
    t = (value - lo) / (hi - lo)
    return out_lo + max(0.0, min(1.0, t)) * (out_hi - out_lo)


def text(x: float, y: float, s: object, fill: str = TEXT, size: int = 9,
         anchor: str = "start", weight: str = "normal") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{esc(s)}</text>')


def rect(x: float, y: float, w: float, h: float, fill: str) -> str:
    # negative dimensions are an SVG error; clamp so a bad datum degrades to
    # an invisible bar rather than a broken document
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0.0):.1f}" '
            f'height="{max(h, 0.0):.1f}" fill="{fill}"/>')


def line(x1: float, y1: float, x2: float, y2: float,
         stroke: str = AXIS, dash: str = "") -> str:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}"{d}/>')


def circle(cx: float, cy: float, r: float, fill: str, opacity: float = 1.0) -> str:
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" '
            f'opacity="{opacity:g}"/>')


def document(width: int, height: int, title: str, parts: list[str]) -> str:
    """Wrap `parts` in a responsive, accessible <svg>.

    Empty parts are dropped and the rest joined with single newlines, because
    a blank line here would break the chart (see module docstring)."""
    body = "\n".join(p for p in parts if p)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'style="max-width:{width}px;height:auto" role="img" '
        f'aria-label="{esc(title)}">\n'
        f"<title>{esc(title)}</title>"
        + (f"\n{body}" if body else "")
        + "\n</svg>"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_svg.py`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/report/svg.py tests/test_svg.py
git commit -m "feat(report): SVG primitives for charts

Two rules the module exists to enforce: no blank lines (python-markdown
splits them and destroys the chart) and no literal colours (the site has
dark and light palettes behind a live toggle)."
```

---

## Task 2: Financial trend bars

**Files:**
- Create: `src/mbe/report/charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_charts.py`:

```python
"""Charts are pure functions returning SVG strings, so they test on output."""

import re

from mbe.models.company import FinancialHistory
from mbe.report import charts


def _fin(**series) -> FinancialHistory:
    return FinancialHistory(data={k: dict(v) for k, v in series.items()})


def test_trend_bars_renders_every_field_and_year():
    fin = _fin(
        revenue={2023: 1.0e9, 2024: 1.4e9, 2025: 2.0e9},
        net_income={2023: 1.0e8, 2024: 1.5e8, 2025: 2.2e8},
        fcf={2023: 5.0e7, 2024: 9.0e7, 2025: 1.1e8},
    )
    out = charts.trend_bars(fin, "USD")
    assert out is not None
    for label in ("Revenue", "Net income", "Free cash flow"):
        assert label in out
    for year in ("FY23", "FY24", "FY25"):
        assert year in out
    assert "\n\n" not in out


def test_trend_bars_draws_a_loss_year_below_the_zero_line():
    """A loss must be visible as a loss, not clipped to nothing."""
    fin = _fin(net_income={2023: 100.0e7, 2024: -50.0e7, 2025: 20.0e7})
    out = charts.trend_bars(fin, "INR")
    assert out is not None
    assert charts.svg.LOSS in out   # the negative bar is coloured as a loss
    assert charts.svg.GAIN in out   # and the positive ones are not
    assert "-50" in out             # the negative value is labelled


def test_trend_bars_needs_two_years_to_be_a_trend():
    assert charts.trend_bars(_fin(revenue={2025: 1.0e9}), "USD") is None
    assert charts.trend_bars(_fin(), "USD") is None


def test_trend_bars_skips_a_field_without_dropping_the_others():
    fin = _fin(revenue={2024: 1.0e9, 2025: 2.0e9}, fcf={2025: 1.0e8})
    out = charts.trend_bars(fin, "USD")
    assert out is not None
    assert "Revenue" in out
    assert "Free cash flow" not in out   # single year: not a trend


def test_trend_bars_emits_no_literal_colour():
    fin = _fin(revenue={2024: 1.0e9, 2025: 2.0e9})
    assert not re.search(r"#[0-9a-fA-F]{3,6}", charts.trend_bars(fin, "USD"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mbe.report.charts'`.

- [ ] **Step 3: Implement `trend_bars`**

Create `src/mbe/report/charts.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_charts.py`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/report/charts.py tests/test_charts.py
git commit -m "feat(report): financial trend bars

Small multiples for revenue, net income and FCF. A loss year draws below the
zero line rather than being clipped, and a single-year field is skipped
because one bar is a dot, not a trend."
```

---

## Task 3: Shareholding donut and the ownership cross-check

**Files:**
- Modify: `src/mbe/report/charts.py`
- Test: `tests/test_charts.py`

Background, measured on the 25 live picks: Yahoo's `insider_pct` contradicts its own float for 4 of them. Gap vs `1 - float_shares/shares_outstanding`: HBL 54pp, KFINTECH 21pp, LEMONTREE 15pp, NIVABUPA 11pp; the other 21 agree within 7.4pp. The 10pp threshold sits in that gap with room on both sides.

The user's decision (2026-08-01) is to **draw the donut anyway** and state the conflict on the chart.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_charts.py`:

```python
from mbe.models.company import CompanyInfo


def _info(**kw) -> CompanyInfo:
    base = dict(ticker="X.NS", name="X Ltd", currency="INR",
                insider_pct=0.60, institution_pct=0.25,
                float_shares=40.0, shares_outstanding=100.0)
    return CompanyInfo(**{**base, **kw})


def test_shareholding_draws_three_slices_with_the_remainder_as_public():
    out = charts.shareholding(_info())
    assert out is not None
    assert "Insider / promoter" in out and "60.0%" in out
    assert "Institutions" in out and "25.0%" in out
    assert "Public / other" in out and "15.0%" in out
    assert "\n\n" not in out


def test_shareholding_drops_the_public_slice_rather_than_drawing_it_negative():
    out = charts.shareholding(_info(insider_pct=0.70, institution_pct=0.45))
    assert out is not None
    assert "Public / other" not in out   # 115% reported: no room left


def test_shareholding_needs_both_reported_figures():
    assert charts.shareholding(_info(insider_pct=None)) is None
    assert charts.shareholding(_info(institution_pct=None)) is None


def test_ownership_conflict_fires_on_hbls_real_numbers():
    """HBL: 8.1% insider reported, 104.4M of 277.2M shares free-floating,
    which implies ~62%. Both are Yahoo's own fields."""
    note = charts.ownership_conflict(
        _info(insider_pct=0.081, float_shares=104429095.0,
              shares_outstanding=277194946.0)
    )
    assert note is not None
    assert "8.1%" in note and "62" in note


def test_ownership_conflict_silent_when_the_two_fields_agree():
    # BLS: 72.7% insider, 116.7M of 411.5M floating -> implied 71.6%
    assert charts.ownership_conflict(
        _info(insider_pct=0.727, float_shares=116735981.0,
              shares_outstanding=411522253.0)
    ) is None


def test_ownership_conflict_says_when_it_could_not_run():
    note = charts.ownership_conflict(_info(float_shares=None))
    assert note is not None
    assert "could not be cross-checked" in note
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts.py -k "shareholding or ownership"`
Expected: FAIL — `AttributeError: module 'mbe.report.charts' has no attribute 'shareholding'`.

- [ ] **Step 3: Implement the donut and the cross-check**

Add to `src/mbe/report/charts.py` (after `trend_bars`). Two imports change at the top of the file: add `import math` beside `from dataclasses import dataclass`, and extend the models import to `from mbe.models.company import CompanyInfo, FinancialHistory`.

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_charts.py`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/report/charts.py tests/test_charts.py
git commit -m "feat(report): shareholding donut with a source cross-check

Yahoo's insider_pct contradicts its own float for 4 of the 25 live picks
(HBL by 54pp). The donut draws regardless, per decision, but states the
contradiction on the chart rather than in a footnote."
```

---

## Task 4: Peer comparison — scatter and inline-bar table

**Files:**
- Modify: `src/mbe/report/charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_charts.py`:

```python
def _peer(ticker, name, roce, growth, pe, score, mcap):
    return charts.PeerRow(ticker=ticker, name=name, roce=roce, growth=growth,
                          pe=pe, score=score, market_cap=mcap,
                          is_subject=(ticker == "HBLENGINE.NS"))


def _hbl_group():
    """HBL's real 8-name Electrical Equipment & Parts group, 2026-08-01."""
    return [
        _peer("HBLENGINE.NS", "HBL ENGINEERING", 0.329, 0.345, 24.5, 76.6, 199.2e9),
        _peer("SCHNEIDER.NS", "SCHNEIDER ELEC", 0.343, 0.179, 155.0, 65.3, 327.6e9),
        _peer("RRKABEL.NS", "R R KABEL", 0.199, 0.201, 48.9, 58.4, 297.4e9),
        _peer("ARE&M.NS", "AMARA RAJA", 0.141, 0.100, 18.1, 44.5, 166.7e9),
        _peer("FINCABLES.NS", "FINOLEX CABLES", 0.097, 0.127, 21.2, 43.3, 151.1e9),
        _peer("HEG.NS", "HEG LTD", 0.049, 0.016, 35.1, 35.8, 126.8e9),
        _peer("TARIL.NS", "TRANS & RECTI", 0.175, 0.223, 34.7, 35.0, 89.8e9),
        _peer("GRAPHITE.NS", "GRAPHITE INDIA", 0.002, -0.031, 73.1, 34.3, 128.4e9),
    ]


def test_peer_table_lists_every_peer_and_marks_the_subject():
    out = charts.peer_table(_hbl_group())
    assert out is not None
    for name in ("HBL ENGINEERING", "SCHNEIDER ELEC", "GRAPHITE INDIA"):
        assert name in out
    assert "32.9%" in out          # subject ROCE
    assert svg.SUBJECT in out      # subject highlighted
    assert "lower is cheaper" in out   # P/E column direction stated
    assert "\n\n" not in out


def test_peer_table_escapes_a_hostile_name():
    rows = [_peer("X.NS", '<script>alert(1)</script> & Co', 0.2, 0.1, 20.0, 50.0, 1e9)]
    out = charts.peer_table(rows)
    assert "<script>" not in out
    assert "&amp;" in out


def test_peer_table_leaves_a_missing_metric_blank_not_zero():
    rows = _hbl_group()
    rows[1] = _peer("SCHNEIDER.NS", "SCHNEIDER ELEC", None, 0.179, 155.0, 65.3, 327.6e9)
    out = charts.peer_table(rows)
    assert out is not None
    assert "n/a" in out            # stated as absent
    assert "0.0%" not in out       # never imputed to zero


def test_peer_scatter_plots_the_group_and_highlights_the_subject():
    out = charts.peer_scatter(_hbl_group())
    assert out is not None
    assert "ROCE" in out and "Revenue CAGR" in out
    assert out.count("<circle") >= 8
    assert svg.SUBJECT in out
    assert "\n\n" not in out


def test_peer_scatter_works_at_the_smallest_real_group_size():
    """MIN_GROUP is 4, so a 4-name group is the smallest that reaches a
    report page — it must still draw rather than falling back to text."""
    four = [
        _peer("HBLENGINE.NS", "HBL ENGINEERING", 0.329, 0.345, 24.5, 76.6, 199.2e9),
        _peer("SCHNEIDER.NS", "SCHNEIDER ELEC", 0.343, 0.179, 155.0, 65.3, 327.6e9),
        _peer("RRKABEL.NS", "R R KABEL", 0.199, 0.201, 48.9, 58.4, 297.4e9),
        _peer("HEG.NS", "HEG LTD", 0.049, 0.016, 35.1, 35.8, 126.8e9),
    ]
    out = charts.peer_scatter(four)
    assert out is not None
    assert out.count("<circle") >= 4
    assert charts.peer_table(four) is not None


def test_peer_scatter_needs_three_plottable_points():
    thin = [_peer("A.NS", "A", 0.2, 0.1, 10.0, 50.0, 1e9),
            _peer("B.NS", "B", None, None, 10.0, 40.0, 1e9),
            _peer("C.NS", "C", None, None, 10.0, 30.0, 1e9)]
    assert charts.peer_scatter(thin) is None


def test_peer_charts_are_none_for_an_empty_group():
    assert charts.peer_table([]) is None
    assert charts.peer_scatter([]) is None
```

Add `from mbe.report import svg` to the imports at the top of `tests/test_charts.py` if it is not already there (Task 2 referenced it as `charts.svg`; both work, but the direct import reads better here).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts.py -k peer`
Expected: FAIL — `AttributeError: module 'mbe.report.charts' has no attribute 'PeerRow'`.

- [ ] **Step 3: Implement the peer row, table and scatter**

Add to `src/mbe/report/charts.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_charts.py`
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/report/charts.py tests/test_charts.py
git commit -m "feat(report): peer comparison table and quality-vs-growth scatter

A missing metric renders n/a with no bar rather than a zero-length bar that
would read as worst-in-group. Names are escaped at the builder boundary."
```

---

## Task 5: Forecast scenario chart

**Files:**
- Modify: `src/mbe/report/charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_charts.py`:

```python
from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath


def _forecast(price=717.0, targets=(1600.0, 1210.0, 640.0)):
    names = ("bull", "base", "bear")
    probs = (0.25, 0.5, 0.25)
    return PriceForecast(
        ticker="HBLENGINE.NS", base_fiscal_year=2026, price=price,
        anchor=MultipleAnchor(anchor=30.0, quality_multiplier=1.1),
        scenarios=[
            ScenarioPath(name=n, probability=p, growth_start=0.30,
                         growth_end=0.15, terminal_net_margin=0.18,
                         exit_multiple=30.0, revenue_fy3=1.0e10,
                         eps_fy3=40.0, target_price=t,
                         cagr_3y=(t / price) ** (1 / 3) - 1)
            for n, p, t in zip(names, probs, targets)
        ],
        completeness=1.0,
    )


def test_scenario_chart_labels_every_target_and_the_current_price():
    out = charts.scenario_chart(_forecast(), "INR")
    assert out is not None
    for name in ("Bull", "Base", "Bear"):
        assert name in out
    assert "717" in out            # today's price marked
    assert "1,600" in out or "1600" in out
    assert "\n\n" not in out


def test_scenario_chart_colours_downside_as_a_loss():
    out = charts.scenario_chart(_forecast(), "INR")
    assert svg.GAIN in out    # bull and base are above today
    assert svg.LOSS in out    # bear is below it


def test_scenario_chart_handles_an_all_downside_forecast():
    """The v0.13 bug this engine shipped was every scenario negative; the
    chart must render that honestly rather than break."""
    out = charts.scenario_chart(_forecast(targets=(600.0, 500.0, 400.0)), "INR")
    assert out is not None
    assert svg.LOSS in out
    assert svg.GAIN not in out


def test_scenario_chart_is_none_without_scenarios():
    f = _forecast()
    f.scenarios = []
    assert charts.scenario_chart(f, "INR") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_charts.py -k scenario`
Expected: FAIL — `AttributeError: module 'mbe.report.charts' has no attribute 'scenario_chart'`.

- [ ] **Step 3: Implement `scenario_chart`**

Add to `src/mbe/report/charts.py`, and add `from mbe.models.forecast import PriceForecast` to the imports:

```python
def scenario_chart(forecast: PriceForecast, currency: str | None) -> str | None:
    """Three-year targets as bars running from today's price.

    Horizontal, one row per scenario, each bar starting at the current price
    so the direction of the bet is the shape of the picture. Bars above are
    gains, below are losses — the engine shipped a version where every
    scenario was negative, and that has to look wrong at a glance."""
    if not forecast.scenarios:
        return None

    price = forecast.price
    targets = [s.target_price for s in forecast.scenarios]
    lo, hi = min(targets + [price]), max(targets + [price])
    left, right = 92.0, 400.0
    height = int(52 + ROW_H * 1.6 * len(forecast.scenarios))
    x_price = svg.scale(price, lo, hi, left, right)

    parts = [
        svg.text(8, 14, f"{forecast.horizon_years}-year scenarios", size=10,
                 weight="600"),
        svg.line(x_price, 22, x_price, height - 22, dash="3 3"),
        svg.text(x_price, height - 10, f"today {price:,.0f}",
                 fill=svg.MUTED, size=8, anchor="middle"),
    ]
    for i, s in enumerate(forecast.scenarios):
        y = 40.0 + i * ROW_H * 1.6
        x_target = svg.scale(s.target_price, lo, hi, left, right)
        up = s.target_price >= price
        parts.append(svg.text(8, y + 4, s.name.capitalize(), size=9, weight="600"))
        parts.append(svg.text(52, y + 4, f"{s.probability * 100:.0f}%",
                              fill=svg.MUTED, size=8))
        parts.append(svg.rect(min(x_price, x_target), y - 4,
                              abs(x_target - x_price), 10,
                              svg.GAIN if up else svg.LOSS))
        parts.append(svg.text(x_target + (6 if up else -6), y + 4,
                              f"{s.target_price:,.0f}  ({s.cagr_3y * 100:+.0f}%/yr)",
                              size=8, anchor="start" if up else "end"))
    return svg.document(470, height, "Three-year price scenarios", parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_charts.py`
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/report/charts.py tests/test_charts.py
git commit -m "feat(report): three-year scenario chart

Bars run from today's price so the direction of the bet is the shape of the
picture; an all-downside forecast looks wrong at a glance, which is what the
v0.13 defect needed and did not have."
```

---

## Task 6: `build_charts` and the report template

**Files:**
- Modify: `src/mbe/report/charts.py` (add `build_charts`)
- Modify: `src/mbe/report/markdown.py` — imports, `render_report` signature at `:331`, the `_TEMPLATE.render(...)` call, and four template sections
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def test_report_without_charts_keeps_every_table():
    """The CLI markdown path: no charts, nothing lost."""
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()))
    assert "## Financial Analysis" in md
    assert "| Revenue CAGR 3y |" in md          # ratios table intact
    assert "| Scenario | Prob." in md           # full scenario table
    assert "3y CAGR |" in md                    # including the columns a chart would carry
    assert "<svg" not in md


def test_report_with_charts_embeds_svg_and_trims_the_scenario_columns():
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    md = render_report(bundle, charts={
        "trend": "<svg id='t'></svg>",
        "ownership": "<svg id='o'></svg>",
        "scenarios": "<svg id='s'></svg>",
    })
    assert "<svg id='t'></svg>" in md
    assert "<svg id='o'></svg>" in md
    assert "<svg id='s'></svg>" in md
    # the chart carries target and CAGR, so the table drops those two columns
    assert "| Scenario | Prob." in md           # assumptions remain
    assert "Exit multiple" in md
    assert "3y CAGR |" not in md


def test_report_states_why_peer_comparison_is_missing():
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()))
    assert "## Peer Comparison" in md
    assert "requires a universe screen" in md


def test_report_ownership_section_carries_its_caveats_and_conflict():
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()), charts={
        "ownership": "<svg id='o'></svg>",
        "ownership_note": "Yahoo reports 8.1% insider, but its own float implies 62%",
    })
    assert "## Ownership" in md
    assert "8.1% insider" in md
    assert "not SEBI's promoter category" in md
    assert "not the promoter/FII/DII" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -k "charts or peer or ownership or tables"`
Expected: FAIL — `render_report() got an unexpected keyword argument 'charts'` and missing sections.

- [ ] **Step 3: Add `build_charts` to `charts.py`**

Append to `src/mbe/report/charts.py`:

```python
def build_charts(bundle, peers: list | None = None) -> dict[str, str]:
    """Every chart this bundle can support, keyed for the report template.

    A key is absent when its chart could not be built, so the template's
    `{% if charts.x %}` is the single place that decides between a chart, a
    table and an explanatory line. `peers` is None for single-ticker
    analysis, which has no group to compare against."""
    out: dict[str, str] = {}
    if chart := trend_bars(bundle.fin, bundle.info.currency):
        out["trend"] = chart
    if chart := shareholding(bundle.info):
        out["ownership"] = chart
    if note := ownership_conflict(bundle.info):
        out["ownership_note"] = note
    if peers:
        rows = peer_rows(bundle.card.ticker, peers)
        if chart := peer_table(rows):
            out["peer_table"] = chart
        if chart := peer_scatter(rows):
            out["peer_scatter"] = chart
    if bundle.forecast and (chart := scenario_chart(bundle.forecast,
                                                    bundle.info.currency)):
        out["scenarios"] = chart
    return out
```

- [ ] **Step 4: Wire the signature in `markdown.py`**

In `src/mbe/report/markdown.py`, change the `render_report` signature (currently at line 331) from:

```python
def render_report(
    bundle: AnalysisBundle,
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
) -> str:
```

to:

```python
def render_report(
    bundle: AnalysisBundle,
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
    charts: dict[str, str] | None = None,
) -> str:
```

and add to the `_TEMPLATE.render(...)` call, after `policy_key=policy_key,`:

```python
        charts=charts or {},
```

- [ ] **Step 5: Add the trend chart to Financial Analysis**

In `src/mbe/report/markdown.py`, find:

```jinja
## Financial Analysis

| Metric | Value | Metric | Value |
```

and insert the chart above the table, so it reads:

```jinja
## Financial Analysis

{% if charts.trend %}
{{ charts.trend }}
{% endif %}

| Metric | Value | Metric | Value |
```

The table is **not** removed: it holds ratios (ROCE, margins, coverage), while the chart holds revenue/profit/cash history. They are different data.

- [ ] **Step 6: Add the Ownership section**

In `src/mbe/report/markdown.py`, insert immediately **before** the `## Financial Analysis` heading:

```jinja
## Ownership

{% if charts.ownership %}
{{ charts.ownership }}
{% if charts.ownership_note %}
**⚠ {{ charts.ownership_note }}.**
{% endif %}

*Yahoo's "insider" is not SEBI's promoter category, and this is not the promoter/FII/DII/public breakdown an Indian investor expects — that data is not in this pipeline. Descriptive only, never scored.*
{% else %}
*Ownership split not reported by the data source.*
{% endif %}

```

- [ ] **Step 7: Add the Peer Comparison section**

In `src/mbe/report/markdown.py`, insert immediately **before** the `## Risk Analysis` heading (which follows `## Valuation`):

```jinja
## Peer Comparison

{% if charts.peer_table %}
{{ charts.peer_table }}
{% if charts.peer_scatter %}
{{ charts.peer_scatter }}
{% endif %}

*The peer group is this stock's industry cohort from the same screen. Descriptive only, never scored.*
{% else %}
*Peer comparison requires a universe screen — single-ticker analysis has no peer group.*
{% endif %}

```

- [ ] **Step 8: Add the scenario chart and trim two table columns**

In `src/mbe/report/markdown.py`, in the `## 3-Year Price Forecast` section, replace:

```jinja
| Scenario | Prob. | Revenue growth | Net margin | Exit multiple | FY+3 EPS | Target | 3y CAGR |
|---|---|---|---|---|---|---|---|
{% for s in forecast.scenarios %}
| **{{ s.name | capitalize }}** | {{ s.probability | pct }} | {{ s.growth_start | pct }} → {{ s.growth_end | pct }} | {{ s.terminal_net_margin | pct }} | {{ "%.1f" | format(s.exit_multiple) }}x | {{ s.eps_fy3 | num }} | {{ s.target_price | num }} | {{ s.cagr_3y | pct }} |
{% endfor %}
```

with:

```jinja
{% if charts.scenarios %}
{{ charts.scenarios }}

{% endif %}
{% if charts.scenarios %}
| Scenario | Prob. | Revenue growth | Net margin | Exit multiple | FY+3 EPS |
|---|---|---|---|---|---|
{% for s in forecast.scenarios %}
| **{{ s.name | capitalize }}** | {{ s.probability | pct }} | {{ s.growth_start | pct }} → {{ s.growth_end | pct }} | {{ s.terminal_net_margin | pct }} | {{ "%.1f" | format(s.exit_multiple) }}x | {{ s.eps_fy3 | num }} |
{% endfor %}
{% else %}
| Scenario | Prob. | Revenue growth | Net margin | Exit multiple | FY+3 EPS | Target | 3y CAGR |
|---|---|---|---|---|---|---|---|
{% for s in forecast.scenarios %}
| **{{ s.name | capitalize }}** | {{ s.probability | pct }} | {{ s.growth_start | pct }} → {{ s.growth_end | pct }} | {{ s.terminal_net_margin | pct }} | {{ "%.1f" | format(s.exit_multiple) }}x | {{ s.eps_fy3 | num }} | {{ s.target_price | num }} | {{ s.cagr_3y | pct }} |
{% endfor %}
{% endif %}
```

The chart labels target and CAGR directly, so those two columns are redundant when it renders. The assumptions — growth, margin, exit multiple — stay in both branches, because they are the engine's reasoning and a chart cannot hold them.

- [ ] **Step 9: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py`
Expected: all PASS. If `test_report_contains_all_sections` fails because it asserts a fixed list of headings, add `Ownership` and `Peer Comparison` to that list — the new sections are intended.

- [ ] **Step 10: Verify the SVG survives markdown conversion**

Run:

```bash
.venv/bin/python -c "
import sys, re; sys.path.insert(0,'tests')
import markdown as md
from test_pipeline import StubProvider
from mbe.pipeline import analyze_ticker
from mbe.report.markdown import render_report
from mbe.report import charts
b = analyze_ticker('GOOD.NS', StubProvider())
c = charts.build_charts(b)
html = md.markdown(render_report(b, charts=c), extensions=['tables'])
svgs = re.findall(r'<svg\b.*?</svg>', html, re.S)
print('charts built:', sorted(c))
print('svgs matched:', len(svgs), 'of', html.count('<svg'))
print('all intact:', all('</p>' not in s for s in svgs) and len(svgs) == html.count('<svg'))
"
```

Expected: the chart keys print, every `<svg` is matched by a closing tag, and `all intact: True`.

**Do not test for `<p><svg`.** That is markdown wrapping the whole chart in a paragraph, which is valid and harmless — SVG is phrasing content. The real failure is a `</p>` appearing *inside* an SVG, which is what the check above looks for. An earlier draft of this plan tested the wrong string and reported a healthy chart as broken.

- [ ] **Step 11: Commit**

```bash
git add src/mbe/report/charts.py src/mbe/report/markdown.py tests/test_pipeline.py
git commit -m "feat(report): charts param, Ownership and Peer Comparison sections

The scenario table drops Target and 3y CAGR when the chart renders, since
the chart labels both; assumptions stay because a chart cannot hold them.
The Financial Analysis ratio table is untouched — it holds different data
from the trend bars."
```

---

## Task 7: Wire charts into the published site

**Files:**
- Modify: `src/mbe/publish.py` — `render_report_page` at `:181`, `render_site`'s report loop at `:349`
- Test: `tests/test_publish.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
def test_peer_bundles_returns_the_group_containing_the_ticker():
    from mbe.publish import peer_bundles

    result = _result()   # 4 bundles, one "Semiconductors" group
    peers = peer_bundles(result, "S0.NS")
    assert {b.card.ticker for b in peers} == {"S0.NS", "S1.NS", "S2.NS", "S3.NS"}


def test_peer_bundles_is_empty_for_an_ungrouped_ticker():
    from mbe.publish import peer_bundles

    assert peer_bundles(_result(), "NOTINANYGROUP.NS") == []


def test_render_site_puts_charts_on_report_pages(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    report = (tmp_path / "reports" / "S0_NS.html").read_text()

    assert "<svg" in report
    assert "Peer Comparison" in report
    # the group's other members are named on the page
    assert "S1.NS" in report or "S1" in report
    # and the svg was not split into paragraphs by markdown
    assert "<p><svg" not in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_publish.py -k "peer or charts"`
Expected: FAIL — `ImportError: cannot import name 'peer_bundles' from 'mbe.publish'`.

- [ ] **Step 3: Add the peer lookup**

In `src/mbe/publish.py`, add above `render_report_page`:

```python
def peer_bundles(result: ScreenResult, ticker: str) -> list[AnalysisBundle]:
    """The screened bundles in this ticker's industry group, including itself.

    Peer comparison is only meaningful against names analysed in the same run
    with the same data vintage, which is exactly what a ScreenResult holds.
    An ungrouped ticker (its industry had fewer than MIN_GROUP members)
    returns [], and the report says so rather than comparing against nothing."""
    for group in result.sector_scores:
        if ticker in group.members:
            by_ticker = {b.card.ticker: b for b in result.ranked}
            return [by_ticker[t] for t in group.members if t in by_ticker]
    return []
```

Confirm `AnalysisBundle` and `ScreenResult` are already imported in `publish.py` with `grep -n "from mbe.pipeline import" src/mbe/publish.py`; add whichever is missing.

- [ ] **Step 4: Thread charts through `render_report_page`**

In `src/mbe/publish.py`, change:

```python
def render_report_page(
    bundle: AnalysisBundle,
    back_href: str = "../index.html",
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
) -> str:
    """Wrap one AnalysisBundle's markdown report in the shared dark shell.
    Used by render_site() for weekly static reports and by api/analyze.py
    for live single-ticker search — one shell, one back-link parameter."""
    body = md.markdown(render_report(bundle, news=news, policy=policy),
                       extensions=["tables"])
```

to:

```python
def render_report_page(
    bundle: AnalysisBundle,
    back_href: str = "../index.html",
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
    peers: list[AnalysisBundle] | None = None,
) -> str:
    """Wrap one AnalysisBundle's markdown report in the shared dark shell.
    Used by render_site() for weekly static reports and by api/analyze.py
    for live single-ticker search — one shell, one back-link parameter.

    Charts are built here rather than in render_report so the renderer stays
    pure and the CLI's markdown output keeps its tables."""
    body = md.markdown(
        render_report(bundle, news=news, policy=policy,
                      charts=build_charts(bundle, peers)),
        extensions=["tables"],
    )
```

Add the import beside the other `mbe` imports at the top of the file:

```python
from mbe.report.charts import build_charts
```

- [ ] **Step 5: Pass peers from `render_site`**

In `src/mbe/publish.py`, change:

```python
            page = render_report_page(
                b, policy=[NewsItem(**p) for p in data.get("policy", [])]
            )
```

to:

```python
            page = render_report_page(
                b,
                policy=[NewsItem(**p) for p in data.get("policy", [])],
                peers=peer_bundles(result, b.card.ticker),
            )
```

`api/analyze.py:64` keeps calling `render_report_page(bundle, back_href=...)` with no `peers`, so live single-ticker search renders every chart except the two peer ones — which is correct, since one ticker has no peer group.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "feat(publish): build and thread report charts, with peer lookup

Peers come from the ScreenResult, so a comparison is only ever against names
analysed in the same run at the same data vintage."
```

---

## Task 8: Rebuild the site and document

**Files:**
- Modify: `site/` (generated), `CHANGELOG.md`, `README.md`

- [ ] **Step 1: Rebuild**

Run: `.venv/bin/python scripts/build_site.py`

Expected: `analyzed 250 | failed 0` and `site built:`. A traceback here means a chart raised on real data that the stub fixtures did not cover — fix the chart, do not wrap the call in try/except.

- [ ] **Step 2: Verify a real report page**

Run:

```bash
.venv/bin/python -c "
t = open('site/reports/HBLENGINE_NS.html').read()
print('svg count:', t.count('<svg'))
print('split svg (BAD):', '<p><svg' in t)
for k in ['Ownership', 'Peer Comparison', 'HBL ENGINEERING', 'SCHNEIDER', 'contradicts itself']:
    print(f'{k:22s}', k in t)
"
```

Expected: `svg count:` at least 5, `split svg (BAD): False`, and every listed string `True`. HBL is the one live pick whose ownership cross-check fires, so `contradicts itself` appearing is the cross-check working, not a bug.

- [ ] **Step 3: Check both themes**

Run:

```bash
.venv/bin/python -c "
import re
t = open('site/reports/HBLENGINE_NS.html').read()
svgs = re.findall(r'<svg.*?</svg>', t, re.S)
hexes = [h for s in svgs for h in re.findall(r'#[0-9a-fA-F]{3,6}', s)]
print('svgs:', len(svgs), '| literal colours inside svg:', hexes or 'none')
"
```

Expected: `literal colours inside svg: none`. Any hex means a chart will be invisible in one of the two themes.

- [ ] **Step 4: Update the changelog**

Insert into `CHANGELOG.md` immediately above the `## v0.14.0` heading:

```markdown
## v0.15.0 — 2026-08-01 (report charts)

### Added
- **Peer comparison** on every report: the stock against its industry cohort
  from the same screen, as a ranked table with proportional bars plus a
  quality-vs-growth scatter. HBL has the best ROCE (32.9%) and best revenue
  growth (34.5%) in its 8-name group at the second-cheapest P/E — true before
  this release, and invisible.
- **Shareholding donut**, **financial trend bars** (revenue, net income, FCF
  as small multiples, loss years below the zero line), and a **three-year
  scenario chart** whose bars run from today's price, so an all-downside
  forecast looks wrong at a glance.
- All charts are server-rendered inline SVG: no JavaScript, no dependency, no
  external request, and they follow the light/dark toggle because they
  reference the theme's CSS variables rather than literal colours.

### Fixed
- **Yahoo's ownership fields contradict each other for 4 of the 25 picks.**
  `insider_pct` disagrees with the company's own reported float by 54pp for
  HBL (8.1% claimed against ~62% implied), and by 11-21pp for three others.
  The donut draws regardless, by decision, but states the contradiction on the
  chart rather than smoothing it.

### Validation status
Descriptive only. No chart adds a pillar, a weight or a risk flag — the same
contract as sector themes, news/policy, franchise and stewardship. Charts
render values the engine already computed.
```

- [ ] **Step 5: Update the README**

In `README.md`, in the "What the page shows" bullet under "Hosted weekly picks (v0.10)", change:

```markdown
- **What the page shows** — the top-25 multibagger/investment ranking,
  week-over-week entries/exits, sector-momentum context, 3-5 recent
  headlines per pick, policy/scheme headlines per industry (each sourced
  and dated), and delayed (~15 min) quotes.
```

to:

```markdown
- **What the page shows** — the top-25 multibagger/investment ranking,
  week-over-week entries/exits, sector-momentum context, 3-5 recent
  headlines per pick, policy/scheme headlines per industry (each sourced
  and dated), and delayed (~15 min) quotes. Each pick's report page carries
  peer-comparison, ownership, financial-trend and scenario charts (v0.15) as
  inline SVG — no JavaScript, and they follow the theme toggle.
```

- [ ] **Step 6: Commit**

```bash
git add site/ CHANGELOG.md README.md
git commit -m "chore(publish): site rebuild with report charts"
```

---

## Notes for the implementer

**A blank line inside an SVG is a silent chart-killer.** python-markdown turns it into `<p><svg ...></p>`. Task 1's `test_document_never_contains_a_blank_line` and Task 8's `split svg (BAD)` check exist for this. If a chart looks empty on the page, check that first.

**Do not impute.** A missing metric renders `n/a` with no bar, never a zero-length bar — a zero bar reads as "worst in the group", which is a claim the data does not make. This rule is engine-wide, not a chart preference.

**Do not weaken an assertion to get a green suite.** If a test cannot pass, find the cause and report it. Three of this codebase's plans have shipped with factually wrong fixtures, and in each case the implementer was right and the root cause sat a layer below the test.

**Nothing here is scored.** If any task starts to feel like it wants a "peer percentile score" or a "governance score" from the ownership split, that is a different feature requiring its own pre-registered validation. Stop and ask.
