# Multibagger Engine

Autonomous equity research & multibagger discovery engine. India-first (NSE/BSE),
US-capable. Evidence-driven: every score is traceable to a metric, a benchmark
threshold, and a rationale; every analysis carries a confidence level derived
from data completeness.

## Quickstart

```bash
uv sync
uv run mbe analyze RELIANCE.NS          # full research report -> reports/
uv run mbe screen nifty-midcap150      # rank an NSE index universe
uv run mbe snapshot india-midsmall     # screen + persist to DuckDB store
uv run mbe history MCX.NS               # score time series from the store
uv run mbe backtest nifty-midcap150 --limit 60   # does the score predict returns?
uv run mbe universes                    # curated + NSE index universes
uv run mbe sectors nifty-midcap150     # industry momentum ranking + themes
uv run python scripts/build_site.py     # offline render from frozen manifests -> site/
uv run python scripts/verify_deterministic_build.py
uv run mbe db-migrate                   # apply canonical relational migrations
uv run mbe instruments-import --download-official --dry-run
uv run mbe instruments-validate        # require all 250 mappings to be unique
uv run mbe financials-import filings.json --dry-run
uv run mbe financials-coverage         # latest normalized dataset status
uv run mbe nse-filings-discover --fixture-dir tests/fixtures/nse-official
uv run mbe nse-financials-ingest --fixture-dir tests/fixtures/nse-official --dry-run
uv run mbe financials-unsupported      # safe unsupported/quarantine report
uv run mbe financials-conflicts        # bounded reconciliation conflicts
uv run mbe company-research-validate  # offline page/contract/route/leak validation
uv run mbe company-research-measure   # static company HTML/JSON footprint
uv run mbe official-pilot-validate     # Phase 6 bounded scope; offline
uv run mbe official-pilot-corpus-verify
uv run mbe official-pilot-evaluate --dry-run
uv run mbe api                          # versioned read API -> :8001/docs
uv run pytest                           # offline test suite
npm ci && npm run check                 # frontend lint, types and unit tests
```

## What it does (v0.1)

For any ticker, the pipeline runs:

1. **Data** — Yahoo Finance connector behind a `DataProvider` protocol
   (swappable; NSE/filings providers planned), with an on-disk TTL cache.
2. **Fundamentals** — growth CAGRs, margins & trend, ROE/ROCE/ROIC, leverage,
   coverage, cash conversion, accruals (earnings quality), dilution.
3. **Technicals** — in-house pandas indicators (RSI, MACD, ATR, ADX, Bollinger,
   CMF, OBV, stochastic), Minervini-style trend template, 52-week structure,
   relative strength vs NIFTY/S&P.
4. **Valuation** — two-stage scenario DCF (bear/base/bull) with an
   owner-earnings floor for capex-heavy compounders, reverse DCF (implied
   growth), PEG/EV-EBITDA/P-S/FCF-yield multiples.
5. **Risk** — rule-based flags (solvency, coverage, earnings quality, dilution,
   valuation heat, liquidity, volatility, governance gaps) → risk score and
   probability-of-permanent-loss bucket.
6. **Scoring** — table-driven benchmarks (`scoring/benchmarks.py`) feed five
   pillars (Quality, Growth, Financial Strength, Valuation, Momentum) plus
   Size-Runway and Reinvestment for the **Multibagger Score**. Hard gates cap
   the score for broken economics (accruals, coverage, dilution, cash burn).
   Every pillar ships an evidence table.
7. **Report** — institutional-style markdown: thesis, financials, technicals,
   valuation scenarios, risk table, entry/exit framework, position sizing,
   full evidence appendix, data gaps.

## Design principles

- **Missing data is surfaced, never imputed** — it lowers confidence instead.
- **Explainability over cleverness** — thresholds are data, not code, so the
  v0.2 backtesting harness can recalibrate them empirically.
