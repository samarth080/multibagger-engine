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
