# Multibagger Engine living handover

Last updated: 2026-08-02 (after Phase 11 Milestone 1 local completion)

Status: Production is live at `https://multibagger-engine.vercel.app/` from
source commit `6fb5a7e` / final tag `v1.0.0`, deployment
`EvCEEd2g9fkRVShmvAdwQeCdoZja`. Public route/function smoke, actual security and
cache headers, gzip, representative source/production hashes, Safari rendering
and production runtime logs passed. The user explicitly authorized promotion
after accepting the disclosed hosted cross-browser, real VoiceOver, hosted
axe/Lighthouse and exhaustive hosted-hash conditions for post-release closure.
Rollback deployment `rBeoLhBW8hNZv5fX3iT64nwrvCsc` remains Ready. Phase 6's
official-ingestion no-go is unchanged.

## How to use this document

This is the continuity source of truth when the conversation is compacted or a
new chat starts.

At the beginning of every phase:

1. Read this file completely.
2. Read the current architecture audit linked below.
3. Inspect `git status` and preserve all existing user/phase changes.
4. Confirm that the recorded verification state still matches the repository.
5. Continue from **Next phase**, rather than restarting the audit or Phase 0.

At the end of every phase, update this file before handing control back:

1. Change the date and current status at the top.
2. Add a row to the phase ledger.
3. Record architecture decisions and why they were made.
4. Record changed modules, migrations and environment variables.
5. Record the exact tests/builds run and their results.
6. Update known limitations and data-provider constraints.
7. Replace **Next phase** with the next concrete, bounded objective.
8. Note whether changes are uncommitted, committed, pushed or deployed.

Do not delete historical phase entries. Correct inaccurate entries explicitly
and note the correction.

## New-chat bootstrap

Use this as the first instruction after compaction:

> Read `docs/HANDOVER.md` and `docs/architecture-audit-2026-08-01.md` completely.
> Continue Multibagger Engine from the recorded next phase. Preserve all current
> working-tree changes. Implement the phase directly in the repository, verify
> it, review the diff, and update `docs/HANDOVER.md` before finishing.

## Product objective and non-negotiables

Transform Multibagger Engine into a polished, trustworthy, India-first equity
research and screening platform while preserving its differentiated research
engine.

Preserve and improve:

- Multibagger, Investment, Confidence and Risk scores.
- Quality, Growth, Financial Strength, Valuation, Momentum, Size Runway and
  Reinvestment evidence.
- Technical trend and sector/industry momentum context.
- Weekly Nifty Smallcap 250 ranking workflow.
- Curated structural themes and Indian policy context.
- Model-validation disclosures and research-tooling disclaimer.
- Missing-data honesty and batch resilience.
- India-first terminology, rupees/crores and NSE/BSE conventions.

Do not:

- Present model scores as guarantees or personalized investment advice.
- Score news, policy or sector themes without separate validation.
- Introduce fake production data.
- Couple core identity to ticker symbols.
- Build US product features during the India-first phases.
- Replace the working Python research engine merely for framework novelty.

## Source documents

- Full audit and staged roadmap:
  [`architecture-audit-2026-08-01.md`](architecture-audit-2026-08-01.md)
- Runtime configuration and data cadence:
  [`environment.md`](environment.md)
- Canonical model, identity/import rules, database, API and deployment:
  [`platform-foundation.md`](platform-foundation.md)
- Frontend architecture, routes, data modes, tokens and test commands:
  [`frontend-architecture.md`](frontend-architecture.md)
- Screener registry, query semantics, readiness, API/static and export limits:
  [`screener-architecture.md`](screener-architecture.md)
- Financial filing/fact schema, field lineage, metric dictionary, units,
  periods, basis, restatements, coverage and APIs:
  [`financial-architecture.md`](financial-architecture.md)
- Official NSE discovery, safe document cache, parser matrix, identity,
  revisions, reconciliation, precedence and legal/operational gates:
  [`official-nse-ingestion.md`](official-nse-ingestion.md)
- Measured provider/score reconciliation result:
  [`financial-reconciliation-2026-08-01.md`](financial-reconciliation-2026-08-01.md)
- Phase 6 manifest, legal/usage gate, corpus, taxonomy, review, Tier-A and
  operational workflow:
  [`phase6-official-corpus-pilot.md`](phase6-official-corpus-pilot.md)
- Phase 6 measured parser sample, coverage/conflicts and production decision:
  [`phase6-parser-accuracy-report.md`](phase6-parser-accuracy-report.md),
  [`phase6-coverage-conflict-report.md`](phase6-coverage-conflict-report.md),
  [`phase6-readiness-recommendation.md`](phase6-readiness-recommendation.md)
- Canonical company route, schema, explanations, peers, history, parity,
  accessibility, security and operations:
  [`company-research-architecture.md`](company-research-architecture.md)
- Project overview and commands: [`../README.md`](../README.md)
- Phase 9 release and authenticated-preview evidence:
  [`phase9-preview-release-report.md`](phase9-preview-release-report.md)
- Historical design specifications and plans: `docs/superpowers/`
- Original product brief: conversation attachment; its requirements are
  summarized in the audit and this handover.

## Current architecture snapshot

The repository is currently a quantitative Python research engine plus a
generated public site, not yet a conventional full-stack application.

- Runtime: Python 3.12, Pydantic 2, pandas/numpy, SQLAlchemy 2 and Alembic.
- Analysis orchestration: `src/mbe/pipeline.py`.
- Scoring: `src/mbe/scoring/`.
- Providers: `src/mbe/data/`.
- Primary production market provider: Yahoo Finance via `yfinance`; normalized
  quote reads use a provider-neutral adapter and registry.
- Additional adapters: bounded official NSE financial-result discovery and
  fixture-qualified Ind-AS XBRL, legacy NSE annual-results compatibility,
  EDGAR, NSE index constituent CSVs and Google News RSS.
- Persistence: legacy/local DuckDB in `data/mbe.duckdb` plus an Alembic-managed
  canonical relational schema targeting PostgreSQL in production and SQLite
  for local/test use. No production database has been provisioned.
- Published frontend: reusable Jinja shell/templates plus external design-token
  CSS and typed-with-JSDoc vanilla JavaScript, generated into `site/`. Primary
  HTML is statically rendered; browser enhancement uses the v1 API or snapshots.
- Dynamic Vercel functions: `api/quotes.py`, `api/analyze.py` and the ASGI
  entrypoint `api/v1.py` for typed versioned read routes.
- Local-only application: FastAPI terminal in `src/mbe/web/app.py`.
- Schedule: GitHub Actions Monday 02:30 UTC / 08:00 IST; commits `site/`, which
  triggers the existing Vercel Git deployment.
- Research/ranking universe: live Nifty Smallcap 250; all 250 scored
  instruments have canonical research pages, 25 ticker report routes remain
  compatible, and all 250 scored rows are available to the bounded screener
  snapshot. The search universe is deliberately wider (Phase 10A/10B): every
  NSE main-board/SME security plus a curated BSE cross-listing starter set
  (2,947 canonical companies) is discoverable, honestly labeled as
  research-available or not — see "Search, research and ranking universes"
  below and `search-architecture.md`.

Production remains operationally coupled to Yahoo and Google News. Official NSE
ingestion is an explicit disabled-by-default operator command, requires the
versioned pilot plus a private non-expired review record for live use, and is
never run by a public request or static build. A canonical
instrument master, persistent schema, versioned read API and interactive
application surface now exist in code. PostgreSQL is not provisioned, so the
current deployable mode remains versioned static snapshots with failure-tolerant
quote enhancement. A typed bounded screener now exists in dynamic and full
250-row static modes. Authentication and job-status orchestration do not exist.

### Search, research and ranking universes

Three intentionally different concepts, introduced explicitly in Phase 10A
after search had quietly narrowed to match the ranking universe:

- **Search universe** — everything the platform can identify. Currently
  every NSE main-board and SME listed security (2,927) from the official
  `EQUITY_L.csv`/`SME_EQUITY_L.csv` archives (`mbe.data.nse_search_master`),
  plus (Phase 10B) a small curated 20-company BSE cross-listing starter
  fixture (`mbe.data.bse_search_master`) — BSE's official endpoints were not
  reachable from this environment; see `search-architecture.md` "BSE
  coverage and honesty about sourcing". Future: full BSE main-board/SME
  breadth once a live feed is reachable.
- **Research universe** — companies with a deterministic research page.
  Currently the same 250 Nifty Smallcap companies as before. Future: the
  entire market, as coverage grows independent of what is currently scored.
- **Ranking universe** — companies currently included in the scoring model.
  Currently Nifty Smallcap 250 (identical to the research universe today,
  but conceptually separate). Future: configurable.

They are separate on purpose: **search must discover everything; ranking
must only rank what is currently modeled; research depth depends on
available data.** A company can be searchable without being ranked (Reliance
today), and could in principle have a research page without a current score
(a build failure), or be ranked without deep research history (a brand-new
addition to the model). Collapsing any two of these back into one — the
Phase 2–8 regression this phase fixes — silently limits what users can find
to whatever the scoring model currently covers. Full design in
`search-architecture.md`.

Since Phase 11 Milestone 2A, every search-universe company's position
between these three universes is expressed as one of four formal, versioned
coverage levels (Identity / Market / Financial / Full Research) rather than
an implicit modeled-or-not split — see
[`coverage-architecture.md`](coverage-architecture.md).

## Phase ledger