- **Conservative by construction** — the DCF stacks cautious assumptions, so
  absolute fair values skew low across the board; ranking power comes from the
  relative metrics (PEG, implied-growth gap, FCF yield). Calibration against
  historical outcomes is the top v0.2 deliverable.
- **Batch-resilient** — one bad ticker never kills a screen.

## Architecture

```text
src/mbe/
├── models/      # pydantic domain models (company, analysis, scoring)
├── data/        # DataProvider protocol, DiskCache, YahooProvider
├── analysis/    # fundamentals.py, technicals.py, valuation.py, risk.py (pure functions)
├── scoring/     # benchmarks.py (tables), pillars.py, engine.py
├── report/      # markdown.py (jinja2 report + screen table)
├── pipeline.py  # orchestration, graceful per-ticker degradation
├── universe.py  # curated starter universes
└── cli.py       # typer CLI
```

Specs and plans live in `docs/superpowers/`.

The current architecture audit and staged platform roadmap are in
[`docs/architecture-audit-2026-08-01.md`](docs/architecture-audit-2026-08-01.md).
Runtime variables and data cadences are documented in
[`docs/environment.md`](docs/environment.md).
For continuity across compacted chats and implementation phases, always start
with [`docs/HANDOVER.md`](docs/HANDOVER.md) and update it at the end of each phase.
Canonical identity, PostgreSQL/SQLite setup, imports, provider contracts,
migrations and `/api/v1` are documented in
[`docs/platform-foundation.md`](docs/platform-foundation.md).
The Phase 2 frontend architecture and route migration plan are in
[`docs/frontend-architecture.md`](docs/frontend-architecture.md).
The Phase 3 typed screener, public fields, null/operator semantics and financial
readiness assessment are in
[`docs/screener-architecture.md`](docs/screener-architecture.md).
Official NSE discovery, document safety, supported formats, reconciliation,
source precedence and operator/legal gates are documented in
[`docs/official-nse-ingestion.md`](docs/official-nse-ingestion.md).

## v0.2 additions

- **NSE index universes** — NIFTY 50/500, Midcap 150, Smallcap 250, Microcap 250
  constituent lists downloaded from niftyindices.com and cached (7-day TTL).
- **DuckDB run store** (`data/mbe.duckdb`) — every `snapshot` persists scorecards;
  `history` shows a ticker's score time series; backtest summaries accumulate.
