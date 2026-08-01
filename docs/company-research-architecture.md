# Canonical company research architecture

> Phase 8 hardening adds keyboard-focusable labelled financial/history/peer
> scrollers, mobile/desktop WCAG-oriented audits, real-Chrome company journeys,
> complete/missing-state visual baselines, generated 404 handling, and static
> release-contract checks. Research values and provider selection are unchanged.
>
> Phase 10A adds a *lightweight* company page for the wider search universe —
> see `docs/search-architecture.md`. This document covers the full research
> page below, which this phase does not change: every existing 250 pages,
> the `CompanyResearch` schema, explanation/peer/history logic and both APIs
> are byte-for-byte unaffected. A company only ever gets the full page
> described here when it is in the research universe; otherwise it gets the
> honestly-labeled lightweight page served by `api/company.py`.

Implemented: 2026-08-01 (Phase 7)

## Route and compatibility decision

The permanent public route is `/company/{instrument_id}.html`. The path is
anchored to the immutable canonical instrument UUID, not the mutable NSE symbol
or company name. All 250 instruments in the scored weekly build receive this
page as a real static file. Global search, rankings, screener rows and peer
links now use it. Since Phase 10A the same URL pattern is canonical for every
company the search universe can identify: Vercel serves the static file when
one exists (all 250 research pages, unaffected); every other instrument ID
falls through to the serverless lightweight-page fallback instead of 404ing.

The 25 published `/reports/{ticker}.html` routes remain complete compatibility
pages. They render the same normalized research payload and declare the
instrument-ID page as canonical. They are not redirects, so old bookmarks stay
useful in static hosting and when JavaScript is unavailable. The sitemap lists
only canonical company URLs; symbol/BSE variants are not generated.

## Domain contract and build compatibility

`mbe.research.domain.CompanyResearch` schema `1.0` is the only template and API
input. Provider responses, SQLAlchemy rows and analysis bundles are normalized
before presentation. Its sections cover identity/listing, quote state,
ranking/components, deterministic summary/explanations/strengths/risks,
bounded history, approved public financials, persisted technical context,
peers, public-safe filings, thresholded news, checklist definition, lineage,
warnings and feature flags.

Static snapshots are written to
`/api/v1/research/{instrument_id}.json`. Dynamic mode returns the same model at
`GET /api/v1/instruments/{instrument_id}/research`. Templates never interpret
raw API, database, Yahoo, NSE or XBRL objects.

Model build, financial build, news cutoff and quote timestamp remain separate.
The page warns when the financial cutoff trails the model cutoff by more than
45 days, news trails by more than 14 days, source-selection policy is
unexpected, accepted data is absent, a quote is stale/unavailable, or history
is insufficient. It renders through non-material mismatches rather than
silently merging score builds.

Static/SQLite tests compare identity, ranking, explanation codes, accepted
financial metric values/source labels, technical state, peer order and history.
Decimal persistence may round beyond 11 decimal places. Allowed runtime
differences are live quote values/market state and news after the static cutoff.
PostgreSQL uses the same SQLAlchemy path but is not provisioned.

## Deterministic explanation rules

Explanation policy `2026-08-01.1` gives every item a stable code,
classification, source field IDs, values/comparison where applicable, period,
source, freshness, methodology link and version.

| Code | Rule | Classification |
|---|---|---|
| `score_vs_universe_median` | Current score versus compatible-build median | positive at/above; warning below |
| `revenue_cagr_vs_median` | Accepted 3-year Revenue CAGR versus compatible covered median | positive at/above; warning below |
| `revenue_cagr_3y_unavailable` | Accepted Revenue CAGR missing | warning |
| `roce_vs_median` | Accepted 3-year average ROCE versus compatible covered median | positive at/above; warning below |
| `roce_3y_unavailable` | Accepted ROCE missing | warning |
| `technical_trend` | `strong_up/up`, `sideways`, `down/strong_down` | positive, neutral, risk |
| `model_confidence` | coverage at least 90%, 70–89.9%, below 70% | positive, neutral, risk |
| `model_risk` | risk below 35, 35–59.9, at least 60 | positive, warning, risk |
| `rank_movement` | rank across compatible persisted builds | positive on improvement; risk on decline |
| `financial_fallback` | approved Yahoo compatibility source selected | warning; explicitly non-official |
| `partial_model_inputs` | snapshot reports missing data | warning |

Strengths are the first five positive explanations. Risks are the first five
warning/risk explanations. Missing values never create positive claims. The
summary uses only rank, score, confidence, risk, the two approved financial
metrics and source state. It contains no recommendation, target, forecast or
LLM output.

## Peer-selection policy

Peer policy `2026-08-01.1` returns at most six peers (API maximum eight), never
the company itself. Candidates must share industry or sector. The score uses:

1. same industry (100 points) before same sector (65);
2. same market-cap category when known (+15);
3. closest Multibagger Score (up to +20);
4. compatible Revenue CAGR and ROCE proximity (up to +10 each);
5. current rank then canonical instrument ID as stable tie-breakers.

Reasons expose industry/sector, market-cap, score and financial similarity.
Unrelated score lookalikes are excluded. No embeddings or external service is
used.

## Score history, financials, filings and news

History reads existing score snapshots/model builds through
`ix_scores_instrument_created`, newest 26 by default and maximum 52. Duplicate
build IDs collapse, timestamps sort in UTC and component order is stable. The
page uses a labelled lightweight SVG plus an exact semantic table. One point
explicitly says no continuous trend is inferred; no interpolation is drawn.

Only Revenue CAGR (3-year) and ROCE (3-year average) are approved public
derived metrics. Existing normalized recent facts may appear with period/unit,
but deferred ratios are not added. Yahoo is labelled `Yahoo compatibility
fallback`, Tier B and unknown-basis where applicable. Official Tier-A remains
unavailable/0 of 250; no official badge is emitted.

Filings are newest-first, bounded to 20 and use allowlisted NSE HTTPS links.
Parser evidence, raw XBRL, cache paths, review decisions and operator records
are excluded. The current static build has no public-safe filing corpus and
says so; discovery never implies acceptance.

Company news is capped at 12. Only high/medium matches at or above 55 survive,
with source, date, match reasons and safe HTTPS link. Static news currently
exists only for the published 25; other pages show an explicit unavailable
state. Low-confidence and unsafe links fail closed.

## Checklist, accessibility and security

Nine due-diligence prompts are stored locally per instrument under
`mbe-research-checklist:{instrument_id}`. IDs are validated, completion is
announced, and reset removes the key. The comparison list is limited to eight
canonical IDs. There are no notes, accounts or cloud writes.

Pages retain the shared skip link, landmarks, visible focus, theme and reduced
motion; add semantic headings/tables/timeline, non-colour classifications,
screen-reader rank/source/stale context, disclosures and exact chart summary.
Mobile makes hero, split panels, news and sidebar one column; dense tables use
labelled overflow. Real-browser keyboard, screen-reader, contrast and 200% zoom
checks remain a pre-deployment gate.

Manual pre-deployment browser checklist:

- Chrome, Safari and Firefox at 1440, 1024, 768, 390 and 320 CSS pixels;
- system/light/dark theme, reduced motion and forced-colour/high-contrast mode;
- 200% zoom with no clipped hero, sidebar, disclosures, chart/table or actions;
- skip link, heading/landmark order, visible focus and complete keyboard path;
- SVG accessible name/summary plus exact table equivalence;
- peer/financial table labels and touch scrolling without whole-page overflow;
- quote success/stale/failure without blocking server-rendered research;
- search/ranking/screener/peer and legacy navigation to the canonical page;
- filing/news external-link label, safe new-tab behavior and focus retention;
- checklist persist/reload/reset announcement and comparison/copy feedback;
- API, static fallback, mismatched-build warning and empty-news/filing/history
  states with VoiceOver or NVDA reading order;
- canonical/Open Graph metadata, sitemap inclusion and no console/CSP errors.

Unsafe URLs fail closed. Public output excludes raw provider payloads,
credentials, paths, private evidence and stack traces. CSP was not weakened.
Generated pages/payloads have route, reference, canonical and private-marker
validation.

## APIs and offline operations

Dynamic endpoints:

- `GET /api/v1/instruments/{instrument_id}/research`
- `GET /api/v1/instruments/{instrument_id}/score-history?limit=26`
- `GET /api/v1/instruments/{instrument_id}/peers?limit=6`

Offline commands:

```bash
uv run mbe company-research-validate [--instrument-id UUID]
uv run mbe company-research-inspect UUID
uv run mbe company-research-build [--instrument-id UUID] [--rebuild-derived]
uv run mbe company-research-legacy-validate
uv run mbe company-research-measure
uv run mbe company-research-parity UUID  # configured migrated DB required
```

`scripts/build_site.py` rebuilds all projections, explanations, peer
selections, JSON and pages. The offline command rerenders or re-derives from the
existing normalized public corpus. Both support one-company validation/build
scope; material failures exit nonzero.

## Measured footprint and limitations

The final build generated 250 canonical HTML pages, 250 research JSON payloads
and preserved 25 legacy pages: 6,242,441 HTML bytes and 5,908,860 JSON bytes,
averaging 24,969.76 and 23,635.44 bytes, with maxima 30,096 and 28,393. Shared
assets remain below the 40 KiB CSS, 60 KiB application JS and 50 KiB route-JS
budgets. No chart library or page-specific bundle was added.

Only current and one previous compatible static build are presently available;
history will accrue weekly. Static filings are unavailable, company news is
available only for the published 25, and BSE codes/SME/market-cap categories
are mostly absent. No PostgreSQL, deployment, commit, scoring or provider change
was introduced.