| Phase | Status | Completed | Verification | Deployment state |
|---|---|---|---|---|
| Phase 0 — audit and stabilization | Complete | Repository audit, entity-aware company news, quote freshness/error contract, static report news fix, structured serverless logs, security headers, environment docs, regenerated site | 331 tests passed; compileall passed; `git diff --check` passed; production build analyzed 250/250 with 0 failures | Working tree only; not committed/pushed/deployed |
| Phase 1 — canonical platform foundation | Complete | Canonical identity/master import, provider-neutral quotes, SQLAlchemy/Alembic schema, DuckDB compatibility migration, model-build/score persistence, typed `/api/v1`, static v1 contracts, operations/docs | 364 tests passed; compileall/diff/JSON checks passed; SQLite upgrade/downgrade and PostgreSQL offline migration passed; official import/validation 250/250; production build 250/250 with 0 failures | Working tree only; not committed/pushed/deployed; PostgreSQL not provisioned |
| Phase 2 — application shell, global search and rankings | Complete | Reusable shell/design system, light/dark themes, canonical command search, static/API data adapter, accessible responsive ranking table, URL filters/sorts/pages, columns/density/export, bounded quotes, methodology route and additive ranking fields | 368 Python tests and 11 frontend tests passed; ESLint/type-check/compileall/diff/JSON/migrations passed; production build 250/250 with 0 failures; deterministic DOM journeys passed; real browser unavailable | Working tree only; not committed/pushed/deployed; PostgreSQL not provisioned |
| Phase 3 — typed advanced screener | Complete | 28-field registry, AND-first validation/query planner, versioned fields/query API, full 250-row static screener snapshot, public route, presets, share state, columns/density/pagination, explainability and safe CSV | 386 Python tests and 20 frontend tests passed; ESLint/type-check/compileall/diff/JSON/migrations/query plans passed; production build 250/250 with 0 failures; real browser unavailable | Working tree only; not committed/pushed/deployed; PostgreSQL not provisioned |
| Phase 4 — normalized financial lineage | Complete | Canonical filing/fact/build/quality schema, decimal units, period/basis/restatement semantics, idempotent import, coverage, Revenue CAGR/ROCE screener fields, financial APIs and report summaries | 400 Python tests and 21 frontend tests passed; ESLint/type-check/compileall/diff/JSON/migrations/query plans/build passed; production build 250/250 with 0 failures; real browser unavailable | Working tree only; not committed/pushed/deployed; PostgreSQL not provisioned |
| Phase 5 — official NSE filing ingestion and reconciliation | Complete | Bounded typed NSE discovery, safe private document cache, fixture-qualified Ind-AS XBRL parser, source/attachment/revision lineage, latest-known/as-filed views, reconciliation/selection policy, filing APIs, source-labelled reports and operational/legal controls | 421 Python tests and 21 frontend tests passed; ESLint/type-check/compileall/diff/JSON/migrations/index plans/build/HTTP passed; production build 250/250 with 0 failures; one bounded live KFINTECH metadata/XBRL check succeeded; real browser unavailable | Working tree only; not committed/pushed/deployed; PostgreSQL not provisioned; scheduled/live bulk NSE ingestion disabled |
| Phase 6 — controlled official-corpus pilot | Complete — no-go | 12-company versioned pilot, explicit private operator-review gate, request/byte/runtime/denial stops, immutable captured-corpus manifest, versioned concept registry, fact evidence, private review workflow, independent ground truth, Tier-A/publication gate and evidence-based readiness reports | 449 Python tests and 21 frontend tests passed; ESLint/type-check/compileall/diff/JSON/HTML/migrations/offline corpus/build/HTTP passed; 8/8 captured ground-truth facts exact; 0 live requests, 0 Tier-A facts/metrics, 13 unresolved review items; public values unchanged; real browser unavailable | Working tree only; not committed/pushed/deployed; no new migration/dependency; PostgreSQL not provisioned; no operator acknowledgement or live pilot acquisition |
| Phase 7 — canonical company research | Complete | Immutable instrument-ID route for 250 companies, 25 legacy compatibility pages, typed research schema, deterministic explanations/strengths/risks/summary/peers, bounded history, approved financials, technical/filing/news states, local checklist, trust panel, static/dynamic APIs and parity | 456 Python and 24 frontend tests passed; lint/type-check/compileall/migrations/build/JSON/HTML/CSP/routes/leaks/HTTP/diff passed; public values unchanged; real browser unavailable | Working tree only; not committed/pushed/deployed; no migration/dependency/environment variable; PostgreSQL not provisioned; NSE gate untouched |
| Phase 8 — release-readiness hardening | Complete — preview conditions remain | Real Chrome journeys, 320–1440 responsive/zoom/reduced-motion coverage, axe WCAG-oriented audit, 11-state visual baselines, performance/Lighthouse evidence, generated 404/robots/favicon, noindex correction, external theme bootstrap, stricter CSP/security/cache policy, deterministic release/public-value verifier, dependency audit and deployment/rollback runbooks | 457 Python, 24 frontend and 65 real-Chrome browser tests passed; static release verifier, Lighthouse, npm/pip audits, compileall/migrations/build/JSON/HTML/SEO/CSP/public-value/diff passed | Working tree only; not committed/pushed/deployed; no migration/runtime environment variable/provider/scoring change; test-only Node dependencies; Firefox/WebKit/VoiceOver/Vercel preview gates remain; NSE no-go untouched |
| Phase 9 — controlled release | Complete — live with accepted conditions | RC1/RC2/RC3 fixed Vercel source bootstrap and FastAPI packaging; RC4 recorded validation; user explicitly authorized production; Vercel created and assigned a Production-environment deployment | 461 Python and 24 frontend passed; original 65 Chrome/11 visual remained green; RC4 preview Ready; production route/function smoke, actual headers/gzip/cache, representative hashes, Safari and runtime logs passed | Source `6fb5a7e`, tags `v1.0.0-rc4`/`v1.0.0`; production `EvCEEd2g9fkRVShmvAdwQeCdoZja` live; rollback `rBeoLhBW8hNZv5fX3iT64nwrvCsc` Ready; hosted cross-browser/VoiceOver/axe/Lighthouse/exhaustive hashes accepted for Phase 10 closure |
| Phase 10A — restore full Indian market discovery (regression fix) | Complete | Separated search/research/ranking universes; additive official NSE main-board/SME search-universe source and pinned snapshot (~2,950 securities); `mbe.search` catalog/ranking package; additive `search-index.json` static artifact; lightweight (lightweight-page-badged) company page for non-research companies; `/company/{id}.html` serverless fallback (`api/company.py`) for every non-research instrument; broadened quote whitelist and 52-week range; additive `GET /api/v1/search` and `GET /api/v1/company/{id}/summary`; additive `search-universe-import` CLI; frontend search UX/badges and truthful homepage/search copy | 545 Python tests (+84) and 25 frontend tests (+1) passed; ESLint/type-check/compileall/`git diff --check` passed; static release verifier passed (279 HTML, 508 JSON — one additive file, 250 company, 25 legacy, 253 indexable/sitemap — both public score/financial hashes unchanged); `instruments.json` contract byte-identical; no migration/canonical-ID/scoring/ranking/financial-value/provider-selection change; real browser unavailable | Working tree only; not committed/pushed/deployed; PostgreSQL still not provisioned, so production search is served by the static path (`search-index.json` + `api/company.py`); the dynamic `/api/v1/search` route and `search-universe-import` CLI are additive/ready but unused until a database exists |
| Phase 10B — search-quality upgrade: BSE coverage, cross-listing, ranking v2 | Complete | Additive BSE search-universe provider + honestly-labeled 20-company curated starter fixture (ISIN-cross-checked; live BSE fetch verified unreachable from this environment); NSE/BSE cross-listing bridge (`import_instruments` new-exchange-listing branch, no migration — reused existing `InstrumentListingRow` columns); multi-listing `SearchIndexRecord`/`ExchangeListing`; versioned search-ranking policy 2 (`SEARCH_RANKING_POLICY_VERSION`) with a full-phrase tier, exchange-aware `NSE:`/`BSE:` query parsing, and documented bounded tie-breakers; classification backfill-without-overwrite (`sector_source`/`industry_source`); listing-status awareness end to end; additive `GET /api/v1/search/meta` and extended `/api/v1/search`, `/api/v1/company/{id}/summary`; enriched lightweight company page (BSE code, all listings, inactive-listing banner); frontend BSE/status badges and exchange-hint search; length-ratio fuzzy-matching performance guard; deterministic search-quality evaluation harness and CLI (`search-quality-evaluate`, `search-inspect`, `bse-search-universe-import`) | 615 Python tests (+70) and 28 frontend tests (+3) passed; ESLint/type-check/compileall/`git diff --check` passed; static release verifier passed (279 HTML, 508 JSON, 250 company, 25 legacy, 253 indexable/sitemap — both public score/financial hashes unchanged, byte-identical to Phase 10A); `instruments.json` contract untouched; search-quality evaluation 100% top-1 accuracy / 100% top-3 recall / 0 false positives on the real 2,947-record merged index; client-side search latency improved ~24.5ms→~16.1ms mean, server-side ~66ms→~35ms mean; no migration/canonical-ID/scoring/ranking/financial-value/provider-selection change; real browser unavailable | Working tree only; not committed/pushed/deployed; PostgreSQL still not provisioned; BSE coverage remains a 20-company curated fixture pending a reachable official feed; dynamic BSE-aware routes are additive/ready but unused until a database exists |
| Phase 10C Milestone 1 — classification provenance, reconciliation and coverage reporting | Complete | Versioned classification-source policy (`mbe.search.classification`, `CLASSIFICATION_POLICY_VERSION`) replacing the Phase 10B ad hoc single-string backfill; every source's classification claim is kept side by side and reconciled through a documented priority rule (exchange-provided > index-provider > research-universe > documented-public for filling a gap; a research-universe claim, once present, is never silently overwritten); conflict/missing/stale review states with a full audit trail; measured coverage report by exchange and main-board/SME with source distribution (`classification-coverage-report` CLI); `docs/classification-policy.md` | 625 Python tests (+10) passed; ESLint/compileall/`git diff --check` passed; static release verifier passed (unchanged file counts and hashes — additive `SearchIndexRecord` fields only); measured coverage unchanged in substance (industry 270/2,947, sector 0/2,947) but now versioned and conflict-tracked (0 conflicts found in the real fixtures); no migration/canonical-ID/scoring/ranking/financial-value change | Working tree only; not committed/pushed/deployed; no DB persistence of multi-source provenance yet — deferred to the static/dynamic-parity milestone |
| Phase 10C Milestone 2 — search ranking policy v3, defensible prominence signals | Complete | `SEARCH_RANKING_POLICY_VERSION` `"2026-08-02.10c.2"` — version-2 primary match tiers frozen byte-for-byte; new documented late tie-break stage (requested-exchange, broad-index membership — structurally present, inert pending real index data —, main-board, research availability, ranking availability, Milestone 1 classification quality); per-candidate evidence fields (`match_reason`, `matched_field`, `prominence_signals`, `ambiguity_warning`, etc.) on `SearchCandidate`/`SearchResultData`/the JS mirror; `InstrumentResolver` (DB-backed `/api/v1/search`) and `app.js`'s `staticSearch` both reordered to the same tie-break priorities via shared helpers/a checked-in parity fixture (`tests/fixtures/search-ranking-parity.json`); expanded `EVALUATION_SET` (group queries for Reliance/Tata/HDFC/ICICI/Bajaj/Mahindra/Adani, exchange-aware queries, CAMS/IEX collision cases) with new metrics (mean reciprocal rank, exact-BSE/ISIN accuracy, group-query recall, exchange-mismatch rate); compact match-evidence line in the search UI | 658 Python tests (+33) and 35 frontend tests (+7) passed; ESLint/TypeScript/compileall/`git diff --check` passed; static release verifier passed unchanged (279 HTML, 508 JSON, 250 company, 25 legacy, 253 indexable/sitemap; public score/financial hashes byte-identical to Phase 10A/10B/Milestone 1: `12a5ef89c5584…` scores, `3e992181163743…` financials); real-universe search-quality evaluation 100% top-1/top-3, 0 false positives, exit 0 (41-case evaluation set); classification coverage unchanged (industry 270/2,947, sector 0/2,947, 0 conflicts); ad hoc server-side (Python, real 2,947-record merged index, 200-run mean) latency: exact-symbol 20.9ms, exact-BSE-code 23.4ms, group/prefix 22.5ms, guarded-fuzzy 132.8ms — identical (133.3ms) on the unmodified Phase 10B/Milestone-1 `ranking.py`, confirming v3 adds no measurable overhead even on the most expensive tier; client-side (Node, same index) mean: exact-symbol 13.7ms, exact-BSE-code 14.3ms, group/prefix 14.4ms, guarded-fuzzy 37.5ms; no migration/canonical-ID/scoring/ranking/financial-value change | Working tree only; not committed/pushed/deployed; `site/` static build was **not regenerated** this milestone — this sandboxed environment's `scripts/build_site.py` always re-screens live via Yahoo, which would rotate ranking-universe membership and financial values (confirmed: a test rebuild attempted here changed 790 files including a universe entry/exit) — out of scope and reverted; broad-index membership (Nifty 50/Next 50/100/200/500) tie-break is real code with no real data yet; classification conflict-tracking is not available on the DB-backed API path (Milestone 1 scoped provenance to the static JSON catalog only); a pre-existing version-2 primary-tier interaction (fixed-score `full_phrase_match` outranking a long-remainder `company_name_prefix` match) makes "Mahindra" rank Kotak Mahindra Bank/Tech Mahindra ahead of M&M itself — M&M remains discoverable, just not first, and fixing this needs primary-tier score recalibration this milestone was told not to do casually |

## Phase 0 implementation details

### Entity-aware company news

Implemented in `src/mbe/data/news_rss.py`.

- Added relevance score, match confidence, match reasons and source quality.
- Queries use company-name variants and exchange/country-anchored symbols.
- A title is independently evaluated after query retrieval; query membership is
  never treated as proof of identity.
- Low-confidence items below 55/100 are hidden.
- Bare/ambiguous ticker matches do not pass.
- A different explicitly declared `NSE:` or `BSE:` symbol is contradictory.
- Generic industry nouns do not count as distinctive company identity.
- One-token group names cannot identify a sibling company by themselves.
- Near-duplicate title clustering supplements exact deduplication.
- Cache namespace is versioned as `NEWS_MATCH_VERSION = "v5"` so stale matcher
  results cannot survive CI's six-day cache TTL.

Live review after the final build:

- 19/25 published picks had accepted company news.
- All published company-news items scored at least 55.
- BLS medical, sports, US-government and architecture collisions were removed.
- `NSE:BLSE` was rejected for `BLS.NS`.
- ACE and VIJAYA abbreviation/name collisions were removed.
- IEX and IGIL retained explicitly corroborated company stories.

Google News RSS does not provide article bodies. This remains conservative
title-level matching, not full named-entity recognition.

### Quote reliability

Implemented in `api/quotes.py` and rendered by `src/mbe/publish.py`.

The endpoint now returns:

- Current price, previous close, absolute change and percentage change.
- Currency, exchange and Yahoo provider identity.
- Quote timestamp and market status.
- Exchange-reported delay when Yahoo supplies it; unknown stays unknown.
- Stale status and human-readable stale reason.
- Per-symbol provider failures and overall `ok`, `partial` or `unavailable`
  status.

The whitelist now fails closed if `site/data.json` is unavailable, instead of
turning the endpoint into an unrestricted Yahoo proxy. The frontend displays
market status, IST timestamp, reported delay, stale state and explicit
unavailable messages.

A live read-only smoke test for `BLS.NS` returned a valid INR/NSI quote with
previous close, daily change, closed-market state and UTC timestamp. Yahoo did
not provide delay metadata for that response, and the application does not
invent a delay value.

### Static report correction

`render_site()` previously included company news on the ranking index but did
not pass it to each static report despite comments/tests implying it did. It now
reconstructs and passes the published ticker's `NewsItem` objects into
`render_report_page()`.

### Serverless safeguards

- `api/analyze.py` and `api/quotes.py` emit JSON-shaped operational logs.
- Client error pages do not expose unexpected exception details.
- Added `X-Content-Type-Options`, referrer policy and frame protection where
  appropriate.
- Rate limiting is still absent and remains required before broader public API
  expansion.

## Phase 0 changed files

Source and API:

- `src/mbe/data/news_rss.py`
- `src/mbe/publish.py`
- `src/mbe/cli.py`
- `scripts/build_site.py`
- `api/quotes.py`
- `api/analyze.py`

Tests:

- `tests/test_news_rss.py`
- `tests/test_quotes_fn.py`
- `tests/test_publish.py`

Documentation:

- `README.md`
- `docs/architecture-audit-2026-08-01.md`
- `docs/environment.md`
- `docs/HANDOVER.md`

Generated deployment output:

- `site/data.json`
- `site/index.html`
- 25 files under `site/reports/`

There were no database migrations and no new environment variables.

## Phase 1 implementation details

Full setup, identity rules, ER diagram, endpoint examples, migration/rollback
and Vercel notes are in [`platform-foundation.md`](platform-foundation.md).

### Canonical identity and instrument master

- Added immutable UUID instrument/company identity models. ISIN is the
  strongest bootstrap/continuity key; ticker and provider symbols are mutable
  mappings, never new-schema primary keys.
- Added normalized exchanges, listings/history, aliases/former names,
  provider-symbol mappings, sectors/industries, indices and memberships.
- Added conservative ranked resolution for NSE symbol, BSE code, ISIN,
  provider symbol, name, alias/former name, prefix and guarded fuzzy matches.
  Every candidate explains why it matched; ambiguous required lookups return
  409 rather than guessing.
- Added the official `NiftyIndexInstrumentProvider`, schema validation, source
  hash/timestamp and a version-controlled 250-record master snapshot with
  company name, NSE symbol/series, ISIN and industry.
- The idempotent transactional importer reports creations/updates/unchanged,
  symbol/alias changes, collisions, ambiguous/invalid rows, listing state,
  index membership changes, duration and source version. Empty inputs fail
  closed; dry runs roll back; unresolved records persist for review.
- The pinned and live official sources both contained 250 unique records and
  matched the production universe exactly on 2026-08-01. BSE code, listing
  date, SME status and inactive history remain null where the source does not
  supply them.

### Relational persistence and migrations

- Added SQLAlchemy 2 models and frozen Alembic revision `20260801_0001` for 18
  canonical tables plus `alembic_version`.
- Production target: PostgreSQL through `psycopg`; local/test compatibility:
  SQLite. Serverless mode uses `NullPool` and an eight-second connection
  timeout so function instances do not retain idle database connections.
- DuckDB remains the legacy research ledger. Additive migration 1 creates a
  migration ledger and adds `instrument_id`/`build_id` linkage without
  rewriting or dropping existing history.
- Added explicit UTC-capable timestamps, foreign keys, check/unique constraints,
  partial unique indexes for current listings/provider symbols, and indexes
  for identity lookup, filters, latest builds, rankings and score history.
- Query-plan inspection used indexes for exchange-symbol lookup,
  provider-symbol lookup, latest complete build and build score ordering.

### Model builds, scores, lineage and freshness

- Added model manifests with model/factor versions, deterministic factor hash,
  universe content version, cutoff/build times, provider versions,
  attempted/scored/failed counts, duration and validation status.
- Existing scoring weights/math were not changed.
- Added normalized score snapshots and component rows keyed by build and
  instrument, including rank, scores, confidence, risk, investability,
  signal/flag counts, coverage and missing-data state.
- Instrument imports and model builds write unified fresh/delayed/stale/
  missing/failed/unknown lineage records. Missing values are never written as
  zero.

### Provider abstraction and quotes

- Added focused capability protocols for instrument masters, quotes,
  historical prices, financial statements, corporate actions, index
  membership, announcements and news. Unsupported operations are explicit;
  no fake implementations were added.
- Added a small provider registry for defaults, health and mock substitution.
- Yahoo chart data now normalizes canonical/provider IDs, exchange/currency,
  OHLCV, previous/current/change values, market state, source/retrieval times,
  delay, freshness/quality and safe errors.
- The Phase 0 `/api/quotes` route is a compatibility wrapper around this
  adapter. Its fail-closed whitelist and partial failures remain intact.
  Quote batches use bounded concurrency because Yahoo's chart route is
  one-symbol-per-request.

### Versioned read API and static compatibility

Added typed routes:

- `GET /api/v1/health`
- `GET /api/v1/status`
- `GET /api/v1/instruments`
- `GET /api/v1/instruments/lookup`
- `GET /api/v1/instruments/{instrument_id}`
- `GET /api/v1/rankings`
- `GET /api/v1/rankings/{instrument_id}`
- `GET /api/v1/quotes`
- `GET /api/v1/methodology`

Contracts use `data`, `meta`, `errors`, `warnings`, `freshness` and sanitized
request IDs. They enforce typed pagination/filter/sort/search input, 100-row
page and 30-quote limits, safe 400/404/409/422/429/500/503 responses,
same-origin CORS by default, optional origin allowlist, security headers and
structured logs. No raw provider/database error or secret is returned.

The static publisher remains database-independent. `site/data.json` now has
schema `1.0`, canonical IDs/ISINs and a model manifest, and the build emits
`site/api/v1/instruments.json`, `rankings.json` and `status.json`. Existing
index/report URLs and quote UI remain unchanged.

### Phase 1 changed files and dependencies

Primary new modules:

- `src/mbe/models/instrument.py`
- `src/mbe/instruments/`
- `src/mbe/db/`
- `src/mbe/api/`
- `src/mbe/data/instrument_master.py`
- `src/mbe/data/market.py`
- `src/mbe/data/registry.py`
- `src/mbe/versioning.py`
- `api/v1.py`
- `migrations/`, `alembic.ini`
- `universes/nifty-smallcap250-instruments.json`
- `docs/platform-foundation.md`
- six new test modules covering identity/import/provider/persistence/API/master
  snapshot behavior.

Updated compatibility/operations files include `src/mbe/storage.py`,
`src/mbe/publish.py`, `src/mbe/cli.py`, `scripts/build_site.py`,
`api/quotes.py`, `vercel.json`, `README.md`, `docs/environment.md`, this audit,
the handover and generated `site/` output.

New runtime dependencies: SQLAlchemy, Alembic, Mako (transitive), psycopg and
psycopg-binary. New documented environment variables:
`MBE_DATABASE_URL`, `MBE_MIGRATION_DATABASE_URL`,
`MBE_DATABASE_POOL_MODE`, `MBE_CORS_ORIGINS` and `MBE_API_PORT`. Safe
placeholders are in `.env.example`; no secrets or paid services were added.

## Phase 2 implementation details

Full route/data-mode/component/accessibility/performance documentation is in
[`frontend-architecture.md`](frontend-architecture.md).

### Incremental frontend architecture

