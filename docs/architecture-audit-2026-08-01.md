# Multibagger Engine architecture audit

Audit date: 2026-08-01

## Executive assessment

Phase 5 update: the working tree now contains bounded official NSE result
discovery, safe attachment caching, fixture-qualified Ind-AS XBRL parsing,
revision-aware views, provider reconciliation/source selection, official filing
APIs and explicit fallback labels. The current static dataset still contains no
canonical official multi-year series, so it honestly reports 0/250 official
coverage and keeps the two existing filters on their approved Yahoo fallback.

Phase 4 introduced a canonical financial filing/fact
warehouse, dataset builds, quality lineage, two evidence-gated fundamental
screener fields, read-only financial APIs and bounded report summaries. The
production static build remains PostgreSQL-independent. Current projections are
still Yahoo compatibility data with unknown basis/filing date; official NSE
coverage expansion remains the next data-quality priority.

The repository is a well-tested quantitative research engine with a small
published surface, not yet a full interactive equity platform. Its strongest
assets are the explainable scoring pipeline, honest validation disclosures,
point-in-time backtest tooling, batch resilience, and weekly India small-cap
workflow. These should be retained.

The production application is a generated HTML site committed to `site/` and
served by Vercel. It has no production database, authentication, application
backend, screener query engine, canonical instrument master, or provider-health
system. A local FastAPI research terminal and DuckDB history store exist, but
neither is deployed. Product expansion should therefore be incremental: first
stabilize the published data contracts, then introduce a versioned API and
canonical data model before building interactive screens.

## Current architecture

| Area | Current implementation | Assessment |
|---|---|---|
| Language/runtime | Python 3.12, Pydantic 2, pandas/numpy | Suitable for the research and ingestion layers |
| Published frontend | Jinja-rendered static HTML/CSS/JS in `src/mbe/publish.py`; generated files in `site/` | Fast and cheap, but one large template and limited interactivity |
| Dynamic production routes | `api/quotes.py` and `api/analyze.py` Vercel Python functions | Narrow, unversioned, no authentication or throttling |
| Local application | FastAPI server-rendered terminal in `src/mbe/web/app.py` | Useful research UI; not the deployed product |
| Persistence | Local DuckDB (`data/mbe.duckdb`) for runs, results, theses, predictions and backtests | Good research ledger; no migrations, constraints, indexes or production durability |
| Primary market provider | Yahoo Finance through `yfinance` | Provider protocol exists, but production is operationally coupled to Yahoo |
| Other providers | NSE annual-results XBRL/legacy HTML, EDGAR, NSE index CSVs, Google News RSS | NSE/EDGAR fundamentals are optional CLI composites, not weekly production defaults |
| Cache | File TTL cache: JSON and Parquet | Effective locally/CI; no atomic writes, lineage, cache status or distributed invalidation |
| Scheduling | GitHub Actions every Monday at 08:00 IST; commit `site/`, which triggers Vercel | Simple and reproducible, but only one workflow and no job-status store |
| Deployment | Vercel static output plus two Python functions | Preserves current deployment; unsuitable by itself for private user features |
| Tests | 321 offline tests at audit baseline; network tests excluded by default | Strong pure-domain coverage; limited deployed-contract and end-to-end coverage |

## Current data and product flows

1. The weekly job downloads the current Nifty Smallcap 250 constituents.
2. Each ticker is analyzed sequentially. Yahoo provides company metadata,
   annual statements and adjusted daily prices. A benchmark price series is
   fetched for relative strength.
3. Pure analysis modules calculate fundamentals, technicals, valuation,
   business quality, stewardship, forecast and rule-based risk.
4. The scoring engine combines five investment pillars plus size runway and
   reinvestment into Investment and Multibagger scores. Hard gates cap the
   Multibagger score at 35 for specified earnings-quality, solvency, dilution
   or viability failures. Confidence is derived from analysis completeness,
   statement history and price-history depth.
5. Sector/industry context is calculated leave-one-out. Its failed ablation is
   disclosed and it remains descriptive rather than scored.
6. The run is saved locally to DuckDB. Recent company and policy headlines are
   fetched from Google News RSS. All 250 scored company research pages and 25
   legacy report compatibility pages are rendered to static files.
7. The browser requests quotes for the 25 published symbols from a Vercel
   endpoint. Live one-ticker analysis is a separate stateless serverless path.

Current production universe: the live Nifty Smallcap 250, with 25 published
ranked names. Pinned universe snapshots are used by research scripts to improve
backtest reproducibility. Curated large-cap/mid-small and US samples also
exist, but US is not part of the weekly production workflow.

## What is static and dynamic

