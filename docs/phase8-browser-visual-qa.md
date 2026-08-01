# Phase 8 browser and visual QA

Date: 2026-08-01

## Outcome

Real Google Chrome 150.0.7871.187 executed the release journeys against the
generated static site. The final Chrome matrix covers rankings, screener,
methodology, canonical company pages with complete and missing financial data,
legacy routes, the not-found document, light/dark themes, JavaScript disabled,
API failure, reduced motion, and 1440/1024/768/390/360/320 CSS-pixel layouts.

The UI is coherent and information-dense at every tested width. Wide research
tables remain intentionally two-dimensional and scroll inside labelled,
keyboard-focusable regions. No page-level horizontal overflow remains.

## Evidence

- `tests/browser/release.spec.js`: end-to-end navigation, keyboard command
  search, ranking filters/sort/columns/export, screener edit/share/reload/export,
  company checklist/copy, canonical compatibility, mobile focus restoration,
  no-JS and explicit API-unavailable behavior.
- `tests/browser/responsive.spec.js`: 18 route/viewport combinations, effective
  200% browser zoom, 24 CSS-pixel minimum targets for visible buttons, reduced
  motion, and delayed enhancement.
- `tests/browser/visual.spec.js`: 11 deterministic baselines in
  `tests/browser/visual-baselines/`; operational UUIDs/timestamps are normalized
  before capture.
- Final visual comparison: 11/11 passed with no unexpected pixel differences.

Visual inspection specifically covered hierarchy, clipped content, table
scroll affordance, empty/missing-data treatment, search dialog, mobile drawer,
light/dark contrast and sticky table columns. A mobile search control that lost
its accessible name was found and fixed during this work.

## Browser matrix limitation

The configured Firefox and WebKit projects are retained for the promotion gate,
but their Playwright engine packages were not locally available. The standard
download was attempted and stalled; it was stopped without changing the
product. The in-app browser also reported no available instance. Safari 26.5.2
and Firefox 153.0.1 are installed on the Mac, but this phase does not claim
completed interaction journeys in those engines.

Cross-engine execution is therefore a required preview condition, not silently
reported as passed. Use `npm run test:browser` after installing the standard
Playwright engines; Chrome-only evidence uses `npm run test:browser:chromium`.