- Kept the Python/Jinja publisher and Vercel static output; no client framework,
  runtime state library, icon bundle or production Node build was introduced.
- Moved the product surface into reusable templates and external source assets
  under `src/mbe/frontend/`; `render_site()` copies assets and emits the index,
  methodology, snapshots and legacy reports together.
- The primary ranking table remains in HTML for no-JavaScript rendering. One
  browser domain model normalizes either database-backed `/api/v1` envelopes or
  static `.json` envelopes and refuses to merge mismatched build IDs.
- `auto` mode probes the dynamic service once and remembers static fallback for
  the browser session; explicit `api` and `static` modes are documented.

### Shell and design system

- Added shared header, primary/mobile navigation, page context, data-mode status,
  research disclaimer, skip link, canonical/Open Graph metadata and an indexable
  methodology page.
- Added maintainable colour/type/spacing/radius/surface/status/focus/table/
  breakpoint/z-index tokens. System theme is the default; a pre-paint local
  override supports polished light and dark modes without accounts.
- The approved dark-professional, information-dense direction is retained. Red
  and green are limited to signed financial/status meaning and paired with text
  or directional shapes.
- Screener and Calendar are labelled as later-phase destinations rather than
  linked to fake pages. Overview, Multibagger, Sectors, News and Methodology
  point to working content.

### Canonical search and rankings

- Added a command-palette search opened by the header, `/` or Ctrl/Cmd+K, with
  debounce, recent-search persistence, arrow navigation, explicit match reasons,
  safe fuzzy thresholds and focus restoration/trapping. Short tied aliases and
  fuzzy-only results require explicit selection.
- Static search now covers all 250 pinned canonical instruments rather than only
  the published 25. Top-25 results open their stable report; other master results
  use the existing working `/api/analyze` route.
- Added stable server/client sorting, API/static pagination, company/sector/
  industry/score/confidence/risk/trend/rank filters, removable chips, validated
  URL state, reset, column visibility, density, CSV export, sticky headers and
  keyboard row movement.
- Added score bars/components, concise positive/risk explanations, rank movement
  where history exists, matched headline confidence in row details, missing-data
  states and snapshot/build/freshness metadata.
- Quotes are requested only for the visible page in deduplicated batches up to
  30. Dynamic mode uses canonical IDs; static mode uses the fail-closed legacy
  whitelist. Quote failure remains per-row and never blocks rankings.

### Dynamic contract and migration

- Additive Alembic revision `20260801_0002` adds nullable technical trend,
  positive-signal explanation and risk explanation fields plus a build/trend
  index. Existing scores remain readable and are not rewritten.
- Dynamic rankings now accept company search, rank range, technical trend and a
  wider stable sort set, and return components/previous-rank context where
  available.
- Lookup candidates include available BSE/ISIN/classification/listing metadata
  without changing canonical resolution precedence.

### Phase 2 changed files and dependencies

Primary new files:

- `src/mbe/frontend/` templates and browser assets.
- `docs/frontend-architecture.md`.
- `migrations/versions/20260801_0002_ranking_interactions.py`.
- `package.json`, `package-lock.json`, `eslint.config.js` and
  `tsconfig.frontend.json`.
- `tests/frontend/` deterministic data/search/ranking and generated-DOM tests.
- Generated `site/assets/` and `site/methodology.html`.

Updated Phase 2 integration files include `src/mbe/publish.py`,
`src/mbe/api/app.py`, `src/mbe/api/schemas.py`, `src/mbe/db/models.py`,
`src/mbe/db/repository.py`, `src/mbe/instruments/resolution.py`,
`tests/test_publish.py`, `tests/test_api_v1.py`, `vercel.json`, `.gitignore`,
`.env.example`, `README.md`, environment/platform/audit docs, static v1
snapshots, the ranking index and all 25 report shells.

New dependencies are development-only ESLint, TypeScript and jsdom; they do not
enter production assets. New public environment variables are
`MBE_FRONTEND_DATA_MODE` and `MBE_PUBLIC_SITE_URL`. No secrets, analytics,
tracking, paid service or model-weight change was introduced.

## Phase 3 implementation details

Full field/operator/readiness/API/static/URL/export/security documentation is
in [`screener-architecture.md`](screener-architecture.md).

### Typed registry and query domain

- Added a stable `1.0` screener schema and `2026-08-01.1` field registry with
  28 public fields covering identity/classification, current and prior rank/
  score movement, model scores, risk/coverage, technical trend, seven validated
  score pillars and two display-only explanations.
- The registry owns labels, descriptions, categories, types, units, operators,
  null behavior, allowed values, filter/sort/export capability, availability,
  source, freshness, formatting, width and static/dynamic support.
- Top-level conditions are ANDed; categorical selections use OR inside
  `any_of`; ranges are inclusive. Missing values never pass ordinary or
  negative comparisons. `is_missing`/`is_available` are explicit.
- Validation rejects unknown fields/operators, wrong types, invalid ranges,
  duplicates, excessive conditions/columns/sorts/page sizes/selections/text,
  incompatible schemas and excessive complexity with stable error codes.
- Initial limits: 12 conditions, 16 columns, 3 sorts, 100 rows/page, 250 export
  rows, 20 categorical values, 80 text characters, complexity 80 and a 64 KiB
  POST body boundary.

### Dynamic API and query engine

- Added `GET /api/v1/screener/fields` (`/metadata` compatibility alias) and
  `POST /api/v1/screener/query`, including count-only reuse of the same planner.
- SQLAlchemy expressions come only from the registry mapping. Client field
  names, operators and values never become SQL fragments; all values remain
  bound parameters.
- Filters, counts, stable multi-sort, canonical-ID tie-breaking and pagination
  execute in SQL. Prior rank/score use the immediately preceding complete build;
  score pillars use correlated lookups through the existing
  `(score_id, component_name)` unique index.
- Responses include applied filters, effective sorting, columns, matched
  conditions/actual values, pagination, build/dataset/freshness metadata,
  mode, request ID, warnings, query timing and a stable fingerprint.
- Representative component filtering performed four SELECTs regardless of
  result count. SQLite plans used existing build/score, build/instrument and
  component indexes. No new migration or index was justified.

### Static compatibility and public route

- The weekly build emits `screener-fields.json` plus a normalized
  `screener.json` containing all 250 successfully scored weekly companies.
  Rankings remain the separately published top 25. Static screener rows include
  canonical IDs, build/cutoff/generated metadata and comparable prior rank/
  score changes when an earlier Phase 3 snapshot exists.
- Added `/screener.html` in the shared shell. It has searchable grouped fields,
  type-specific values, categorical multi-select, add/edit/remove/clear,
  transparent editable presets, count, stable sort, pagination, registry-driven
  columns/formatting, density, matched-condition explanations and report/
  analysis destinations.
- One normalized browser model selects the API or compatible static contracts
  and refuses registry/build mismatch. Auto mode remembers a database fallback
  for the session.
- Share state is bounded versioned base64url JSON in the `screen` parameter;
  unknown/malformed values reset or are removed with a visible warning and
  back/forward navigation replays the state.
- CSV includes canonical ID, model build ID, data cutoff, generated timestamp
  and visible fields. Formula-leading cells are neutralized. Dynamic export
  reuses bounded 100-row queries up to 250; static export is local.

### Field readiness and deliberate deferrals

- Public: canonical name/symbol/exchange/sector/industry; rank and rank/score
  movement; Multibagger/Investment/Confidence/Risk; signal/flag/coverage/
  missing state; technical trend; Quality/Growth/Financial Strength/Valuation/
  Momentum/Size Runway/Reinvestment pillars; concise explanations.
- Deferred: market cap, live/build price filters, raw returns, ROCE, growth,
  margins, leverage, interest coverage, PE/PB/PEG and other financial ratios.
  Although several have strong local coverage, they remain ticker/JSON keyed
  and lack normalized period, unit, consolidation, filing/restatement and
  source lineage.
- Sector Momentum remains descriptive and is not a registry filter because its
  registered ablation failed. Live quotes never control screen membership.

### Phase 3 changed files and dependencies

Primary new files:

- `src/mbe/screener/` domain, registry and SQL/static engine.
- `src/mbe/frontend/templates/screener.html`.
- `src/mbe/frontend/assets/screener.js`.
- `tests/test_screener.py` and Phase 3 frontend unit/DOM tests.
- `docs/screener-architecture.md`.
- Generated `site/screener.html`, `site/api/v1/screener-fields.json` and
  `site/api/v1/screener.json`.

Updated integration files include `src/mbe/api/app.py`,
`src/mbe/api/schemas.py`, `src/mbe/publish.py`, `scripts/build_site.py`, shared
templates/CSS, frontend tooling/tests, README, platform/frontend/environment/
audit docs, this handover and generated site output.

No runtime or development dependency, database migration, environment variable,
secret, paid provider, analytics integration or model-weight change was added.

## Phase 0 verification record

Latest full test command:

```bash
uv run pytest
```

Result: 331 passed in 5.28 seconds, with one pre-existing
FastAPI/Starlette `httpx` deprecation warning.

Syntax verification:

```bash
.venv/bin/python -m compileall -q src api scripts tests
```

Result: passed.

Diff validation:

```bash
git diff --check
```

Result: passed.

Final production build:

```bash
MBE_CACHE_TTL_HOURS=144 MBE_THROTTLE_SECS=0 \
  .venv/bin/python scripts/build_site.py
```

Result:

- Screened 250.
- Analyzed 250.
- Failed 0.
- Company news for 19/25 picks.
- 90 policy items from 20/20 queried sectors.
- Rebuilt `site/index.html`, `site/data.json` and 25 reports.
- Generated build timestamp: `2026-07-31T21:36:42.196937+00:00`.

## Phase 1 verification record

Latest complete regression:

```bash
uv run pytest
```

Result: 364 passed in 6.34 seconds. The only warning is the existing
FastAPI/Starlette TestClient `httpx` deprecation; no test was removed.

Syntax and repository checks:

```bash
.venv/bin/python -m compileall -q src api scripts tests migrations
git diff --check
.venv/bin/python -m json.tool vercel.json
```

Result: all passed.

Migration verification:

- Frozen Alembic revision `20260801_0001` upgraded and downgraded a new SQLite
  database successfully.
- `alembic check` against the upgraded schema reported no new upgrade
  operations, confirming migration/ORM metadata parity.
- PostgreSQL offline migration rendering completed successfully (320 SQL
  lines), proving dialect compilation without contacting a database.
- A handcrafted pre-migration DuckDB fixture opened through `RunStore`, kept
  its old history readable and received additive migration version 1.

Instrument-master operational verification against a temporary migrated DB:

- Pinned official snapshot: 250 read, 250 instruments and index memberships
  created, 0 ambiguous, 0 invalid.
- Live official source content hash: `sha256:94c317be611993fe`.
- Live official dry rerun: 250 unchanged, 0 created/updated/collisions/
  ambiguous/invalid, no membership changes.
- Mapping validation: 250 expected, 250 resolved, 0 missing, 0 collisions.
- Schema status: revision `20260801_0001`, 19 tables including
  `alembic_version`, 250 instruments.
- Exact live/pinned universe comparison: 250 vs 250, no additions/removals;
  all 250 live rows supplied name, ISIN and industry.

Query-plan inspection confirmed indexed searches for exchange symbol,
provider symbol, latest completed build and score ordering within a build.

Final Phase 1 production build:

```bash
MBE_CACHE_TTL_HOURS=144 MBE_THROTTLE_SECS=0 \
  .venv/bin/python scripts/build_site.py
```

Result:

- Screened/analyzed 250/250; failed 0.
- Company news for 19/25 picks.
- 90 policy items from 20/20 queried sectors.
- Rebuilt legacy site output and 25 report URLs.
- Emitted three static v1 contracts with canonical ISIN-based IDs.
- Build ID: `f5d909bc-0c99-44cb-be8c-16cd7e646dda`.
- Build timestamp: `2026-07-31T22:25:25.247959+00:00`.
- Factor configuration hash prefix: `c952c0365bc6`.
- Unknown SME status remained null for all 25 published rows; it was not
  fabricated as false.

No lint or static type-check command is configured in `pyproject.toml`. Do not
claim those checks ran. Add a deliberate lint/type-check configuration in a
future reliability phase rather than silently substituting a different tool.

Phase 2 correction: Python lint/type checking remains unconfigured, but the new
browser asset now has deliberate ESLint and TypeScript `checkJs` commands in
`package.json`; those checks are recorded below.

## Phase 2 verification record

Python regression:

```bash
uv run pytest
```

Result: 368 passed in 7.68 seconds. The only warning remains the existing
FastAPI/Starlette TestClient `httpx` deprecation. No Python test was removed.

Frontend checks:

```bash
npm run check
```

Result: ESLint passed, TypeScript `checkJs` passed, and 11/11 Node tests passed.
The tests cover exact/fuzzy/ambiguous search ranking, URL validation,
normalization/build mismatch, composed ranking filters, stable sorting, API
query mapping, CSV export, static fallback and generated-DOM journeys for
keyboard search, mobile navigation, themes, filters, sorting and density.
`npm audit` reported zero known vulnerabilities after `npm ci`.

Syntax, contracts and repository checks:

```bash
.venv/bin/python -m compileall -q src api scripts tests migrations
.venv/bin/python -m json.tool vercel.json
.venv/bin/python -m json.tool site/data.json
.venv/bin/python -m json.tool site/api/v1/{instruments,rankings,status}.json
git diff --check
```

Result: all passed. A local HTTP smoke test loaded `/`, `/methodology.html` and
the static instrument snapshot. `lxml` parsed the index, methodology and 25
reports and confirmed unique IDs, main landmarks, skip links and safe rel values
on external index links.

Migration regression:

- A new SQLite database upgraded through `20260801_0001` and
  `20260801_0002`; `alembic check` reported no new operations.
- `20260801_0002` downgraded to `20260801_0001`, re-upgraded and then the full
  chain downgraded to base successfully.
- PostgreSQL offline rendering completed at 332 SQL lines without a connection.

Final Phase 2 production build:

```bash
MBE_FRONTEND_DATA_MODE=auto MBE_CACHE_TTL_HOURS=144 \
  MBE_THROTTLE_SECS=0 uv run python scripts/build_site.py
```

Result:

- Screened/analyzed 250/250; failed 0.
- Company news for 19/25 picks.
- 90 policy items from 20/20 queried sectors.
- Full static search master 250; published rankings 25; report URLs 25.
- Schema `1.1`; build ID `f9661845-72b3-428a-af8a-e9f11ba8d6ed`.
- Build timestamp `2026-08-01T05:14:22.035176+00:00`.
- Uncompressed/gzip sizes: index 110,193/38,565 bytes; JavaScript
  51,461/14,190; CSS 23,736/5,373; ranking snapshot 115,224/26,405; lazily
  searched instrument snapshot 210,457/19,198.
- Production Python build still has no Node runtime/build dependency.

The in-app Browser skill was followed, but browser discovery returned an empty
list. Therefore no screenshots, real-engine viewport inspection or manual
screen-reader pass was possible. Deterministic DOM keyboard/responsive-state
tests passed, but real desktop/tablet/mobile visual and assistive-technology QA
remains a pre-deployment check. Do not claim screenshots were captured.

## Phase 3 verification record

Python regression:

```bash
uv run pytest
```

Result: 386 passed in 7.06 seconds. The only warning remains the existing
FastAPI/Starlette TestClient `httpx` deprecation. No test was removed.

Frontend checks:

```bash
npm run check
```

Result: ESLint passed, TypeScript `checkJs` passed and 20/20 Node tests passed.
Phase 3 tests cover registry uniqueness/completeness, URL round trips/recovery,
AND/null/range/categorical/boolean semantics, stable multi-sort, static/API
compatibility, formula protection and generated DOM journeys for field/operator
selection, condition creation/removal, presets, result count, sorting,
explainability, share copy, keyboard row movement and static fallback.

Syntax, contracts, security and generated-page checks:

```bash
.venv/bin/python -m compileall -q src api scripts tests migrations
.venv/bin/python -m json.tool vercel.json
for file in site/data.json site/api/v1/*.json; do
  .venv/bin/python -m json.tool "$file" >/dev/null
done
git diff --check
```