- Static: ranking page, weekly data payload, 250 canonical company pages,
  top-25 report compatibility pages, sector table,
  themes, policy context, model disclosures and all report charts.
- Dynamic: delayed quote fetch and on-demand single-ticker analysis.
- Local-only dynamic: stored runs, score history, backtest summaries,
  prediction calibration and report generation through FastAPI.

Production API routes:

- `GET /api/quotes?symbols=...`
- `GET /api/analyze?ticker=...`

At the Phase 0 audit baseline there were no versioned production APIs for instruments, search,
financials, rankings, screener queries, sectors, news, events, watchlists,
comparisons, methodology, freshness or job status.

## Strengths to preserve

- Explainable evidence rows and table-driven scoring thresholds.
- Explicit missing-data confidence penalties rather than imputation.
- Research-ranking language and validation disclosures.
- Point-in-time truncation and documented survivorship/cost limitations.
- Batch continuation when one ticker/provider call fails.
- Score, thesis and prediction history in the local research ledger.
- Descriptive-only treatment of unvalidated themes, sector momentum and news.
- India-first units, indices and scheduled small-cap discovery workflow.
- Offline fixtures that keep tests independent of third-party availability.

## Priority findings

### P0: news entity matching

The published `site/data.json` contains medical, sports, US-government and
architecture stories for BLS. Root cause: the query used `"company name" OR
"ticker"` and accepted every returned title. A short symbol was treated as an
entity identifier even without company, exchange, country or industry
corroboration. Exact-title deduplication also allowed lightly rewritten wire
duplicates.

Phase 0 response: query on company-name variants plus India/exchange context,
score every title using company-name coverage, guarded symbol evidence,
industry context and source quality, hide scores below 55, expose match
confidence, cluster near-duplicate titles, and version the cache key so old
false positives cannot survive a rebuild. RSS lacks article bodies; this is a
conservative title-level matcher, not full named-entity resolution.

### P0: quote reliability and freshness

The quote endpoint previously returned only price and percentage change. It
discarded provider timestamps, delay metadata, market state and error reasons;
the UI hard-coded `~15 min` and rendered every failure as `n/a`. The endpoint
also failed open as a public Yahoo proxy if its symbol whitelist could not be
loaded.

Phase 0 response: return previous close, absolute/percentage change, quote
timestamp, provider-reported delay, currency, exchange, market status and stale
reason; expose partial failures; show the metadata in each row; and fail closed
when the published-symbol whitelist is unavailable.

### Data quality and reproducibility

- Ticker is the identity throughout the application and DuckDB. There is no
  internal security ID, ISIN, BSE code, alias/former-name table or provider
  symbol mapping.
- Score builds lack a persisted model version, factor configuration hash,
  provider version, universe version and validation status.
- DuckDB stores pillar/metric JSON but not rank, rank change, data lineage or
  complete input snapshots, so historical builds are not fully reproducible.
- Consolidated/standalone status, restatements, units and corporate-action
  lineage are not modeled consistently across providers.
- Weekly analysis uses Yahoo statements despite the NSE statement adapter.
- Current market data has no automated missing/impossible-value dashboard.

### Reliability and observability

- The weekly screen is sequential and repeatedly fetches the same benchmark,
  making Yahoo latency/rate limits the dominant bottleneck.
- Retry logic lives in the build script, recognizes only stringified 429s and
  uses linear rather than exponential backoff.
- Broad exception handling intentionally preserves builds, but structured
  error type/provider/job context is not retained.
- There is no job table, health/freshness endpoint, provider circuit breaker,
  error monitor or operational dashboard.
- File-cache writes are not atomic and corrupted cache JSON can propagate an
  exception to callers.
- The dynamic analysis route has no cache or request throttling and can perform
  several expensive third-party calls per anonymous request.

### Security and privacy

- No secrets are currently required in production, which limits exposure.
- Jinja autoescaping and URL-scheme filtering address known XSS/link risks.
- Dynamic routes have input format validation/caps but no per-client rate
  limiting, abuse monitoring or shared request budget.
- Security headers are incomplete, and the inline-script/static-template model
  complicates a strict Content Security Policy.
- Authentication, authorization, CSRF policy and private data do not exist yet;
  they become mandatory before watchlists or saved screens are introduced.

### Frontend, accessibility and performance

- Static delivery, small handwritten JavaScript and inline SVG charts are fast.
- The production template lacks a full application shell, global entity search,
  filterable/sortable tables, pagination, keyboard table navigation, reusable
  states and route-level page structure.
- Heavy information is encoded in a single template module, increasing change
  risk and making component testing difficult.
- Loading/failure states are text substitutions rather than reusable skeleton,
  retry, empty and stale components.
