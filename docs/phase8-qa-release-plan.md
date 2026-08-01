# Phase 8 QA and release plan

Date: 2026-08-01

## Scope and candidate

The immediate release candidate is the versioned static `site/` artifact. It
must remain usable without PostgreSQL, live Yahoo, live NSE, paid services or a
runtime build step. Phase 8 may harden presentation, accessibility, security,
performance, observability and release operations, but must not change scores,
financial values, source precedence or the Phase 6 operator gate.

## Test matrix

| Dimension | Planned coverage |
|---|---|
| Browsers | System Google Chrome 150 through Playwright; Firefox 153 and Safari/WebKit 26.5 where standard local automation succeeds. Connected in-app browser is unavailable (`[]`). |
| Desktop | 1440×900 |
| Tablet | 1024×768 and 768×1024 |
| Mobile | 390×844, 360×800 and 320×720 |
| Preferences | light, dark, system, reduced motion; JavaScript disabled; 200% zoom and increased text where the engine supports deterministic automation |
| Routes | rankings/home, screener, methodology, complete company, missing-financial company, missing-news company, legacy report, static JSON and error/empty states |
| Journeys | navigation, keyboard search, rankings filters/sort/columns/export, screener preset/condition/share/export, company explanations/history/source/peer/checklist/copy, legacy canonical, mobile menu, static/API-unavailable fallbacks |
| Accessibility | axe-core, semantic/SEO validator, keyboard assertions, focus trap/return, live-region/state checks, automated contrast; VoiceOver only if an actual manual session can be completed |

## Targets

- Zero serious or critical automated accessibility violations on representative
  routes; no keyboard traps; visible focus; semantic titles, landmarks,
  headings, tables and status announcements.
- No horizontal page overflow at the viewport level from 320 CSS pixels upward;
  intentionally wide research tables remain in labelled scroll containers.
- CSS no more than 40 KiB, shared application JavaScript no more than 60 KiB,
  screener JavaScript no more than 50 KiB and research JavaScript no more than
  50 KiB, all uncompressed.
- Largest company HTML no more than 35 KiB and largest research JSON no more
  than 32 KiB; retain 250/250 page/payload coverage and readable contracts.
- Locally measured static Chrome targets under repeatable throttling: LCP no
  more than 2.5 s, CLS no more than 0.1, TBT no more than 200 ms and no
  avoidable main-thread task above 50 ms. These are laboratory gates, not a
  claim about field Core Web Vitals.
- Search, rankings and screener transformations over 250 rows remain below
  100 ms in deterministic browser measurements; timing tests use a generous
  regression ceiling rather than brittle microbenchmarks.

## Known visual and release risks

- Sticky table identity/header intersections, narrow 320-pixel layouts, long
  company/industry/news/filing text and the sticky company sidebar.
- Dialog/drawer focus, layering and background scroll locking; column popovers
  near viewport edges; table focus obscured by sticky headers.
- Dark-theme muted text, warning/negative chips, chart grid/lines and disabled
  controls may miss contrast requirements.
- Current CSP allows inline script/style, there is no `robots.txt`, immutable
  asset caching/fingerprints are absent, and deployment documentation is not yet
  consolidated.
- The static build currently depends on pre-existing provider cache contents;
  preview must not trigger ingestion. Dynamic APIs have no shared anonymous rate
  limiter and are not the immediate release candidate.
- Real Firefox/WebKit automation, VoiceOver, production/preview HTTP headers and
  field Core Web Vitals may remain external gates.

## Required configuration and evidence

- Development-only pinned browser/accessibility tooling and intentional visual
  baseline commands; no runtime browser dependency or new production variable.
- Deterministic local server, browser journeys, bounded screenshots, axe output,
  performance/payload reports, SEO/security/dependency audits, and route smoke.
- Release artifact records model and financial build IDs, cutoff, public-value
  hashes, test/browser versions and screenshot inventory.

## Release blockers and rollback criteria

Block preview for broken canonical or legacy routes, score/financial drift,
incorrect Tier-A/source labels, private-data leakage, serious/critical
accessibility failures, widespread JavaScript failure, CSP/header regression,
unusable 320-pixel layout or failed static build. Roll back for the same
conditions plus major ranking/screener failure, incorrect canonicals or a
material performance regression. The rollback target is the previous verified
static artifact/deployment; dynamic API and quote enrichment can be disabled
independently.