Result: all passed. JSON validation covered every static v1 contract. `lxml`
parsed the index, screener, methodology and 25 reports (28 pages), confirmed
unique IDs/main landmarks/skip links/external rel safety, and resolved all local
page/asset references. Local HTTP smoke loaded `/`, `/screener.html`,
`/methodology.html` and the screener snapshot. CSP still contains no
`unsafe-eval`; source and generated assets match.

Cross-mode and query verification:

- Deterministic fixtures matched SQLite SQL and Python reference-static
  membership/order for score+risk, sector+trend, rank movement, missing values,
  inclusive ranges and two-field sorting.
- Browser JavaScript tests independently exercised equivalent static semantics.
- A representative score+component query used existing indexed lookups and a
  fixed four SELECTs with no N+1 behavior.

Migration regression (no Phase 3 migration was added):

- A new SQLite database upgraded through `20260801_0001` and `20260801_0002`;
  `alembic check` reported no new operations.
- `20260801_0002` downgraded to `20260801_0001`, re-upgraded and the full chain
  downgraded to base successfully.
- PostgreSQL offline rendering remained 332 SQL lines.

Final Phase 3 production build:

```bash
MBE_FRONTEND_DATA_MODE=auto MBE_CACHE_TTL_HOURS=144 \
  MBE_THROTTLE_SECS=0 uv run python scripts/build_site.py
```

Result:

- Screened/analyzed 250/250; failed 0.
- Company news for 19/25 picks; 90 policy items from 20/20 queried sectors.
- Ranking reports 25; canonical search master 250; static screener rows 250.
- Field registry 28 fields; all 250 rows have comparable prior rank/score values.
- Build ID `e03f5369-1b90-4a89-86a0-6f0086b2a2f0`; generated at
  `2026-08-01T05:57:08.434171+00:00`.
- Uncompressed/gzip bytes: screener page 29,379/6,774; route JS
  38,142/10,053; shared CSS 27,723/6,001; screener data 283,215/30,258;
  field manifest 30,418/3,414. Source budgets passed.

The required in-app browser workflow was retried against the local route, but
browser discovery again returned no available browser types. No screenshots or
manual real-engine accessibility claims were made. Desktop/tablet/mobile,
light/dark, zoom, focus, contrast and screen-reader checks remain a deployment
gate; deterministic jsdom coverage is not a substitute.

## Phase 4 implementation details

Full lineage inventory, schema, metric dictionary, formulas, policies, coverage,
commands and API contracts are in
[`financial-architecture.md`](financial-architecture.md).

### Canonical warehouse and import

- Added typed annual/quarter/YTD/TTM/instant periods, consolidated/standalone/
  unknown basis and explicit quality states.
- Centralized 20 metric definitions at version `2026-08-01.1`.
- Added decimal normalization for rupees, thousands, lakhs, millions and crores;
  zero and negative values remain real values, never missing sentinels.
- Added compatible YTD-quarter residual and strict four-sequential-quarter TTM
  derivation with source lineage.
- Added idempotent typed filing import, dry-run rollback, unknown field/unit
  reporting, revision collision rejection and linked non-destructive restatements.
- Provider precedence is official exchange/company/regulator first and Yahoo
  compatibility second. Conflicts are reported rather than blended.

Migration `20260801_0003` adds financial dataset builds, filings, facts, metric
snapshots and quality issues. Core facts are relational `NUMERIC`, not primary
JSON documents. Indexes support filing/fact history and build/metric/value
screener reads.

### Coverage, public fields and compatibility

Current cached 250-universe coverage:

- Yahoo compatibility financial histories: 250/250.
- Cached official NSE histories: 86/250; old cache shape lacks full filing/basis
  identity, so it was not relabelled as canonical official lineage.
- Revenue CAGR (3y): 246/250, 98.4%, range -90.1% to 232.4%.
- ROCE (3y average): 232/250, 92.8%, range -55.0% to 54.7%.

Only those two metrics are public, both `Ready-with-caveat`: current static rows
explicitly say source `yahoo_compatibility`, statement basis unknown and filing
date unavailable. Operating/net/FCF margins, debt/equity, interest coverage,
profit growth, cash-flow and valuation filters remain deferred because their
taxonomy, denominator, sector or timestamp behavior is not yet reliable enough.

The screener registry is `2026-08-01.2` with 30 fields. Static and dynamic modes
use the same metric IDs, formulas, null behavior and dataset lineage. Added the
transparent editable `Revenue Growth & Returns` preset (Revenue CAGR >=10%,
ROCE >=15%). All Phase 3 field IDs and URL state remain compatible.

The public static build projects the new metrics with the unchanged score-input
calculator: 0/246 Revenue-CAGR mismatches and 0/232 ROCE mismatches. Model
weights, score output and historical builds were not changed.

### APIs and company summary

Added:

- `GET /api/v1/financials/metrics`
- `GET /api/v1/financials/coverage`
- `GET /api/v1/instruments/{instrument_id}/financials`
- Static coverage plus 25 published-company financial summary JSON files.

Metric selection is allowlisted/capped at 20 and periods at 12. Report pages now
show a semantic latest annual table, accepted derived metrics, source/basis/
cutoff/quality context, warnings, methodology link and research disclaimer.

### Phase 4 changed files

Source/migration: `src/mbe/financials/`, `src/mbe/db/models.py`,
`src/mbe/data/provider.py`, `src/mbe/screener/`, `src/mbe/api/`,
`src/mbe/publish.py`, `src/mbe/cli.py`, and migration `20260801_0003`.

Frontend/static: `src/mbe/frontend/templates/report.html`, methodology anchor,
shared CSS, generated screener/field/coverage/report assets and 25 static
financial summary contracts.

Tests/docs: `tests/test_financials.py`, API/screener/publisher updates,
`docs/financial-architecture.md`, platform/screener/environment/audit/README and
this handover.

No dependency or environment variable was added. No PostgreSQL service was
provisioned. No commit, push or deployment was performed.

### Phase 4 verification record

- `uv run pytest`: 400 passed in 7.35 seconds; one existing Starlette/httpx
  deprecation warning.
- `npm run check`: ESLint, TypeScript `checkJs`, and 21/21 Node tests passed.
- Python compileall passed.
- Fresh SQLite upgrade through `20260801_0003`, `alembic check`, Phase 4
  downgrade/re-upgrade and full downgrade to base passed.
- PostgreSQL offline migration rendering passed at 476 SQL lines.
- Representative financial screen uses the indexed financial build/metric/value
  and instrument/metric/period projections; no client SQL or raw formula exists.
- Production build analyzed 250/250 with 0 failures. Model build
  `8da41e8a-333d-45d8-818a-b8d4c124c404`; financial build
  `34baaa1c-e2f6-508b-b2f0-389669739b2a`.
- Screener is 303,707 bytes / 36,872 gzip; fields 36,615 / 4,151; financial
  coverage 1,376 / 608; shared CSS 28,575 / 6,112; KFINTECH report 52,131 /
  14,783.
- Browser runtime initialization and required troubleshooting succeeded, but
  browser discovery returned `[]`. No screenshots or manual real-engine
  accessibility claims were made.

## Phase 5 implementation details

Full source/access policy, supported-format matrix, cache/parser security,
identity/revision rules, tolerances, selection tiers, commands, APIs, rollback
and legal gate are in
[`official-nse-ingestion.md`](official-nse-ingestion.md). Measured provider and
score-input results are in
[`financial-reconciliation-2026-08-01.md`](financial-reconciliation-2026-08-01.md).

### Official discovery and safe document boundary

- Added typed NSE corporate financial-result discovery retaining announcement
  sequence ID, symbol/name/ISIN, broadcast/filing timestamps, exact period,
  audited/cumulative/basis/revision hints, attachment metadata, raw-row hash,
  raw-response hash and canonical economic identity hash.
- Live ingestion is disabled by default and requires
  `MBE_NSE_INGESTION_ENABLED=true` after current NSE terms/data-use review.
- Requests are HTTPS-host-allowlisted, synchronous/per-host concurrency one,
  0.75-second interval by default, capped at 100 per run, limited to two
  retryable exponential-backoff retries and three redirects, and never use
  rotating/evasive headers or browser automation.
- Safe fetching enforces connection/read budgets, 12 MB default bytes,
  declared-length/partial-read checks, MIME/signature validation, sanitized
  filenames, SHA-256, atomic private cache writes, validator-aware refresh and
  exact checksum invalidation. Cache paths/content never enter public output.
- Parser registry marks NSE discovery JSON metadata-only; NSE Ind-AS result
  XBRL is the only fully supported fact format. CSV, XLS/XLSX, legacy HTML,
  text/image PDF, ZIP and other inputs are explicit unsupported/quarantine
  states. No macro/formula/external-link/archive/OCR path executes.

### Parser, identity, revision and canonical import

- XBRL template `nse-ind-as-results-xbrl` v1 uses safe XML, FourD/OneI
  contexts, explicit reporting dates, INR unit refs and independent metadata/
  document basis evidence. Conflicting basis rejects rather than guesses.
- Central aliases map source labels into the Phase 4 metric dictionary. EBIT,
  EBITDA, total debt, shares and FCF proxies preserve their exact source inputs
  and derived state. Unknown units are retained as rejected quality issues.
- Exact reruns are idempotent; changed URLs with the same checksum reuse the
  canonical filing. Separate attachments and standalone/consolidated filings
  stay distinct. Only explicit revised/corrigendum evidence creates a revision
  relationship and supersedes the predecessor.
- Cutoff-aware `latest_known` and `as_filed` views prevent later revisions from
  changing historical model-build views. Source/attachment status acts as a
  safe resumable checkpoint; unsupported/quarantined rows remain reviewable.

### Migration, reconciliation and public selection

- Additive migration `20260801_0004` adds `official_filing_sources`,
  `official_filing_attachments`, `financial_filing_relationships`,
  `financial_reconciliations` and `financial_source_selections`.
- Reconciliation version `2026-08-01.1` records exact, rounding, material,
  period, basis, unit, official-only, compatibility-only, both-missing and
  unresolved states with safe near-zero percentage behavior.
- Selection version `2026-08-01.1` prefers valid official values with resolved
  period/unit/basis, permits compatibility fallback only for Revenue CAGR/ROCE,
  and otherwise returns missing. Conflicts stay visible and formulas never
  blend sources.
- Official Revenue CAGR requires positive annual endpoints exactly three years
  apart; official ROCE requires at least two compatible annual EBIT/equity/debt
  periods and positive capital. Consolidated is preferred, standalone labelled.
- Screener registry is `2026-08-01.3`; the two existing fields add preferred/
  fallback source, Tier A/B/C and reconciliation metadata. No new financial
  filter, metric formula, score input or model weight was introduced.

### Coverage, fixture and score compatibility

- The implemented adapter completed one bounded live KFINTECH metadata request
  and one linked official XBRL request on 2026-08-01: two requests, 77,853
  bytes, 16 parsed live facts and consolidated basis. No bulk/universe crawl ran.
- Captured fixture: one FY2024 consolidated audited filing, one 2,696-byte XBRL
  excerpt and 15 accepted facts. Full source document SHA-256 is recorded.
- Current static official multi-year public-metric coverage: 0/250. The old 86
  `nse_fin_*.json` histories remain non-canonical because basis/attachment/
  revision identity was lost; they were not relabelled.
- Tier B fallback coverage remains Revenue CAGR 246/250 (98.4%) and ROCE
  232/250 (92.8%). Reconciliation correctly reports compatibility-only/both-
  missing rather than inventing official comparison rates.
- Unchanged score projector still has 0/246 Revenue-CAGR differences and 0/232
  ROCE differences. With zero eligible official replacements in the static
  build, hypothetical ranking impact is not yet computable and no build changed.
- Operating margin, debt/equity and interest coverage remain deferred.

### APIs, reports and operations

Added bounded safe read routes:

- `GET /api/v1/instruments/{instrument_id}/filings`
- `GET /api/v1/filings/{filing_id}`
- `GET /api/v1/instruments/{instrument_id}/financials/reconciliation`
- extended `GET /api/v1/financials/coverage`

Added explicit commands:

- `mbe nse-filings-discover`
- `mbe nse-financials-ingest` with fixture, metadata-only, dry-run, cache,
  force-refetch, date/symbol/period/document/byte bounds
- `mbe financials-reconcile`
- `mbe financials-unsupported`
- `mbe financials-conflicts`
- `mbe financials-cache-invalidate`

Reports now distinguish “Official NSE filing” from “Compatibility-provider
fallback” and include a keyboard-native source-lineage disclosure with source
tier, basis, filing/revision state, reconciliation, build and safe official
link. Current generated reports correctly show fallback/unknown-basis state.

### Phase 5 changed files and configuration

Primary new modules: `official_domain.py`, `document_fetch.py`,
`nse_official.py`, `parsers.py`, `official_importer.py`,
`official_repository.py`, `official_metrics.py` and `reconciliation.py` under
`src/mbe/financials/`; migration `20260801_0004`; official fixture and
`tests/test_official_financials.py`; official ingestion/reconciliation docs.

Updated models/importer/quality/repository/provider/CLI/API/projection/screener/
publisher/template/CSS/tests, README, environment/platform/financial/screener/
audit docs and generated static output. No dependency or secret was added.

New safe configuration variables: `MBE_NSE_INGESTION_ENABLED`,
`MBE_NSE_REQUEST_INTERVAL_SECONDS`, `MBE_NSE_FILING_CACHE_DIR`,
`MBE_NSE_MAX_DOCUMENT_BYTES`, `MBE_NSE_MAX_REQUESTS_PER_RUN` and
`MBE_NSE_USER_AGENT`. Live ingestion defaults disabled; static builds do not
read them to refresh data.

### Phase 5 verification record

- `uv run pytest`: 421 passed in 7.43 seconds; one existing Starlette/httpx
  deprecation warning.
- `npm run check`: ESLint passed, TypeScript `checkJs` passed, 21/21 Node tests
  passed.
- Python compileall passed.
- Fresh SQLite upgrade through `20260801_0004`, `alembic check`, Phase 5
  downgrade/re-upgrade and full downgrade to base passed.
- PostgreSQL offline migration rendering passed at 638 SQL lines.
- SQLite plans used indexes for official filing history, attachment checksum,
  reconciliation status, selected-source lookup and accepted financial facts.
- Production build analyzed 250/250 with 0 failures; company news 19/25 and 90
  policy items across 20/20 sectors. Model build
  `3cab5859-b445-4fb8-8dd8-3bf9650fb792`; deterministic financial build
  `34baaa1c-e2f6-508b-b2f0-389669739b2a`; generated
  `2026-08-01T07:15:47.377680+00:00`.
- Bytes uncompressed/gzip: screener page 29,379/6,775; CSS 29,386/6,230;
  screener data 303,708/36,870; field manifest 40,990/4,347; financial coverage
  3,391/1,032; KFINTECH report 53,093/15,090.
- 35 JSON files and 28 generated pages validated; IDs, landmarks, skip links,
  external rel, local references, CSP/no `unsafe-eval`, no local paths/cache/
  raw metadata/database variable in public output, source/generated asset
  equality and six-route HTTP smoke all passed. `git diff --check` passed.
- Browser runtime/troubleshooting was followed, but browser discovery returned
  `[]`. No screenshot or manual real-engine accessibility claim was made.

## Phase 6 implementation details

Full selection, gate, acquisition policy, corpus format, taxonomy/context/unit
rules, evidence/review workflow, security, commands and rollback are in
[`phase6-official-corpus-pilot.md`](phase6-official-corpus-pilot.md). Exact
sample results and limitations are in
[`phase6-parser-accuracy-report.md`](phase6-parser-accuracy-report.md),
[`phase6-coverage-conflict-report.md`](phase6-coverage-conflict-report.md) and
[`phase6-readiness-recommendation.md`](phase6-readiness-recommendation.md).

### Gate, pilot and acquisition bounds

- Added manifest `nse-official-pilot-2026-08-v1`, version `2026-08-01.1`,
  scope hash `a083848a6a51d6d18a34251d94f46730356b9207f881b7cb963823d0d250e2b5`.