- Basic labels, focus styles and SVG accessible names exist. Remaining gaps
  include table captions/scope, richer status announcements and systematic
  automated accessibility testing.

### Dead or duplicated architecture

- The deployed static UI and local FastAPI terminal are separate visual and
  routing systems.
- Theme and page-shell concerns are embedded in Python strings rather than
  reusable template files.
- Provider retry/throttle behavior is a script wrapper rather than a shared
  provider policy.
- README version labels, package version `0.1.0`, and feature versions through
  `v0.15` are inconsistent.

## Phase 1 foundation update (2026-08-01)

Roadmap step 2 is implemented in the working tree. Ticker-keyed legacy paths
remain compatibility surfaces, but new identity/storage/API code uses immutable
instrument IDs, normalized aliases/listings/provider mappings, Alembic-managed
relational tables, versioned model builds and typed `/api/v1` read contracts.
Yahoo quote parsing is behind a provider-neutral adapter, and the Phase 0
endpoint consumes it without weakening its whitelist.

The official Nifty constituent CSV currently maps all 250 pinned production
symbols one-to-one and supplies name, ISIN, series and industry. It is not a
complete exchange master: BSE codes, inactive listings, listing dates and SME
history remain source gaps.

PostgreSQL is the production target, SQLite is local/test-only, and DuckDB is
retained as the legacy research ledger with additive migrations. The static
publisher remains database-independent and now emits a versioned build
manifest/canonical IDs plus static v1 snapshots.

Remaining deployment work is to provision managed PostgreSQL/pooling and
configure Vercel environment separation. Shared rate limiting, job
orchestration, financial-statement lineage and full NSE/BSE history remain
future hardening. See [`platform-foundation.md`](platform-foundation.md).

## Phase 2 application update (2026-08-01)

Roadmap step 3 is implemented in the working tree through progressive
enhancement rather than a framework rewrite. The generated ranking route now
uses a reusable Jinja shell, external design tokens and a typed-with-JSDoc
vanilla browser client. It remains statically rendered and database-optional.

The browser client selects the database-backed v1 API when it is healthy and
falls back once per session to compatible versioned snapshots. It provides
canonical command-palette search, shareable ranking filters, stable sorting,
pagination, columns, density, CSV export, bounded visible-row quotes, score
details and explicit loading/empty/stale/error states. The static instrument
snapshot now covers the full pinned 250-name master while rankings remain the
published top 25. Existing report paths and the on-demand analysis route remain
useful search destinations.

The shell adds semantic landmarks, skip navigation, visible focus, focus-trapped
dialogs, keyboard result/table navigation, screen-reader announcements,
reduced-motion handling and responsive table behavior. System theme preference
is respected until a local light/dark override is saved. Static methodology is
indexable, while placeholder routes are not created.

Additive migration `20260801_0002` stores technical trend and concise score/risk
explanations for dynamic rankings. No score weights changed. Development-only
Node tooling now supplies ESLint, JavaScript type-checking and deterministic
unit/DOM journeys; the production site still has no Node build dependency.
See [`frontend-architecture.md`](frontend-architecture.md).

In-app browser discovery returned no available browser during final QA, so
pixel-level screenshots and a real-engine manual accessibility pass remain to
be completed on the next machine with that surface. Generated DOM structure,
keyboard/dialog/filter behavior and static fallback are covered by automated
tests, but this does not replace real responsive visual review.

## Phase 3 screener update (2026-08-01)

Roadmap step 4 is implemented in the working tree. A centralized 28-field
registry now defines types, operators, units, null behavior, availability,
formatting and static/dynamic support. A bounded AND-first query contract is
compiled through allowlisted parameterized SQLAlchemy expressions with stable
multi-sort, canonical tie-breaking, count/pagination, build metadata, query
fingerprinting and matched-condition explanations.

The public `/screener.html` route reuses the application shell and progressively
selects the dynamic POST API or compatible static contracts. Static mode screens
all 250 scored weekly companies and clearly states that it is not an all-market
screen. Conditions, sorting, pages, columns and density are shareable without
accounts; presets are visible ordinary conditions; CSV exports carry lineage
and neutralize spreadsheet formulas.

Financial readiness was measured rather than inferred. DuckDB contains several
high-coverage ratios, but they remain ticker/JSON keyed and lack normalized
period, units, statement basis, restatement and source lineage. They are not
public filters. No migration, model-weight change, paid provider or production
database was introduced. See [`screener-architecture.md`](screener-architecture.md).

## Phase 5 official financial ingestion update (2026-08-01)

