# Trading-Platform UI Redesign — Zerodha-Dark / Groww-Light

**Date:** 2026-07-20 · **Status:** Approved design (visual mockups reviewed
in brainstorm session; user chose dark-default with light toggle)
**Goal:** Restyle every rendered surface of the hosted site to trading-
platform quality — Zerodha-Kite-inspired dark theme by default, Groww-
inspired light theme behind a persistent toggle — using the user's exact
palette tokens. Pure template/CSS work: zero changes to pipeline, scoring,
data, or the weekly Actions job.

## Palette tokens (user-provided, exact)

| Token | Dark (default) | Light |
|---|---|---|
| Background | `#1F2022` | `#F3F4F6` |
| Surface (cards/nav) | `#252629` | `#FFFFFF` |
| Text | `#E4E6EB` | `#2D343C` |
| Muted text | `#9B9EA4` | `#6B7280` |
| Border | `#333333` | `#DDE4F0` |
| Accent (links, scores, active tab) | `#38A6F0` | `#5076EE` |
| Gain | `#4CAF50` | `#039955` |
| Loss | `#F44336` | `#D32F2F` |

## Theme system

- CSS custom properties on `:root`; dark values are the default, a
  `data-theme="light"` attribute on `<html>` switches the set.
- ☀/☾ toggle button in the nav; choice persisted to `localStorage`; a tiny
  inline script in `<head>` applies the saved theme before first paint (no
  flash of wrong theme).
- **No Tailwind** (deliberate): Tailwind needs a build step (pipeline has
  none, by design) or a CDN script (flash + external dependency). ~150
  lines of hand-rolled CSS variables give the same visual result with zero
  new moving parts. Revisitable later.
- System UI font stack (Inter-alike on every platform, no webfont fetch).

## Surfaces (all of them — a partial redesign would clash on click-through)

1. **Index page** (`_INDEX` in `src/mbe/publish.py`):
   - Sticky top nav: brand mark, Picks / Sectors / Policy anchor tabs,
     search pill (the existing `/api/analyze` GET form) living in the nav,
     theme toggle.
   - Changes-this-week as gain/loss chips.
   - Top-25 as a card-contained table, two-line rows: company bold +
     industry/rank/theme-tag subline (also the mobile-survival strategy).
   - Score in accent color; quote cell trading-app style: **LTP + day-change
     %** primary (quotes API already returns `day_change_pct`), "since pick
     +x%" as the small second line (the product's honest differentiator
     stays visible).
   - Sector momentum + policy sections as matching cards.
   - Validation footer: styling changes, wording stays verbatim (the
     honesty is non-negotiable).
2. **Report pages** (`_REPORT_SHELL` / `render_report_page`): same nav
   treatment (brand + back + toggle), markdown content restyled to match —
   carded tables, themed headings. Weekly static reports and live-search
   reports inherit automatically via the shared shell.
3. **Analyze error pages** (`_ERROR_PAGE` in `api/analyze.py`): same tokens
   and toggle-respecting theme (reads the same localStorage key).

## Quote cell contract (small behavior change, index JS only)

The quotes JS currently shows price + since-build %. New rendering per
quote cell: line 1 `₹LTP  ±day%` (colored by day direction), line 2 muted
`since pick ±x%` (from `data-base`, unchanged). No API changes —
`day_change_pct` is already in the `/api/quotes` response.

## Testing & rollout

- All existing template tests keep passing (they assert wiring/content —
  form action, footer text, changes strip — none of which change).
- New tests: theme-toggle markup present; both token sets present in the
  emitted CSS; the saved-theme inline script present; report shell and
  error page carry the same theme system.
- Local `scripts/build_site.py` rebuild → visual check in the brainstorm
  companion browser before any deploy → commit → push → Vercel.

## Explicitly deferred

Tailwind adoption, webfonts, charts/sparklines, stock logos, mobile
hamburger nav (anchor tabs wrap acceptably at phone widths), any layout
change to report *content* (markdown structure unchanged, only styling).