- Selected 12 published companies across at least nine industries: BLS,
  HBLENGINE, NATCOPHARM, SARDAEN, FORCEMOT, WELCORP, CAMS, KFINTECH, NETWEB,
  LTFOODS, CEMPRO and NIVABUPA. CAMS/KFINTECH/NIVABUPA are segregated
  financial-services cases and cannot dilute general-company acceptance rates.
- Restricted dates to 2022-04-01 through 2026-03-31, annual results only, four
  filings/company, two attachments/filing, 48 documents, 60 requests, 12 MB/
  document, 120 MB total, concurrency one, 0.75-second interval, two retries,
  30-minute runtime, 25% quarantine stop and five identity anomalies.
- Live commands now require the global kill switch, exact manifest scope, a
  non-expired private operator record bound to the manifest hash and its review
  ID supplied again. The record covers terms, cadence, retention,
  redistribution, attribution and responsibility but makes no legal claim.
- Fixture/offline paths remain usable without the gate. No review record was
  created and no additional live discovery or attachment request was made.
- Safe fetch now enforces total-run bytes/runtime and stops after repeated
  403/429 denial in addition to Phase 5 safeguards.

### Corpus, taxonomy, evidence and review

- Added an immutable captured-corpus manifest for the existing KFINTECH FY2024
  reduced excerpt: 1 company, 1 filing, 2,696 bytes, exact excerpt/full-source
  hashes, safe relative path and explicit captured/unreviewed/redistribution
  states. Offline integrity verification passed 1/1.
- Added concept mapping registry version `2026-08-01.1` with metric, observed
  concept names, statement/period/unit/basis/sign semantics, confidence and
  public eligibility. Extension mapping always fails closed without a reviewed
  rule. Namespace-less captured evidence is `supported_excerpt`, never a full
  supported taxonomy.
- Parser evidence preserves original and Decimal-normalized value, unit ref,
  decimals, precision, scale, concept/context, mapping version, candidates and
  selection reason. Scale is applied once; nil is not a fact;
  duplicate-equivalent facts collapse; conflicting preferred duplicates block
  the metric instead of falling through to a broader alias.
- Added XML limits: 50,000 elements, depth 64, 1,000,000-character text nodes,
  10,000 contexts and 100,000 numeric facts. Defused XML/no-entity/no-remote-
  schema behavior remains.
- Added private evidence export, deterministic 13-item review queue and
  append-only, attributed, reversible decision events. Nothing under
  `data/official-pilot` enters public output.

### Ground truth, Tier A, reconciliation and publication

- Added eight independently transcribed KFINTECH expectations: revenue, PAT,
  equity, debt, finance cost, assets, CFO and capex. Results: 8/8 exact and 8/8
  period/unit/basis/mapping in this one captured reduced filing.
- Explicitly left EPS, revision, comparative context, full taxonomy diversity,
  multi-company coverage and multi-year derived metrics unmeasured. The 100%
  fixture result is not presented as universal accuracy.
- Added Tier-A policy version `2026-08-01.1` at fact level. All identity,
  checksum, parser/taxonomy, mapping, period/unit/basis, normalization,
  duplicate, supersession, quality and review requirements must pass.
- Source-selection policy is now `2026-08-01.2`: unreviewed official values
  cannot replace approved compatibility fallbacks. Eligibility and publication
  are separate states.
- Official Tier-A facts/metrics remain 0; Revenue CAGR/ROCE official derivation
  is 0/12; static official coverage remains 0/250; compatibility fallback
  remains 246/250 Revenue CAGR and 232/250 ROCE.
- The pre/post static screener hash for instrument/rank/score/Revenue CAGR/ROCE
  was identical:
  `2910f94714bb0d64941083edb3dca6410ce1b73ad18524be3e1d45c0b4a0578d`.
- Production decision is no-go because operator review, representative corpus,
  namespace/revision/comparative evidence, multi-year metrics and completed
  manual review are absent. This is an operational evidence decision, not a
  legal conclusion or parser failure.

### Phase 6 changed files and configuration

New modules/artifacts: `src/mbe/financials/pilot.py`,
`src/mbe/financials/xbrl_concepts.py`, the versioned pilot manifest, captured
corpus manifest, independent ground truth, `tests/test_official_pilot.py` and
four Phase 6 documents. Updated parser/domain/fetcher/reconciliation/CLI,
README, environment, official/financial/audit docs and this handover.

No migration or dependency was added. New safe variables are
`MBE_NSE_MAX_TOTAL_BYTES=120000000` and
`MBE_NSE_MAX_RUNTIME_SECONDS=1800`. Operator acknowledgement is deliberately
not an environment variable or committed artifact.

### Phase 6 verification record

- `uv run pytest`: 449 passed in 6.70 seconds; one existing Starlette/httpx
  deprecation warning.
- `npm run check`: ESLint passed, TypeScript `checkJs` passed and 21/21 Node
  tests passed. Python compileall passed.
- Pilot manifest validation, 1/1 corpus checksum verification, offline parser,
  review queue and evaluation commands passed without network access.
- Fresh SQLite upgrade through unchanged head `20260801_0004`, `alembic check`,
  Phase 5 downgrade/re-upgrade and full downgrade passed. PostgreSQL offline
  rendering remained 638 SQL lines. No new query plan applies because Phase 6
  added no schema/query.
- Production build analyzed 250/250 with 0 failures; news 19/25 and 90 policy
  items across 20/20 sectors. Model build
  `a19f340f-9f06-4a1c-a959-781b7239aed4`; financial build
  `34baaa1c-e2f6-508b-b2f0-389669739b2a`; generated
  `2026-08-01T07:56:09.518460+00:00`.
- Bytes uncompressed/gzip: screener page 29,379/6,774; CSS 29,386/6,230;
  screener data 303,707/36,868; field manifest 40,988/4,341; financial coverage
  3,391/1,034; KFINTECH report 53,093/15,090.
- 32 static JSON files and 28 generated pages validated; duplicate IDs,
  landmarks, external rel, local references, CSP/no `unsafe-eval`, public
  local/private-path scans and source/generated assets passed. Six HTTP routes
  returned 200 and `git diff --check` passed.
- No public UI behavior changed, so no new visual claim was made. The existing
  real browser/accessibility deployment gate remains pending.

## Phase 7 implementation details

### Canonical route, domain and page experience

- Added `/company/{instrument_id}.html` as the permanent symbol-independent
  company route. All 250 scored instruments receive HTML plus a matching
  `/api/v1/research/{instrument_id}.json` payload.
- The 25 `/reports/{ticker}.html` paths remain full compatibility renderings of
  the same model and declare the instrument-ID page as canonical. Search,
  rankings, screener and peer actions now use canonical routes. The sitemap
  lists canonical pages only.
- Added typed research schema `1.0` covering identity, failure-tolerant quote,
  current/previous score/rank, components, explanations, strengths/risks,
  history, approved financials, technical context, peers, filings, news,
  checklist, lineage, warnings and feature flags. Jinja does not consume raw
  provider or database objects.
- Delivered the company hero, deterministic research summary, why-ranked
  evidence, separate strengths/risks, labelled SVG plus exact history table,
  financial/source disclosures, technical trend, peer table, filing state,
  entity-matched news, local checklist, trust panel and disclaimer.

### Deterministic research services

- Explanation policy `2026-08-01.1` uses stable codes and compatible universe
  medians for score, Revenue CAGR and ROCE; explicit thresholds for confidence
  and risk; persisted technical/rank movement; and source/missing-data warnings.
  Each item includes fields, values, source, period, methodology and version.
- Strengths are positive classifications; risks are warning/risk
  classifications. Missing values cannot create positive prose and no LLM or
  recommendation language is used.
- Peer policy `2026-08-01.1` requires same industry or sector, then ranks by
  industry precedence, market-cap match when known, score proximity, compatible
  Revenue CAGR/ROCE proximity, rank and canonical ID. It returns six by default,
  maximum eight, never self or unrelated score-only matches, and exposes every
  selection reason.
- Score history uses existing indexed build/snapshot rows, collapses duplicate
  builds, sorts UTC, stabilizes component order and caps at 26 (API maximum 52).
  One point explicitly does not imply continuity.

### Data sources, parity and safety

- Public financial scope remains Revenue CAGR three-year and ROCE three-year
  average plus existing normalized recent facts. Yahoo is labelled Tier-B
  compatibility fallback with unknown-basis warnings. Official Tier-A remains
  unavailable/0 of 250; no official badge or new metric was introduced.
- Static filing timelines correctly show unavailable because no public-safe
  official corpus exists. Dynamic metadata is bounded to 20, newest first, and
  official links pass the NSE HTTPS host allowlist. Private evidence, raw XBRL,
  cache paths and operator records never enter the contract.
- News is capped at 12 and requires high/medium confidence, relevance at least
  55 and safe HTTPS. The published 25 retain entity-matched news; other pages
  show an explicit unavailable state. Low-confidence matches remain hidden.
- Static/SQLite dynamic tests prove parity for identity, current ranking,
  explanation codes, accepted financial values/source, technical state, peers
  and history; Decimal storage tolerance is `1e-11`. Only live quote/market
  state and post-cutoff news may differ at runtime.
- Added material-age/policy mismatch warnings, strict public URL handling,
  private-marker validation, bounded local-storage keys, eight-ID comparison
  storage and a nine-item per-company resettable local checklist.

### APIs, operations, files and configuration

New dynamic endpoints:

- `GET /api/v1/instruments/{instrument_id}/research`
- `GET /api/v1/instruments/{instrument_id}/score-history`
- `GET /api/v1/instruments/{instrument_id}/peers`

New offline commands: `company-research-validate`,
`company-research-inspect`, `company-research-build` (optional one-company and
derived-policy rebuild), `company-research-legacy-validate`,
`company-research-measure` and `company-research-parity`.

New modules/assets: `src/mbe/research/`, company Jinja template,
`research.js`, `tests/test_research.py`, `tests/frontend/research.test.js` and
`docs/company-research-architecture.md`. Publisher, API/repository/financial
projection reads, CLI, shared CSS/JS, build script, tests, README and architecture
documents were updated. Generated `site/company/`, research JSON, all 25 legacy
pages, ranking/screener/instrument destinations and `sitemap.xml` changed.

No migration, dependency or environment variable was added. The database
already has suitable score-history, build/score, financial-metric and filing
indexes. No PostgreSQL was provisioned. The Phase 6 NSE operator gate and no-go
are unchanged; Phase 7 made zero live NSE requests.

### Phase 7 verification record

- `uv run pytest`: 456 passed; one existing Starlette/httpx deprecation
  warning. `npm run check`: ESLint and TypeScript `checkJs` passed; 24/24 Node
  tests passed. Python compileall and `git diff --check` passed.
- Cached offline-compatible production build analyzed 250/250 with zero
  failures; news remained 19/25 and policy 90 items across 20/20 sectors.
- Generated/validated 250 canonical company pages, 250 research JSON payloads
  and 25 legacy pages. Final totals: 6,242,441 HTML bytes and 5,908,860 JSON
  bytes; averages 24,969.76 and 23,635.44; maxima 30,096 and 28,393 bytes.
- Shared source assets: CSS 36,829 bytes, application JS 51,580 bytes and
  research JS 4,847 bytes, within existing budgets. No chart library was added.
- Final static build: model `c5b3efd0-dcff-4bb1-bb5d-afda723bcaca`, financial
  `34baaa1c-e2f6-508b-b2f0-389669739b2a`, generated
  `2026-08-01T08:47:55.778115+00:00`; Revenue CAGR coverage 246/250 and ROCE
  coverage 232/250, unchanged from Phase 6.
- Fresh SQLite migration round trip, unchanged head `20260801_0004`, Alembic
  check and PostgreSQL offline rendering passed. Existing score-history and
  financial indexes were used by representative SQLite query plans; no new
  migration was justified.
- JSON/schema/HTML/landmark/duplicate-ID/external-rel/local-reference/canonical/
  sitemap/CSP/private-path/public-value/source-asset/HTTP checks passed. Real
  browser visual, contrast, keyboard, screen-reader and 200% zoom checks remain
  pending; jsdom coverage is not claimed as visual proof.

## Phase 8 implementation details

Phase 8 is bounded release hardening. It changes no score, model weight,
provider choice, financial acceptance, official-ingestion gate, database schema
or public product scope.

- Added Playwright 1.62.1 system-Chrome journeys, axe-core 4.12.1 scans,
  responsive/zoom/reduced-motion checks, performance observers and 11 committed
  visual baselines. Lighthouse 13.4.1 artifacts remain ignored local evidence.
- Fixed defects found by the audit: missing mobile search name, three contrast
  failures, prohibited chip ARIA, non-focusable scroll regions, undersized sort
  targets and legacy routes missing `noindex`.
- Moved the pre-paint theme code into a same-origin external asset so CSP can
  remove inline script. Added a code-native SVG favicon, generated `404.html`,
  `robots.txt`, HSTS/COOP/cross-domain headers and bounded asset/static-JSON
  cache policy. Inline style remains allowed for current generated presentation
  attributes; `unsafe-eval` and inline executable script are prohibited.
- Added `scripts/verify_release.py`, the Phase 8 public-value hash fixture, a
  pytest release contract and SEO/security/dependency/performance/deployment/
  rollback documentation. The verifier currently proves 279 HTML, 507 JSON,
  250 company, 25 legacy, 253 unique indexable/sitemap routes and unchanged
  public score/financial hashes.
- Exact development-only Node dependencies were added for Playwright, axe and
  Lighthouse. No production bundle/runtime dependency or environment variable
  was added. No Alembic migration was needed.

### Phase 8 verification record

- Real Google Chrome 150.0.7871.187 ran the 65-test browser suite. The final
  matrix includes 17 axe audits, 11 visual baselines, 23 responsive/reflow
  checks, 9 release journeys and 5 performance/bundle checks.
- Lighthouse mobile-lab scores: rankings 94/100/96/100, screener
  89/100/100/100, company 100/100/96/100 and methodology 100/100/100/100 for
  performance/accessibility/best-practices/SEO. Rankings/screener synthetic LCP
  are 2.97s/3.76s; zero or near-zero CLS/TBT. Local quote 404s explain the 96
  best-practices scores and are a preview verification item.
- `npm audit` and `pip-audit` reported zero known vulnerabilities; `npm ls`
  resolved. The final build analyzed 250/250 with zero failures and made no live
  official NSE request.
- Final static build: model `577191f1-a9c2-4202-8ed2-85e13090e095`, financial
  `34baaa1c-e2f6-508b-b2f0-389669739b2a`, generated
  `2026-08-01T09:34:57.391942+00:00`; compatibility Revenue CAGR/ROCE coverage
  remains 246/250 and 232/250 and official coverage remains 0/250.
- In-app browser initialization returned no available browser. Standard
  Firefox/WebKit engine acquisition stalled and was stopped. A macOS
  accessibility-tree read was attempted but did not return in a bounded wait.
  Firefox/WebKit journeys and VoiceOver speech/navigation are explicitly not
  claimed and remain preview promotion conditions.
- Release decision: ready with conditions for an explicitly authorized preview;
  not approved for production. No preview/deploy/commit/push occurred.

## Phase 9 implementation and verification record

Phase 9 created an auditable release candidate without changing product scope.
The candidate-file review excluded ignored runtime databases/caches, browser
artifacts and private operator records. Staged scans found no credential-shaped
secret, sensitive filename or ignored file. Two intentional visual-baseline
PNGs were the only candidate files larger than 1 MiB.

- Created branch `release/v1.0.0-rc1` from `main` at `dcaf069`.
- Committed 953 files as `6797a2eadf9d4fed6bbfbce6f02c9a5c7b22d89b`
  with message `release: prepare Multibagger Engine v1.0.0-rc1` and created
  annotated tag `v1.0.0-rc1`.
- Existing Vercel Git integration created RC1 deployment
  `7K7NSKs89gv9bGHNWzdMyfPeCmVt`. The exact protected alias remains omitted
  from public documentation.
- Authenticated Safari access later reached the actual application. RC1 quote
  requests failed because Vercel functions could not import `mbe`; runtime logs
  showed `ModuleNotFoundError: No module named 'mbe'`.