Migration `20260801_0004` adds official source/attachment lineage, filing
relationships, reconciliation and selected-source records. Live discovery is
explicitly disabled pending operator terms review; allowlisted requests are
rate-, retry-, redirect-, byte- and run-capped and cached outside public assets.
The parser registry supports only NSE Ind-AS result XBRL for facts. Every other
format has a visible metadata-only, unsupported or quarantine state.

The implemented adapter completed a bounded two-request KFINTECH discovery and
XBRL parse (77,853 bytes, 16 live facts) and supplied the captured offline
fixture. No bulk NSE scrape occurred. Fixture tests verify 15 facts,
basis conflicts, idempotency, revisions, latest-known/as-filed cutoffs,
reconciliation and source precedence. Static builds never call NSE and existing
scores/ranks are untouched. Full rules and operating constraints are in
[`official-nse-ingestion.md`](official-nse-ingestion.md).

## Phase 6 controlled-corpus pilot update (2026-08-01)

Phase 6 hardened the validation boundary without making a new live request.
Live discovery and download now require the Phase 5 kill switch, the exact
12-company annual-results manifest, a non-expired private operator review record
bound to its SHA-256 scope, and the review ID supplied again on the command
line. The manifest caps four filings/company, 48 documents, 60 requests, 120 MB
total and 30 minutes. Repeated 403/429 responses stop rather than trigger
evasion.

The captured KFINTECH excerpt has an immutable corpus manifest and offline
integrity command. A versioned concept registry, Decimal scale/precision
evidence, duplicate/nil handling, XML resource bounds, private review queue,
append-only reversible decisions, independent eight-fact ground truth and
explicit Tier-A/publication policy were added. Source-selection version
`2026-08-01.2` prevents unreviewed official values from displacing public
fallbacks.

The operator-review prerequisite was not satisfied, so the result is no-go:
0 live companies attempted, one captured reduced filing, 8/8 exact facts only
within that sample, 0 Tier-A facts/metrics, 13 unresolved review items and no
Revenue CAGR/ROCE official series. No migration was justified for the private
single-operator artifact workflow. Public output and scores remain unchanged.
See [`phase6-official-corpus-pilot.md`](phase6-official-corpus-pilot.md) and
[`phase6-readiness-recommendation.md`](phase6-readiness-recommendation.md).

## Phase 7 canonical company research update (2026-08-01)

Phase 7 adds the immutable `/company/{instrument_id}.html` destination and a
versioned provider-neutral company-research model shared by static and dynamic
modes. All 250 scored companies receive HTML and JSON; search, ranking,
screener and peer actions use canonical identity. The 25 ticker report paths
remain full compatibility renderings with canonical metadata.

The page combines deterministic score explanations, evidence-backed
strengths/risks, bounded persisted history, the two approved public financial
metrics with Yahoo fallback/Tier-B disclosure, technical trend, transparent
industry/sector peers, public-safe filing state, thresholded news, a local
checklist and build/source trust panel. Official Tier-A coverage stays 0/250
and public score/financial values are unchanged. No migration, provider,
model-weight or NSE-ingestion change was made.

See [`company-research-architecture.md`](company-research-architecture.md) for
the schema, rules, parity contract, route strategy, operations, security and
measured footprint.

## Implementation roadmap

1. **Stabilize the current deployment.** Complete entity-aware news filtering,
   freshness-aware quotes, honest failure states, environment documentation,
   focused tests and a verified production build.
2. **Introduce the platform foundation.** Add canonical instruments and aliases,
   provider capability interfaces, ingestion/job models, model-build metadata,
   migrations and a versioned read API. Keep the existing static publisher as a
   compatibility consumer during this transition.
3. **Build the application shell and rankings.** Create navigation, global
   search, theme/accessibility primitives, reusable data states and a
   server-paginated rankings table using the new API.
4. **Add the screener (complete in Phase 3).** The typed AND-first schema,
   metadata/query API, static compatibility and shareable public route now
   exist. Authenticated persistence remains deferred until authorization.
5. **Normalize financial lineage and official-source reconciliation (complete
   through the Phase 6 no-go pilot), then add stock detail/market/sector surfaces.** Build only
   from period/unit/source/restatement-aware,
   freshness-labelled datasets. Lazy-load licensed charts and keep unavailable
   data explicit.
6. **Add user workflows.** Authentication, private watchlists, saved screens,
   comparisons and events, with audit logging and authorization tests.
7. **Harden operations.** Split ingestion schedules, idempotent jobs,
   exponential backoff/circuit breakers, provider health, data-quality checks,
   observability, performance budgets, accessibility/E2E tests and deployment
   runbooks.

US support should remain behind market/currency/calendar/provider identifiers;
no US product work is required in the current phases.