- **Point-in-time backtest harness** — statements gated by FY-end + 90-day filing
  lag, prices truncated at cutoff, present-day fields (holdings, PE, beta)
  excluded so nothing leaks. Reports Spearman IC, top/bottom-quantile spread and
  hit rate per cutoff. Known caveats printed in every report: survivorship bias
  (today's constituent lists), ~5y Yahoo statement depth limits cutoffs, no
  costs/slippage — a validation instrument, not a strategy simulator.

## v0.9 additions

- **Sector rotation & tailwind engine** — groups screened companies into
  industries (with a sector-level pool fallback for thin industries), scores
  each stock's industry momentum against its screened peers, and attaches a
  leave-one-out per-stock Sector Momentum pillar (a stock's own momentum is
  excluded from its group's medians, since that is already paid by the
  Momentum pillar). `mbe sectors` ranks a universe's industries directly.
- **Curated descriptive-only tailwind theme tags** (dated `CURATED_AS_OF`,
  staleness always printed alongside them) surfaced in reports and screens.
- **Validation status, stated plainly:** the pre-registered sector-momentum
  ablation (4 samples, US + India, 2y horizon) demoted the pillar to
  descriptive-only — augmented beat base in only 1/4 samples. The engine
  shows sector context on every card and report but does not score it; the
  multibagger score is unaffected.

## Hosted weekly picks (v0.10, deterministic build since Phase 11 M1)

Every Monday, GitHub Actions builds a public read-only page of the NIFTY
Smallcap 250 multibagger ranking — the lab (`mbe serve`, CLI, backtests)
stays local; the site is only its published output. The Phase 2 site has a
reusable, progressively enhanced research application shell. It respects the
system colour preference until a persistent light/dark override is chosen.

- **What the page shows** — an interactive top-25 multibagger/investment ranking
  with shareable filters, stable sorting, pagination, density and column
  controls, canonical instrument search, explicit build/data-mode metadata,
  week-over-week entries/exits, sector-momentum context, 3-5 recent
  headlines per pick, policy/scheme headlines per industry (each sourced
  and dated), and freshness-labelled quotes when available. Each pick's report page carries
  peer-comparison, ownership, financial-trend and scenario charts (v0.15) as
  inline SVG. Rankings remain server-rendered and useful without JavaScript;
  browser enhancement reads either the typed API or versioned static snapshots.
  The public `/screener.html` route screens all 250 scored weekly companies in
  static mode and uses `POST /api/v1/screener/query` when the canonical database
  is available. Phase 4 adds normalized financial lineage, Revenue CAGR and
  ROCE filters, read-only financial coverage/metric/company APIs, and bounded
  canonical summaries on the 25 published reports. Current values retain an
  explicit Yahoo-compatibility/unknown-statement-basis caveat. Phase 5 adds an
  explicit, disabled-by-default official NSE result-ingestion path with safe
  caching, fixture-qualified Ind-AS XBRL, revision-aware views and provider
  reconciliation. The current static dataset truthfully remains 0/250 official
  multi-year coverage; no browser automation, OCR, paid feed or bulk scrape is
  hidden inside the build.
- **Architecture** — a GitHub Actions job verifies and renders the checked
  frozen build every Monday; it cannot fetch Yahoo/NSE/BSE/RSS data, recompute
  scores or write DuckDB. Provider acquisition, model, financial, research,
  search-only and frontend-only operations are explicit separate commands.
  Vercel serves the committed `site/` artifact (no implicit data refresh).
  Delayed quotes are served by a single stdlib-only Vercel serverless
  function scoped to the published tickers. See
  `docs/phase11-m1-deterministic-build.md` for refresh/promotion and rollback.
- **Honesty carried over from the reports** — descriptive layers (sector
  momentum, theme tags, news, policy) are shown, never scored; a build
  that can't analyze at least 100 of the 250 names refuses to publish
  rather than ship a degraded ranking; every page carries the same
  model-validation footer as the research reports.

## Canonical and live search (v0.11, upgraded in Phase 2)

Open the command search with `/` or Ctrl/Cmd+K and search the pinned canonical
Smallcap 250 master by symbol, company name or ISIN. The browser uses the typed
lookup API when configured and the full versioned instrument snapshot otherwise.
All scored names open the stable canonical `/company/{instrument_id}.html`
research route. The 25 historical ticker report paths remain compatibility
pages with canonical metadata. Other unscored master names use the existing
on-demand analysis route. Direct `/api/analyze?ticker=…` requests still support
other valid Yahoo-covered tickers.

- **What live analysis does** — the no-JavaScript fallback and canonical search
  can route a ticker to `/api/analyze`, which runs the same `analyze_ticker()` pipeline as the CLI
  and returns a full HTML report at a shareable URL. Labelled on the page as
  live, not part of the weekly ranking, and can take 10-30s (a cold
  serverless fetch against Yahoo, not a lookup from `data.json`).
- **Architecture** — a free Vercel serverless function (`api/analyze.py`),
  packaged with a scoped `requirements.txt` rather than the full project's
  dependencies. No disk cache (`YahooProvider(cache=None)`) and no
  prediction-ledger persistence — stateless serverless has no database to
  write one to — so this is an honest one-shot report: full thesis,
  critique, and evidence, same validation footer as everywhere else, just
  no history across searches.
- **Security** — a reflected XSS was found in the error page (a rejected
  ticker was echoed back unescaped) and fixed before merge by HTML-escaping
  every interpolated value and dropping exception detail from the client-
  facing 500 page entirely. Recorded here in keeping with this project's
  practice of stating real findings plainly rather than glossing over them;
  usage is small right now, but the fix is in place regardless.

## News & policy context (v0.14)

Every report carries a **Recent News & Policy Context** section: dated,
sourced, English headlines for the company and for its industry's policy
environment. It replaces two failures that had both been shipping silently.

- **The section was a stub.** Every report ever published rendered the
  literal text *"Macro, government-policy and news catalyst modules arrive
  in v0.3 — this section will populate automatically."* It never populated.
- **Policy tagging could never match.** The site pulled PIB's RSS feed,
  which serves **Hindi** headlines, and tagged them against a **lowercase
  English** keyword table — 0 of 12 items tagged in the last build, and none
  ever could have. `Lang=1/2/3` and `Regid=1..6` all return Hindi or an
  empty feed, so it was not a parameter fix. The build printed
  `12 policy items` either way, which is why it survived so long.
- **What replaced it** — `sector_policy()` builds a policy query from the
  stock's industry against the Google News pipeline that already worked.
  **The query is the relevance filter**, so no separate keyword-matching
  step remains that can quietly return nothing while the build reports
  success. Cached per industry, so members of a sector share one fetch.
- **The query names the regulator, not the Yahoo label**, because that
  design puts all the relevance on the wording — so the wording was
  measured rather than assumed. Querying `Electrical Equipment & Parts`
  returns national-policy filler; querying `power ministry transmission CEA`
  returns transmission-corridor policy. Hand-scoring every headline across
  all 20 live industries: **67% relevant and 7/20 industries covered** on the
  raw label, **84% across 20/20** with `POLICY_TERMS`. Broadening the query
  with `scheme OR subsidy OR tariff` made it *worse* — those words match any
  government story. Method and per-industry numbers: Addendum 25 in
  `docs/backtest-findings-2026-07.md`. A missing table entry falls back to
  the raw label and still searches, and the build prints unmapped industries.
- **Empty states are explicit.** Every branch that could render nothing
  renders text instead — *"No recent company news found."*, *"No sector
  policy items found."*, *"No sector classification — policy context
  unavailable."* The old version's defining flaw was looking identical
  whether it worked or not. A typical week fills ~7 of 20 queried
  industries; the build line reports which, not how many it asked.
- **Never scored.** No pillar, no weight, no risk flag — the same contract
  as sector themes, franchise and stewardship. Headlines are evidence a
  reader weighs, not catalysts the engine has identified.

## Roadmap

- **v0.3** — macro dashboard, filings ingestion (annual reports, con-calls),
  promoter pledging via NSE data; benchmark-table recalibration fed by
  accumulated backtest evidence. News and policy context shipped in v0.14 as
  a *descriptive* layer — turning either into a scored signal needs its own
  pre-registered validation and is not scheduled.
- **v0.4** — web UI, scheduling, portfolio construction, continuous-improvement loop.

## Release verification

Phase 8 adds development-only real-browser, accessibility, visual-regression and
performance checks. It does not add a production JavaScript dependency.

```bash
npm run check
npm run test:browser:chromium
npm run test:visual
uv run python scripts/verify_release.py \
  --fixture tests/fixtures/phase8-public-value-hashes.json
```

The complete promotion procedure and rollback criteria are in
`docs/deployment-runbook.md` and `docs/pre-deployment-checklist.md`. Chrome is
verified locally; Firefox/WebKit, VoiceOver + Safari and actual Vercel headers
remain required preview gates. Phase 8 did not deploy, commit or push.

## Known limitations (v0.1)

- Yahoo Finance only: ~5 years of statements, no promoter pledging/FII-DII
  detail, occasional stale `info` fields.
- DCF conservatism understates fair value for high-multiple quality names.
- No macro/policy/sentiment *signal*: news and policy headlines are surfaced
  as context (v0.14) but never scored, and no macro layer exists at all.

## Disclaimer

Research tooling, not investment advice. Model outputs carry stated assumptions
and incomplete data; verify independently before any investment decision.