- Added explicit `src` bootstraps to `api/quotes.py` and `api/v1.py`, plus
  subprocess entrypoint regression tests. Commit
  `786e61d803f5c0e0cb15121a4eb7120626934823`, tag `v1.0.0-rc2` and deployment
  `9ZYwbgXU7kt9SoaSMP2cZWYgWTdN` restored quotes.
- RC2 then exposed `ModuleNotFoundError: No module named 'fastapi'` on
  `/api/v1/health`. Added FastAPI to the Vercel root requirements and a
  packaging regression assertion. Commit
  `9de46429119ae918b5b221fa4787fe400ed1446f`, tag `v1.0.0-rc3` and deployment
  `7iyyZhWCQDYg4XepdSx8W1ywedum` restored the typed routes.
- The remote release branch and peeled `v1.0.0-rc3` tag resolve to RC3. No
  force push or history rewrite occurred. GitHub CLI and a callable in-app
  browser engine remain unavailable, so no pull request was created.

RC3 authenticated Safari validation passed the root/rankings with live quotes,
methodology, screener and its High Score/Moderate Risk preset, KFINTECH complete
company, CANHLIFE missing-data company, KFINTECH legacy report, product 404,
instrument/research JSON, degraded health, intended database-unavailable status
and missing/invalid ticker analysis contracts. The KFINTECH page showed the
same 22.5% Revenue CAGR, 27.4% ROCE and Tier-B source disclosure; CANHLIFE kept
missing Revenue CAGR/ROCE unavailable without zero imputation.

Authenticated Vercel evidence records RC3 Ready in 1m 28s. Its 39-line deploy
log uses Python 3.12 and uv 0.10.11, installs dependencies, compiles bytecode and
completes `/vercel/output` in 29 seconds. Deployment-filtered runtime logs show
zero Warning/Error/Fatal console events, quote 200, health 200, intended status
503 with request ID, and intended analysis 400 responses.

Local pre-commit RC1 results remain 457 Python, 24 frontend, 65 Chrome and 11
visual tests. After both fixes, 461 Python and 24 frontend tests, ESLint,
JavaScript type checking, compileall, `git diff --check` and the release verifier
pass. The RC3 verifier reconfirmed 279 HTML, 507 JSON, 250 companies, 25 legacy
routes, 253 indexable/sitemap routes and both public hashes. Fixes did not change
generated site/scoring/provider/NSE content. The cached build remains 250/250
with zero failures; model build
`1bd53d15-67c6-4b02-b830-0eb0bb1d582b`, financial build
`34baaa1c-e2f6-508b-b2f0-389669739b2a`, generated
`2026-08-01T11:10:03.765519+00:00`. Public score/financial hashes remain
`12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19` and
`3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`;
official coverage remains 0/250, fallback coverage remains 246/250 Revenue CAGR
and 232/250 ROCE, Phase 6 remains `live_enabled: false`, and Phase 9/9B made zero
live NSE requests.

The documentation-only RC4 commit
`6fb5a7ea26c2ce996e17e298aae4c41c0965605d` and annotated tag `v1.0.0-rc4`
were pushed. RC4 preview `1nxtgBJQxq5Ty5VBbBH6MJMU7pxp` reached Ready in
1m 27s, rendered model build `1bd53d15`, returned the expected degraded health
200 contract and had clean runtime logs.

After the unresolved hosted cross-browser, real VoiceOver, axe/Lighthouse and
exhaustive hosted-integrity conditions were disclosed, the user explicitly
authorized production. Vercel's promotion flow stated that it would build a new
deployment with the Production environment; it therefore produced deployment
`EvCEEd2g9fkRVShmvAdwQeCdoZja` in 1m 26s rather than assigning the RC4 preview
artifact directly. The production domain is
`https://multibagger-engine.vercel.app/`.

Production Safari and HTTP smoke passed root/rankings, screener, methodology,
canonical and legacy company routes, static JSON, live quotes, health 200,
intended database-unavailable status 503 and product 404. Actual application
CSP/HSTS/referrer/permissions/frame/nosniff headers, gzip and HTML/CSS/static
JSON/dynamic cache policies passed. Representative SHA-256 parity was exact for
root HTML, CSS, instruments JSON, KFINTECH research JSON and canonical/legacy
company HTML. Production runtime logs showed the expected quote 200, health
200 and status 503 traffic with zero warning/error/fatal events. The prior
deployment `rBeoLhBW8hNZv5fX3iT64nwrvCsc` was separately rechecked and remains
Ready for rollback.

Decision: production live by explicit risk acceptance. Hosted Chromium,
Firefox and WebKit/mobile automation, real VoiceOver, hosted axe/Lighthouse and
exhaustive hosted hashing remain post-release closure conditions and are not
claimed as passes. Full evidence is in `phase9-preview-release-report.md`.

## Phase 10A implementation details

### Root cause

Search had quietly narrowed to the 250-company Nifty Smallcap research/
ranking universe. `staticSearch()`/the dialog read `instruments.json`, and
that snapshot's own contract warning said so explicitly: "Static instrument
master is limited to the pinned Nifty Smallcap 250 universe." No canonical
instrument outside that pinned master had ever been imported anywhere in the
system, so a user could not find Reliance, TCS, Infosys, HDFC Bank, Dixon,
Polycab, HAL, BEL, Zomato, Trent or any other major Indian company that
happened not to be a current Smallcap-250 constituent. The resolver logic
itself (`InstrumentResolver`, `staticSearch()`) was never the problem — both
already scan whatever identity data they are given; the ranking universe had
simply become the only identity data that existed.

### The three-universe separation

Introduced as three explicitly separate concepts (previously conflated —
see "Search, research and ranking universes" in the architecture snapshot
above for the full definitions): search universe (everything identifiable —
now ~2,950 NSE main-board/SME securities), research universe (companies with
a deterministic page — 250, unchanged) and ranking universe (companies
currently scored — 250, unchanged, conceptually independent of the research
universe even though identical today). Full design, the merge/ranking
algorithm, the static/dynamic/serverless data flow and known limitations are
in [`search-architecture.md`](search-architecture.md).

### Files changed

New: `src/mbe/data/nse_search_master.py` (official NSE main-board/SME CSV
provider), `src/mbe/search/{domain,catalog,ranking}.py`, `src/mbe/research/
lightweight.py`, `src/mbe/frontend/templates/company_lightweight.html`,
`api/company.py` (serverless canonical-page fallback), `scripts/
refresh_search_universe.py`, `universes/nse-search-universe.json` (pinned
snapshot).

Changed (all additive): `src/mbe/publish.py` (emits `search-index.json`;
adds `render_lightweight_company_page`), `src/mbe/api/app.py` and `src/mbe/
api/schemas.py` (`GET /api/v1/search`, `GET /api/v1/company/{id}/summary`),
`src/mbe/cli.py` (`search-universe-import`), `src/mbe/data/market.py`
(`week52_high`/`week52_low` on `NormalizedQuote`), `api/quotes.py`
(whitelist unions the search universe; 52-week range passthrough),
`src/mbe/frontend/assets/app.js` (search reads `search-index.json`/
`/api/v1/search`; honest research/ranking badges; truthful copy),
`src/mbe/frontend/templates/{base,index}.html` (truthful search/homepage
copy), `vercel.json` (new `api/company.py` function and one rewrite),
`scripts/verify_release.py` (expected JSON count 507 → 508).

Untouched: canonical ID derivation, the scoring/ranking engine, financial
lineage, provider selection/registry, every existing migration, every
existing route's contract (`instruments.json`, `/api/v1/instruments/lookup`,
`/api/v1/instruments/{id}/research`, all 250 static company pages and 25
legacy report pages).

### New APIs

- `GET /api/v1/search?q=&limit=` — search-universe results with honest
  `result_type`/`research_available`/rank/score; preserves
  `InstrumentResolver`'s entity-disambiguation tiering exactly.
- `GET /api/v1/company/{instrument_id}/summary` — always 200 for any known
  instrument; never fabricates rank/score for a non-research company.
- Static: `GET /api/v1/search-index.json`.
- Serverless: `GET /company/{instrument_id}.html` now resolves for every
  search-universe company (previously 404/only 250+25), via `api/company.py`
  when no static file exists.

### Performance

No provider lookups happen on search keystrokes: both the static path
(`search-index.json`, fetched once and searched in memory, mirroring the
existing `instruments.json` pattern) and the dynamic path (`InstrumentResolver`
SQL scan, existing debounce) are unchanged in kind, just over a larger fixed
snapshot (~2,950 rows vs. 250) — well within the "5,000+" design target in the
product spec. `api/company.py` fetches a quote only on an actual page load of
a non-research company, never per keystroke. The release verifier's
`largest_company_html_bytes`/`app_js_bytes`/`app_css_bytes` budgets are
unchanged.

### Test results

545 Python tests (461 → 545, +84) and 25 frontend tests (24 → 25, +1) passed.
ESLint, TypeScript type-check, `python -m compileall`, `git diff --check` and
the offline static release verifier (`scripts/verify_release.py`) passed —
279 HTML, 508 JSON (the one new additive `search-index.json`), 250 company,
25 legacy, 253 indexable/sitemap, and both public value hashes
(`12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19` scores,
`3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`
financials) byte-identical to the Phase 9 release — confirming no scoring or
financial-value change. New regression coverage: `tests/
test_phase10a_regression.py` (the full Definition-of-Done company list —
Reliance, TCS, Infosys, HDFC Bank, HAL, BEL, Dixon, Polycab, BLS/ACE/VIJAYA
collisions, unknown company, research/non-research company, quote-
unavailable, research-unavailable — against the real pinned search-universe
snapshot), plus `test_search_universe.py`, `test_search_catalog.py`,
`test_search_ranking.py`, `test_search_static_build.py`,
`test_publish_lightweight.py`, `test_research_lightweight.py`,
`test_company_fn.py`, `test_api_v1_search.py` and
`test_search_universe_cli.py`. No real browser available in this
environment; hosted cross-browser verification remains a Phase 10 (post-
release monitoring) condition as before.

### Remaining limitations

See "Known limitations" in `search-architecture.md`: group-company name
collisions (e.g. the Reliance family) are resolved deterministically rather
than by market cap/volume (unavailable for unmodeled companies); no sector/
industry/business-description exists for search-universe-only companies
(no scraping was introduced); `api/company.py` resolves identity from the
static snapshot, so a company newly listed since the last weekly build will
not resolve until the next scheduled build; BSE-only listings are not yet
covered (NSE main board + SME only, matching the spec's "at minimum" scope).

### Recommended Phase 10B work

1. Provision PostgreSQL and run `search-universe-import` so the dynamic
   `/api/v1/search`/`/api/v1/company/{id}/summary` routes serve the full
   universe in database-backed mode, not only the static path.
2. Add a BSE listed-security source alongside NSE, following the same
   fail-closed provider pattern.
3. Weekly-build-time freshness metadata for `search-index.json` (a
   `retrieved_at`/staleness banner on lightweight pages, similar to the
   research-page freshness disclosures).
4. A prominence signal (e.g. index membership breadth, once a wider index
   universe than Smallcap 250 is imported) to resolve group-company search
   ties by more than lexical remainder length.
5. Complete the deferred Phase 10 (pre-existing) post-release monitoring and
   accepted-condition closure work below — hosted cross-browser/VoiceOver/
   axe/Lighthouse verification now additionally needs to cover the new
   search dialog badges and at least one lightweight company page journey.

## Phase 10B implementation details

### Root architectural decisions

1. **BSE cross-listing needed no migration.** `InstrumentListingRow` already
   had `exchange_code`/`bse_code`/`isin`/`is_primary`/`status` columns
   (Phase 0), and `stable_instrument_id()` already keys on ISIN alone when
   present, so a BSE row sharing an NSE instrument's ISIN was already
   guaranteed to compute the same canonical ID. The only real gap —
   `import_instruments()` had no branch for "instrument exists, no listing
   on this exchange yet" — was closed additively (`ImportSummary.
   cross_listings_added`), reusing the existing schema exactly as
   instructed.
2. **BSE source honesty over fabricated coverage.** Every official BSE
   endpoint reachable from this environment (`api.bseindia.com`,
   `www.bseindia.com` downloads) returned a bot-protection error page or
   the site's client-side app shell instead of data — verified during this
   phase, not assumed. Rather than fabricate thousands of BSE records or
   scrape a third-party aggregator (explicitly prohibited), the pinned
   `universes/bse-search-universe.json` is a small, explicitly-labeled
   curated starter fixture (`coverage_status:
   "curated_starter_fixture_pending_live_verification"`) of 20 long-stable
   large-cap scrip codes, each cross-checked against the real, live-fetched
   NSE ISINs from Phase 10A. `BseListedSecurityProvider` is fully
   fetch-capable and will use a live official feed automatically the moment
   one is reachable (`scripts/refresh_bse_search_universe.py` tries live
   first, falls back to curated only on `ProviderError`).
3. **Ranking v2 stays a pure function over the same merged index**, not a
   new service or database dependency — versioned via a single
   `SEARCH_RANKING_POLICY_VERSION` constant surfaced in both
   `search-index.json`'s meta and the new `/api/v1/search/meta` route.
4. **No corporate-group/parent-subsidiary field was added.** The phase spec
   explicitly prohibits inferring one from company names alone, and no
   authoritative ownership source exists in this repository. Group-query
   relevance (multiple results, correct exact-match ordering) is achieved
   through ranking tiers/tie-breakers instead, matching the required
   behavior without the prohibited inference.

See `docs/search-architecture.md` for the full design (BSE source honesty,
cross-listing bridge, ranking policy v2 tier table, listing-status handling,
classification reconciliation, performance measurements, evaluation harness
and known limitations) — not duplicated here.

### Phase 10B files changed

New: `src/mbe/data/bse_search_master.py`, `scripts/
refresh_bse_search_universe.py`, `universes/bse-search-universe.json`
(pinned curated fixture), `src/mbe/search/evaluation.py`.

Changed (all additive): `src/mbe/instruments/importer.py`
(`cross_listings_added` branch), `src/mbe/instruments/resolution.py`
(`ListingMatch`/`MatchCandidate.listings`), `src/mbe/search/domain.py`
(`ExchangeListing`, `SearchIndexRecord.listings`/`primary_exchange`/
`sector_source`/`industry_source`), `src/mbe/search/catalog.py`
(`bse_rows` parameter, classification backfill-without-overwrite),
`src/mbe/search/ranking.py` (versioned policy, full-phrase tier,
`parse_exchange_hint`, exchange filtering, length-ratio fuzzy guard,
active/primary/SME/research tie-breakers), `src/mbe/publish.py`
(`bse_rows` threaded through `render_site`/`_render_static_v1`, new
`search-index.json` meta fields), `src/mbe/api/app.py` and `src/mbe/api/
schemas.py` (`ListingData`, `SearchMetaData`, extended `SearchResultData`/
`CompanySummaryData`, new `/api/v1/search/meta`, extended `/api/v1/search`
params), `src/mbe/cli.py` (`bse-search-universe-import`,
`search-quality-evaluate`, `search-inspect`), `src/mbe/research/
lightweight.py` (BSE/listings/inactive-banner fields), `src/mbe/frontend/
templates/company_lightweight.html` (BSE code, listings table, inactive
banner), `src/mbe/frontend/assets/app.js` (`parseExchangeHint`, exchange
filtering, BSE/status badges, fuzzy-guard performance fix),
`scripts/verify_release.py` unchanged this phase (JSON count already 508
from Phase 10A).

Untouched: canonical ID derivation, the scoring/ranking engine, financial
lineage, provider selection/registry, every existing migration, every
existing route's contract, all 250 static company pages, all 25 legacy
report pages, `instruments.json`'s contract and warning.

### New/extended APIs

- `GET /api/v1/search/meta` (new, additive) — NSE/BSE/cross-listed/active/
  SME/research/ranked counts and `search_ranking_policy_version`.
- `GET /api/v1/search` — adds `exchange`, `active_only`, `include_sme`,
  `include_inactive` query params (all optional, default preserves Phase
  10A behavior) and `bse_code`/`primary_exchange`/`listings`/
  `sector_source`/`industry_source` response fields.
- `GET /api/v1/company/{id}/summary` — same new response fields as above.
- CLI: `bse-search-universe-import`, `search-quality-evaluate`,
  `search-inspect` — all offline, all exit nonzero on material failure.

### Phase 10B performance

Length-ratio pre-filter added to both `mbe.search.ranking._best_match` and
`app.js`'s `staticSearch()`: skip the fuzzy comparison entirely when two
strings' lengths differ by more than half the longer one (a standard
fast-reject for edit-distance-like measures). Measured on the real
2,947-record merged index: server-side `rank_search_candidates()` mean
latency 66ms → 35ms; client-side `staticSearch()` mean latency (Node/V8
benchmark) 24.5ms → 16.1ms. `search-index.json` is 2.9 MB raw / ~245 KB
gzipped. No index caching, prefix trees or WASM were introduced — the
measured numbers comfortably support the "5,000+" design target with the
existing debounce (180ms) and this simple guard, so a heavier rework was
not justified this phase.

### Search-quality evaluation result

`uv run mbe search-quality-evaluate` against the real 2,947-record merged
index (16-query evaluation set: exact symbol, BSE code, ISIN, company name,
group queries, short-alias collisions, unknown-company negative case):
**100% top-1 accuracy, 100% top-3 recall, 0 false positives.**

### Phase 10B test results

615 Python tests (545 → 615, +70) and 28 frontend tests (25 → 28, +3)
passed. ESLint, TypeScript type-check, `python -m compileall`, `git diff
--check` and the offline static release verifier passed — 279 HTML, 508
JSON, 250 company, 25 legacy, 253 indexable/sitemap, and both public value
hashes (`12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19`
scores, `3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`
financials) byte-identical to Phase 9/10A — confirming no scoring or
financial-value change. New regression coverage: `tests/
test_bse_search_universe.py`, `tests/test_search_catalog_bse.py`, `tests/
test_search_ranking_v2.py`, `tests/test_search_static_build_bse.py`, `tests/
test_api_v1_search_bse.py`, `tests/test_search_cli_phase10b.py`, `tests/
test_search_evaluation.py`, `tests/test_phase10b_regression.py`, plus
cross-listing cases added to `tests/test_instrument_import.py` and `tests/
test_instruments.py`. No real browser available in this environment;
hosted cross-browser verification remains a Phase 10 (post-release
monitoring) condition as before.

### Verified counts

Computed and printed from the real pinned snapshots during this phase, not
asserted from memory:

- Search-universe total: 2,947 canonical companies (2,927 NSE-only + 20
  BSE-cross-linked + 0 BSE-only).
- BSE records read: 20; all valid/active; 0 SME; 0 invalid; 0 missing ISIN;
  0 duplicate BSE codes/ISINs; 0 ambiguous records; 0 inactive listings.
- NSE/BSE cross-listing count: 20. BSE-only company count: 0 (none of the
  20 curated large caps are BSE-only; the code path is exercised via
  synthetic test fixtures).
- Canonical-ID change count: 0 (verified — the cross-listing bridge always
  resolves to the pre-existing NSE-created instrument ID).
- Research-universe count: 250 (unchanged). Ranking-universe count: 250
  (unchanged).
- Aliases added by BSE import: 0 (the cross-listing branch adds a listing,
  not an alias — matches the existing former-symbol/former-name alias
  semantics, which only fire on a symbol/name *change*, not a new
  exchange).
- Industry coverage: 270/2,947 (250 research-universe + 20
  BSE-cross-linked). Sector coverage: 0/2,947 (neither source populates a
  real sector value — a pre-existing Phase 0/1 characteristic).
- Public score hash: unchanged
  (`12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19`).
  Public financial hash: unchanged
  (`3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`).

### Phase 10B remaining limitations

See "Known limitations" in `search-architecture.md` (fully rewritten this
phase): BSE coverage is a 20-company curated fixture, not full breadth;
group-company ties still lack a market-cap/volume/prominence signal; no
sector data anywhere; no corporate-group field (by design, per the
phase's own constraints); no business description anywhere outside the
research universe; static/dynamic parity is structural, not continuously
verified against a live database (none is provisioned).

### Recommended Phase 10C scope

1. Provision PostgreSQL, run `search-universe-import` and
   `bse-search-universe-import` so the dynamic `/api/v1/search`,
   `/api/v1/search/meta` and `/api/v1/company/{id}/summary` routes serve
   the full universe in database-backed mode, not only the static path —
   and continuously verify static/dynamic parity against a live database.
2. Obtain reachable live BSE connectivity (a different network path, an
   authorized mirror, or a documented alternate official endpoint) and
   re-run `scripts/refresh_bse_search_universe.py` to replace the curated
   20-company fixture with full BSE main-board/SME breadth.
3. ~~A prominence signal (e.g. index membership breadth across NSE/BSE index
   families, once imported) to resolve group-company search ties by more
   than lexical remainder length — still without fabricated market-cap
   data.~~ Done structurally in Phase 10C Milestone 2 (search ranking policy
   v3's tie-break dimension 4, `index_membership_rank`) but still inert —
   see "Recommended Milestone 3 scope" for the remaining data-import step.
4. Weekly-build-time freshness metadata for `search-index.json` (a
   `retrieved_at`/staleness banner on lightweight pages, similar to the
   research-page freshness disclosures) — carried over from Phase 10A,
   still open.
5. Complete the deferred Phase 10 (pre-existing) post-release monitoring
   and accepted-condition closure work below — hosted cross-browser/
   VoiceOver/axe/Lighthouse verification now additionally needs to cover
   BSE code/exchange-hint search, the inactive-listing banner and the
   enriched lightweight-page cross-listing table.

### Recommended Milestone 3 scope

Phase 10C Milestone 2 (search ranking policy v3, see the phase ledger above
and `docs/search-architecture.md` "Search ranking policy version 3") is
complete. Recommended follow-on work:

1. Import real Nifty 50 / Next 50 / 100 / 200 / 500 constituent data (the
   provider already exists — `NiftyIndexInstrumentProvider` in
   `src/mbe/data/instrument_master.py` supports fetching any of these five
   indices by name; only Nifty Smallcap 250 is ever invoked today) so the
   broad-index-membership tie-break (dimension 4, `index_membership_rank`)
   stops being structurally-present-but-inert and can actually differentiate
   group-query ties like "Reliance" or "Adani" by real index breadth.
2. Wire classification provenance (sector/industry/conflict/review-status)
   into the DB schema so `InstrumentResolver`/`/api/v1/search` gets full
   tie-break parity with the static path instead of always treating
   `classification_conflict` as `False` — needs a migration, deliberately
   out of scope for both Milestone 1 and Milestone 2.
3. Investigate whether a dedicated partial-word-match scoring tier (as
   opposed to relying on the guarded fuzzy tier) would measurably improve
   multi-token partial queries — only if real evaluation-set evidence shows
   the fuzzy tier under-serving that case; do not add a new tier speculatively.
4. Consider whether the fixed `full_phrase_match` score (84) should be
   revisited relative to `company_name_prefix`'s remainder-length-degraded
   range (75–82) — today a company whose name merely *contains* a group's
   brand name as a substring (e.g. "Kotak Mahindra Bank Limited" for query
   "Mahindra") can outrank the group's own flagship prefix match (M&M).
   This is a primary-tier scoring change, so it needs its own evaluation-set-
   backed milestone, not a casual reorder.
5. Re-run the `site/` static rebuild in an environment with either a stable
   pinned market-data cache or explicit approval to accept live score/
   universe churn, so `search-index.json` actually carries the Milestone 2
   evidence fields in production rather than only in the offline test suite.

## Current working-tree state

Branch: `release/v1.0.0-rc1`, tracking `origin/release/v1.0.0-rc1`.

Phase 0 through Phase 8 source, generated output and verification assets are in
commit `6797a2e` and annotated tag `v1.0.0-rc1`. Preview fixes are in pushed
commits `786e61d`/`9de4642` and annotated tags `v1.0.0-rc2`/`v1.0.0-rc3`.
Production source is pushed commit
`6fb5a7ea26c2ce996e17e298aae4c41c0965605d` and annotated tags `v1.0.0-rc4`
and `v1.0.0`. Release-evidence documentation follows that source commit on the
release branch without changing the production identity.

Repository-local `.git/info/exclude` was narrowed from the overly broad `data`
pattern to `/data/`; this keeps root runtime data ignored while ensuring new
tracked-source candidates under `src/mbe/data/` appear in `git status` and
cannot be omitted accidentally.

Production deployment `EvCEEd2g9fkRVShmvAdwQeCdoZja` is live. Retain
`rBeoLhBW8hNZv5fX3iT64nwrvCsc` until the Phase 10 closure window completes.

## Known limitations and open risks

### Architecture and data

- Legacy analysis models and historical DuckDB callers remain ticker-keyed for
  compatibility. New canonical storage/API/static contracts use instrument
  IDs, but the analysis pipeline has not yet been fully converted end to end.
- The current master source is Nifty-index focused, not a complete NSE/BSE
  security master. It lacks BSE codes, listing/delisting dates, inactive
  listings, SME status, former names and corporate-action history unless a
  future source supplies them.
- Historical pre-Phase-1 DuckDB rows remain only partially reproducible; new
  rows link canonical build/instrument IDs, but old provider input snapshots
  cannot be reconstructed retroactively.
- Canonical financial statement, restatement, unit, basis, official attachment
  and reconciliation lineage now exists, but no bulk official corpus has been
  imported. Current production-static official multi-year coverage is 0/250.
- Weekly production still uses Yahoo statements. Live official NSE ingestion is
  disabled pending operator terms review and has only a one-company transport
  check plus deterministic fixtures, not scheduled operational proof.
- Phase 6 fixed a representative 12-company scope but did not acquire it: no
  operator review record exists. The captured sample lacks a full taxonomy
  namespace, EPS, revision, comparative context and multi-year series; its 8/8
  ground-truth result cannot estimate broader parser accuracy or coverage.
- PostgreSQL is designed but not provisioned. Dynamic v1 data routes safely
  return 503 without `MBE_DATABASE_URL`; static v1 snapshots are the current
  deployable compatibility path.
- The public screener exposes only Revenue CAGR and ROCE as approved Tier B
  compatibility fallbacks. Other raw ratios remain excluded until official
  coverage, sector semantics and reconciliation thresholds are measured.

### Reliability and security

- Weekly screening is sequential and repeatedly requests benchmark data.
- Legacy Yahoo build retries remain build-script-local, recognize stringified
  429 errors and use linear rather than exponential backoff. The new official
  fetcher has bounded exponential backoff but does not change the legacy path.
- Legacy provider cache writes are not atomic. The new official document cache
  is atomic and checksum-validated.
- Health/freshness APIs now exist, but there is no durable job-status store,
  provider circuit breaker, error monitor or operational dashboard.
- The v1 API has page/batch abuse limits but no distributed per-client rate
  limiter. Add platform/firewall or shared-store throttling before broad
  anonymous runtime use.
- Anonymous legacy live analysis remains expensive and has no rate limiting or
  cache.
- Authentication, authorization, CSRF policy and private user data do not exist.

### Product and frontend

- The new application experience is live in production. Hosted Chromium,
  Firefox/WebKit mobile/fallback, real VoiceOver, hosted axe/Lighthouse and
  exhaustive hosted-integrity evidence remain explicit post-release risks.
- Static ranking scope remains the published top 25. The full 250-name
  `instruments.json` snapshot is the research/ranking master, not a
  fabricated ranking of unpublished results. Since Phase 10A, canonical
  search itself uses a separate, deliberately wider `search-index.json`
  snapshot (~2,950 NSE securities) — see `search-architecture.md`.
- Static screener scope is the 250 successfully scored companies in the weekly
  Nifty Smallcap 250 build. It is not a complete NSE/BSE market screen and must
  move to mandatory server mode before scaling to several thousand securities.
- Canonical stock detail now covers all 250 scored companies. Only the top 25
  currently receive entity-matched company news; static filing timelines are
  unavailable, and history has only current/one previous compatible point until
  more weekly builds accrue. Sector explorer, news dashboard, calendar, full
  comparison workspace, watchlists, authentication and alerts remain future.
- The static site and local FastAPI terminal duplicate UI/routing concepts.
- The static research/ranking master (`instruments.json`, 250 companies)
  still lacks most aliases/former names and BSE codes because its official
  source does not supply them. The wider search universe (`search-index.
  json`) now carries a BSE code for 20 large-cap companies via the Phase 10B
  curated cross-listing fixture, but not for the 250 research-universe
  companies specifically (none of the 20 curated large caps happen to
  overlap with the smallcap research universe) or for BSE-only/SME
  companies. Dynamic search can expose richer imported metadata when a
  future source and PostgreSQL are configured.
- Real system-Chrome responsive screenshots, contrast/axe, keyboard journeys,
  zoom/reflow and reduced motion now pass. Firefox/WebKit and VoiceOver + Safari
  remain unverified because those automation paths were unavailable; they are
  required preview conditions, not inferred passes.
- CSP now prohibits inline executable script and `unsafe-eval`. It still permits
  inline style for deterministic generated presentation attributes. Narrowing
  `style-src` requires replacing those attributes without regressing charts.
- Local Lighthouse sees expected `/api/quotes` 404s because the static Python
  server does not emulate Vercel functions. Actual headers, compression,
  function routing/logs and cache behavior require preview verification.

### Providers

- Yahoo is unofficial, can be stale/rate-limited and may omit delay metadata.
- Official NSE result discovery is public-source but may change shape, deny
  access or be subject to terms/data-use constraints. Operators must review
  current terms; the code does not circumvent denial. Only Ind-AS XBRL is
  fixture-qualified and current canonical production coverage is zero.
- Provider-neutral interfaces exist, but only currently required providers are
  implemented; no licensed quote fallback exists.
- Google News matching has titles but no article bodies or canonical entities.
- Policy mapping is manually maintained and descriptive only.
- No paid or licensed exchange feed was introduced.

## Architecture decisions in force

1. Preserve the Python analysis/scoring engine and current deployment while a
   platform foundation is introduced incrementally.
2. Keep news/policy descriptive and unscored.
3. Prefer hiding uncertain news over publishing ambiguous matches.
4. Never invent quote delay/freshness values when the provider omits them.
5. Introduce canonical identity and versioned data contracts before building a
   feature-rich screener against ticker-keyed JSON.
6. Keep market/currency/country/time-zone identifiers extensible, while the UI
   remains India-first.
7. Keep DuckDB for legacy research history; use Alembic-managed PostgreSQL for
   concurrent platform reads and future user data, with SQLite only for
   compatible local/test behavior.
8. Never run migrations implicitly during public requests or static builds.
9. The static publisher must remain database-independent until PostgreSQL is
   provisioned and operationally proven.
10. Use ISIN as the strongest available security continuity key; never merge on
    similar names alone, and persist ambiguity for review.
11. Keep current Yahoo behavior behind normalized provider contracts without
    claiming unsupported paid/licensed data functionality.
12. Keep the production frontend statically rendered and progressively enhance
    one route at a time; do not introduce a framework until measured needs
    exceed the shared Jinja/vanilla architecture.
13. Use one normalized frontend domain model for static and dynamic modes and
    never merge rows from different build IDs.
14. Use system theme preference by default, persist only an explicit local
    override, and reserve red/green for signed financial or operational meaning.
15. Keep Node tooling development-only; the public Python build must continue
    to succeed without Node or PostgreSQL.
16. Treat the Python screener registry as the single public source of truth;
    generate browser metadata rather than duplicating field definitions.
17. Keep Phase 3 query logic AND-first and portable. Add nested groups/OR only
    through a future schema version, never through SQL or arbitrary expressions.
18. Exclude null from ordinary and negative screener comparisons; require
    explicit missing/available operators across SQL and static modes.
19. Publish the full scored 250-row screener snapshot while PostgreSQL is
    optional, but keep the top-25 ranking/report product boundary unchanged.
20. Do not expose financial ratios merely because they exist in DuckDB JSON;
    public filters require normalized lineage, period, unit and restatement
    semantics.
21. Keep normalized financial lineage beside the legacy score pipeline until an
    explicitly versioned score migration is validated; do not rewrite old builds.
22. Store filed facts relationally with decimal original/normalized values and
    use an indexed build projection for screening rather than querying raw EAV
    history for every row.
23. Prefer consolidated, fall back explicitly to standalone, and label unknown;
    never combine numerator and denominator across source, period, currency or
    basis.
24. Treat current Yahoo-derived public fundamentals as Ready-with-caveat and
    expose only Revenue CAGR and ROCE until official filing lineage expands.
25. Treat every official document as untrusted: allowlist NSE HTTPS hosts,
    validate length/MIME/signature, cache privately and parse only registered
    fixture-qualified templates. Unsupported is a valid stored state.
26. Never infer a revision from timestamp alone or a monetary unit from value
    magnitude. Explicit source evidence is required; conflict means quarantine.
27. Use versioned reconciliation and selection rules. Prefer accepted official
    facts, allow Yahoo fallback only per approved metric, store conflicts and
    never blend sources in one formula.
28. Keep live official ingestion disabled until an operator reviews current NSE
    terms/data-use conditions. Never run ingestion from public requests, static
    builds or browser automation.
29. Bind live pilot authority to a dated private review record and exact
    versioned manifest hash. A kill-switch environment variable or generic user
    request is not sufficient acknowledgement, and software controls do not
    establish legal compliance.
30. Treat taxonomy support, parser success, review acceptance, Tier-A
    eligibility, source selection and publication as separate states. Newly
    parsed official data cannot displace a fallback before the publication gate.
31. Keep single-operator pilot evidence and review decisions in deterministic
    private artifacts until an authorized corpus proves that a multi-user
    relational workflow is justified. Do not add a migration merely to label a
    validation phase.
32. A no-go is a valid pilot result. Small captured samples must show their
    denominator and cannot be generalized to unseen companies, taxonomies,
    revisions, contexts or derived metrics.
33. Use immutable instrument-ID company URLs as canonical. Keep symbol report
    URLs as full compatibility renderings with canonical metadata; do not make
    ticker or company-name slugs permanent identity.
34. Treat company research as a versioned provider/template-neutral projection.
    Static and dynamic adapters must use the same schema and deterministic
    explanation/peer policies; runtime quote/news are the only allowed live
    differences.
35. Derive explanations and peers at read/build time instead of persisting
    them until measured scale or audit requirements justify snapshots. Existing
    score/financial/filing indexes are sufficient; Phase 7 adds no migration.
36. Supersede decision 19's top-25 *report-page* boundary: rankings remain the
    published top 25, but all 250 scored instruments now receive canonical
    research pages. This does not fabricate 250 published ranking positions;
    pages disclose their current full-universe model rank and data scope.
37. Treat real-browser, accessibility, visual and public-value checks as release
    contracts. Chrome evidence is valid for Chrome only; unavailable engines or
    assistive technology remain explicit promotion conditions.
38. Keep executable CSP self-only. A tiny external synchronous theme bootstrap
    is preferable to inline executable code; inline style remains a separately
    disclosed defense-in-depth limitation.
39. Index only immutable canonical routes. Symbol compatibility routes and the
    generated not-found document are `noindex`; the sitemap must exactly match
    the 253 indexable canonicals.
40. Promote an immutable artifact through preview before production and retain a
    last-known-good deployment for rollback. Phase 8 authorizes neither preview
    creation nor production promotion.
41. A Vercel build-success status is not a preview pass. Application routes,
    headers, functions and browsers must reach the actual artifact; an SSO
    redirect is a blocked gate and cannot be substituted with config review.
42. Keep protected preview aliases and bypass credentials out of public
    documentation. Authenticate through the existing team or use an approved
    secure bypass; do not weaken Deployment Protection merely for automation.
43. Treat every Vercel Python entrypoint as independently packaged: bootstrap
    repository `src` explicitly and regression-test imports without ambient
    working-directory or `PYTHONPATH` assumptions.
44. Keep root Vercel `requirements.txt` aligned with every imported serverless
    runtime dependency; a dependency present only in `pyproject.toml` is not
    proof that Vercel functions receive it.
45. Authenticated Safari accessibility-tree evidence is useful semantic QA but
    is neither cross-browser automation nor a VoiceOver pass. Protection-layer
    headers are never application-header evidence.
46. When Vercel promotion creates a fresh Production-environment build instead
    of aliasing the verified preview, record the rebuild explicitly and require
    independent production smoke plus representative source/production hashes.
47. Explicit user risk acceptance can authorize production with bounded gates
    unresolved, but it does not convert those gates into passes. Carry each one
    into a named post-release closure phase and keep rollback Ready.

## Next phase

### Phase 10 — post-release monitoring and accepted-condition closure

Objective: monitor production deployment `EvCEEd2g9fkRVShmvAdwQeCdoZja`, close
the explicitly accepted release conditions, and retain deployment
`rBeoLhBW8hNZv5fX3iT64nwrvCsc` as the immediate rollback target.

1. Run a bounded post-release observation window over production route status,
   function request IDs, 5xx/error rate, cache behavior and unexpected provider
   activity. Record timestamps and results; do not enable live NSE ingestion.
2. Run hosted Chromium, Firefox and WebKit desktop/mobile, JavaScript-disabled
   and static/API-fallback journeys for navigation, search, rankings, screener,
   complete/missing company, legacy and 404 states.
3. Perform and record a real VoiceOver + Safari journey covering landmarks,
   dialogs, tables/scrollers, charts/SVG descriptions, live feedback,
   disclosures, checklist state and focus order.
4. Run hosted axe/visual checks and Lighthouse/transfer/request measurements.
   Perform exhaustive hosted public-value hashes, private-data/leak/security
   checks and route-count probes.
5. Treat any widespread 5xx, invalid public value, missing security policy,
   critical accessibility defect or unexpected provider activity as a rollback
   trigger. Promote the retained deployment and execute the runbook if needed.
6. If a defect is non-emergency, add a regression test and use a separate
   fix commit/tag/preview/production cycle. Never mutate the live artifact.
7. When the observation window and accepted conditions close, update this
   handover and release report, record whether rollback can be retired, and
   leave the working tree clean.

Out of scope: new metrics/model weights, live NSE corpus work without its exact
private gate, authentication/watchlists/alerts, full comparison workspace,
portfolio/trading, AI summaries, paid data, PostgreSQL provisioning and US
expansion.

## Phase 11 Milestone 1 — deterministic offline build architecture (2026-08-02)

- Status: Complete locally; not pushed or deployed.
- Objective achieved: the normal static render is offline, deterministic and
  unable to recompute model membership, scores, financials or DuckDB state.
- Previous coupling: `scripts/build_site.py` selected live NSE membership,
  fetched Yahoo info/statements/prices and benchmark data, ran `screen()`,
  appended DuckDB, fetched Google News, projected financials, built research
  and search payloads, copied frontend assets and rendered/pruned the entire
  site in one command. Wall-clock model/financial timestamps added churn.
- New commands: `refresh_market_data.py`, `build_model.py`,
  `build_financials.py`, `build_research_payloads.py`, offline `build_site.py`,
  `build_search_assets.py`, `build_frontend_assets.py`, and
  `verify_deterministic_build.py`.
- Frozen inputs: checked manifest
  `builds/manifests/phase11-m1-frozen-inputs.json`; Smallcap model build
  `1bd53d15-67c6-4b02-b830-0eb0bb1d582b`; financial build
  `34baaa1c-e2f6-508b-b2f0-389669739b2a`; pinned membership/canonical/search
  sources; 250 financial and 250 company-research payloads. The manifest is
  marked `legacy_baseline` because the pre-M1 raw Yahoo cache was not a
  committed immutable acquisition artifact. Future refreshes produce a real
  normalized source artifact first.
- Network behavior: only explicit acquisition is networked. Model, financial,
  research, render, search and frontend stages consume frozen inputs. Offline
  stages deny socket/URL calls and fail immediately on an attempt. The checked
  site manifest reports `network_used: false`.
- Site manifest: `site/build-manifest.json`, schema
  `2026-08-02.11.1`, deterministic UUIDv5 site build ID, controlled generated
  time, search/classification policy versions, nullable large/mid build IDs,
  Smallcap and financial build IDs, universe versions, input/output/config
  hashes, news cutoff, quote mode, build mode, status and warnings.
- Determinism: two clean builds completed in 1.568 seconds and produced the
  identical complete-output digest
  `11f061c7bcfc26d6a916161790e90be765022242e3c9f81d4076b17d56713976`.
- Preservation: score hash remains
  `12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19`;
  financial hash remains
  `3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`;
  rankings, screener, 250-company research JSON tree, financial JSON tree,
  canonical master and 250-member universe are byte-identical. Company HTML
  research content is unchanged; the frontend-only build intentionally updates
  shared Phase 10 search scope/copy on all pages. Search JSON intentionally
  advances from the stale static 10B policy artifact to verified policy
  `2026-08-02.10c.2` without touching model/financial artifacts.
- Release shape: 279 HTML, 509 JSON (one new build manifest), 250 canonical
  company pages, 25 legacy pages and 253 sitemap/indexable routes.
- Migration: none; existing Alembic history is unchanged.
- Verification: 659 Python tests and 35 frontend tests passed; ESLint,
  TypeScript, Python compilation, `git diff --check`, release verification,
  deterministic double-build and a fresh SQLite `alembic upgrade head` plus
  `alembic check` passed. A measured in-place offline render completed in
  3.47 seconds. The release verifier reconfirmed both preservation hashes and
  every declared site-manifest output hash.
- Detailed audit, commands, manifest contract, rollback and Milestone 2 gate:
  [`phase11-m1-deterministic-build.md`](phase11-m1-deterministic-build.md).
- Exact Milestone 2 recommendation: import pinned official Nifty 100 and Nifty
  Midcap 150 memberships into additive versioned universe manifests, map every
  member to existing canonical IDs, reconcile overlap/primary membership,
  persist membership history, and publish coverage/eligibility reports. Do not
  calculate or expose large/mid-cap rankings until universe-specific model
  configurations are reviewed and validated in Milestone 3.

## Phase 11 Milestone 2A — universal company report coverage architecture (2026-08-03)

- Status: Complete locally; not pushed or deployed.
- Objective achieved: every one of the 2,947 search-universe companies now
  carries a deterministic, versioned coverage-level assessment instead of a
  binary "has research page or not" split, and the ~2,697 non-Level-3
  companies are served an honest, coverage-appropriate page rather than a
  flat "not researched" placeholder.
- Four coverage levels (`mbe.coverage.domain.CoverageLevel`, assigned by the
  single `mbe.coverage.policy.assess_coverage()` function every caller
  shares): **Level 0 — Identity Coverage** (identity only, the floor);
  **Level 1 — Market Coverage** (identity plus live quote, requires a
  provider symbol); **Level 2 — Financial Coverage** (adds a financial
  summary, requires financial data and a provider symbol); **Level 3 — Full
  Research** (the existing full research page, requires model score, full
  research payload, financial data and provider symbol together, all four).
  Each level's page sections are a strict superset of the previous level's.
- Policy version `RESEARCH_COVERAGE_POLICY_VERSION = "2026-08-03.11.2a.1"`
  (`coverage_level_version` for the level/section taxonomy is tracked
  separately as `"1.0"`).
- The existing 250 Level-3 pages are byte-for-byte unchanged: same score
  hash (`12a5ef89c5584…`), same financial hash (`3e992181163743…`), same
  research-universe membership. This milestone is purely additive to the
  other ~2,697 instruments and to search/API metadata.
- Static/serverless decision, with real measured numbers from a full
  offline+search+coverage-artifact build: the 250 Level-3 pages stay static;
  the other ~2,697 instruments are served by the coverage-aware
  `api/company.py` serverless fallback, computing `assess_coverage()` on
  demand from the bundled search index. `site/` total ~21.02 MiB
  (22,043,312 bytes); `site/company/` (250 static pages) ~6.06 MiB
  (6,352,941 bytes); `search-index.json` average record 1,725.9 bytes (max
  1,953, 2,947 records); `research-coverage.json` 764 bytes. Rendering all
  2,697 non-Level-3 instruments as real static pages, at a sampled real page
  size of ~10,753 bytes/page, would cost ~27.66 MiB — roughly 1.3x the
  entire current `site/` output, and ~4.6x the current `company/` directory
  alone (the 250 static pages) — which is the concrete justification for the
  static/serverless split. Level counts in the current frozen build: Level
  0: 0, Level 1: 2,697, Level 2: 0, Level 3: 250. Build durations for the
  three independent offline stages: site render ~2.16s, search-asset build
  ~1.19s, coverage-artifact build ~0.89s.
- New artifact: `site/data/research-coverage.json`
  (`mbe.builds.offline.build_coverage_only`), aggregating per-record
  coverage fields already written into `search-index.json` — schema
  version, coverage policy version, build IDs, instrument count, level
  counts, coverage-reason tally, generated-at and source hashes.
- New API surface: `GET /api/v1/company/{instrument_id}/coverage`
  (`CoverageData` envelope) and additive coverage fields on
  `GET /api/v1/company/{instrument_id}/summary` — both DB-backed, both
  return the standard bounded 503 `database_not_configured` error when
  PostgreSQL isn't provisioned, same as every other dynamic route.
- New search fields: `SearchIndexRecord` gains `research_coverage_level`,
  `coverage_label`, `coverage_level_version`, `research_coverage_status`,
  `research_eligible`, `research_eligibility_reasons`,
  `research_sections_available`, `research_sections_missing`,
  `coverage_policy_version` and `financial_available`; `app.js`'s
  `researchBadgeText()` renders the four public badges ("Full Research",
  "Financial Coverage", "Market Coverage", "Identity Only"). Ranking and
  match-tier logic (`SEARCH_RANKING_POLICY_VERSION`) are unchanged — coverage
  is exposed as data on each result, not folded into ranking.
- Known limitation: **Level 2 has zero real members today.** Financial data
  is only computed for the 250 Smallcap-model companies
  (`scripts/build_financials.py` is scoped to
  `universes/nifty-smallcap250-instruments.json`), so every instrument with
  financial data today also qualifies for Level 3 outright — there is no
  financial data source yet for any other instrument, and ingesting one is
  out of scope for this milestone. Level 2 is fully specified, policy-tested
  and template-tested, but will show 0 members until a broader financial
  data source exists.
- Pre-deploy step required: the checked-in `site/api/v1/search-index.json`
  predates this milestone and does not yet carry the new coverage fields.
  Regenerating it (`scripts/build_search_assets.py` then
  `scripts/build_coverage_artifact.py` against the frozen manifest, then
  committing the refreshed `search-index.json` and `research-coverage.json`)
  was deliberately not done as part of this milestone's implementation,
  since it touches a checked-in build artifact whose interaction with
  `builds/manifests/phase11-m1-frozen-inputs.json`'s pinned artifact hashes
  needs explicit human review — verified safe for the score/financial hash
  gate specifically, but the broader frozen-manifest interaction was not
  fully characterized.
- Tooling gap found, not yet fixed: `scripts/verify_release.py`'s hardcoded
  expected JSON count (509) doesn't account for the new
  `research-coverage.json` artifact, and its offline-build check expects
  `build-manifest.json`'s `build_mode` to read `"offline"`, but running the
  search-asset/coverage-artifact stages after `build_site.py` leaves it
  stamped `"search-only"` (the last stage's own label). Does not affect the
  real checked-in `site/`, which still passes `verify_release.py` cleanly.
- Full detail, exact module/field references and the Milestone 2B
  recommendation: [`coverage-architecture.md`](coverage-architecture.md).
- Verification: 699 Python tests and 36 frontend tests passed.
- Working-tree/commit/deployment state: committed locally on branch
  `phase11-m2a-coverage` (20 commits); not merged, pushed or deployed; no
  migration, no scoring/ranking/financial-value change; PostgreSQL still
  not provisioned.

## End-of-phase update template

Copy this section when closing each future phase:

```markdown
### Phase N — <name>

- Status:
- Date completed:
- Objective achieved:
- Main implementation:
- Architecture decisions:
- Files/modules changed:
- Database migrations:
- New/changed environment variables:
- Provider/data limitations:
- Tests run and results:
- Build/deployment result:
- Known limitations introduced or remaining:
- Working-tree/commit/deployment state:
- Next phase:
```
