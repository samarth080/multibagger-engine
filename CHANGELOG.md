# Changelog

## v0.1.0 — 2026-07-12

Initial vertical slice, built spec-first with TDD (51 offline tests).

### Added
- Domain models with explicit missing-data semantics (`None` + completeness, never imputed).
- `DataProvider` protocol; Yahoo Finance connector (yfinance 1.5) with canonical
  statement field map and fallback row names; disk cache (JSON + parquet, TTL).
- Fundamentals engine: CAGRs, margins/trend, ROE/ROCE/ROIC, leverage, coverage,
  cash conversion, accruals ratio, reinvestment rate, dilution.
- Technicals engine: in-house RSI/MACD/ATR/ADX/Bollinger/stochastic/OBV/CMF,
  Minervini trend template, 52w structure, relative strength, volatility regime,
  traded-value liquidity.
- Valuation engine: two-stage scenario DCF (bear/base/bull), reverse DCF via
  bisection, owner-earnings floor for capex-heavy cash-backed compounders,
  PEG/EV-EBITDA/P-S/FCF-yield multiples, explicit assumptions dict.
- Risk engine: 9 rule families -> flags with severity, composite risk score,
  permanent-loss bucket.
- Scoring engine: table-driven benchmarks; Quality/Growth/Strength/Valuation/
  Momentum pillars with per-metric evidence and weight renormalization on
  missing data; Investment Score (risk-haircut) and Multibagger Score
  (size runway + reinvestment) with hard gates; confidence from completeness,
  statement years, and price history depth.
- Markdown research report (thesis, scenarios, entry/exit, sizing, evidence
  appendix, data gaps) and universe screener with per-ticker failure isolation.
- Typer CLI: `analyze`, `screen`, `universes`. Curated starter universes.

### Verified
- Live NSE run: `analyze RELIANCE.NS` sane vs known figures (ROCE ~9.5%,
  P/E ~22, D/E 0.44); `screen india-midsmall` processed 25/25 tickers with the
  quality-compounder cohort (MCX, KPIT, CAMS, Polycab, Dr Lal) ranked top.

### Design decisions of note
- Sizing guidance can never recommend a position when the verdict is Avoid.
- DCF is deliberately conservative; absolute fair values skew low. Empirical
  recalibration of all benchmark tables is the headline v0.2 deliverable.

## v0.2.0 — 2026-07-12

### Added
- NSE index universe ingestion (NIFTY 50/500, Midcap 150, Smallcap 250,
  Microcap 250) from niftyindices.com, cached 7 days, loud failures.
- DuckDB run store (`data/mbe.duckdb`): `mbe snapshot` persists scorecards,
  `mbe history` shows per-ticker score time series, backtest summaries stored.
- Point-in-time backtest harness: statements gated by FY-end + 90-day filing
  lag, prices truncated at cutoff, present-day fields (holdings/PE/beta)
  excluded to prevent lookahead. Reports Spearman IC, top/bottom-quantile
  spread, hit rate. `mbe backtest UNIVERSE --cutoffs … --horizon … --score …`.

### Measured (see docs/backtest-findings-2026-07.md)
- First live calibration evidence on NIFTY Midcap 150 (60 names, 2 cutoffs,
  1y horizon): mean IC ~0.02 (multibagger), ~0.01 (investment), -0.03
  (momentum, with a -0.14/+0.08 regime flip across the midcap correction).
  Conclusion: no demonstrated 1-year edge at this sample size; no
  recalibration performed (2 cutoffs = curve-fitting risk); deeper
  fundamentals history is the binding constraint.

### Fixed
- Spearman IC on constant score vectors now returns None instead of NaN.

## v0.3.0 — 2026-07-12

### Added
- **Local web research terminal** (`mbe serve` -> http://127.0.0.1:8000):
  stored runs, rankings with score meters, in-browser research reports
  (analyze any ticker), per-ticker score history, backtest evidence table.
- **SEC EDGAR fundamentals provider** (`--fundamentals edgar`): 15-20 years of
  US annual statements from XBRL companyfacts, original-filing values only
  (restatements ignored to prevent leakage), per-year exact first-public dates.
- `FinancialHistory.filed` + filed-date-aware point-in-time truncation
  (exact dates beat the FY-end + 90d heuristic; late filers handled honestly).
- `CompositeProvider` (EDGAR statements + Yahoo prices/info), `us-largecap60`
  universe, technical-only backtests no longer require statements at cutoff.

### Measured (docs/backtest-findings-2026-07.md)
- Momentum, 8 annual cutoffs, 60 Indian midcaps: mean IC -0.01, whipsaw
  -0.30..+0.20 — no stable annual-rebalance momentum edge.
- US large caps via EDGAR (7 cutoffs 2018-2024): multibagger 1y IC +0.004,
  investment 1y IC -0.025, multibagger 2y IC -0.001. Caveat recorded: a
  large-cap universe structurally penalizes the size-runway pillar in a
  mega-cap-led regime; proper test needs small/mid-cap universes (queued).

### Fixed
- EDGAR tag fallbacks merge across eras (ASC 606 revenue tag switch) — values
  verified against Apple's reported figures to the million.

## v0.3.1 — 2026-07-12

### Added
- Full-depth price history (`period=max`) — backtest cutoffs back to ~2012.
- Disjoint replication samples (`us-smallcap-sample2`, stride midpoints).
- **Model validation status section in every research report** (test-enforced):
  states the current null result and links the findings record.

### Measured — headline research conclusion (docs/backtest-findings-2026-07.md)
- Decade matrix (12 cutoffs x 2 disjoint S&P600 samples, 2y horizon):
  primary +0.098 mean IC vs replication **-0.028** — the earlier +0.16 was
  sample luck. Cross-sample agreement only in 2021-22 (regime effect).
  **No demonstrated persistent edge; benchmark tables remain unvalidated
  priors.** Next directions: pillar-level attribution, Indian replication
  (BSE PDF pipeline), delisting-inclusive universes.

### Fixed
- Findings addendum dedupe; local DuckDB store untracked from git.
- (Process) pytest-pipe exit codes masked one failure; verification now uses
  pipefail.

## v0.4.0 — 2026-07-12

### Added
- **NSE XBRL fundamentals provider** (`--fundamentals nse`): Indian Ind-AS
  annual statements from NSE corporate-results filings, with **exact broadcast
  dates** for true point-in-time gating. Consolidated-preferred, original-filing
  dedupe, EBIT/EBITDA/FCF derived. Verified to the crore vs Reliance FY24.
  defusedxml parsing. Coverage FY2019+ (pre-Ind-AS taxonomy is future work).
- Survivorship sensitivity analysis + raw-panel export on the harness.
- `OVERVIEW.md` — plain-language tour of the whole engine.

### Measured
- **First India home-market backtest** (50 NIFTY smallcaps, 2y): mean IC
  **+0.232**, 3/3 cutoffs positive — strongest home-market number yet, but a
  single post-COVID regime on a small survivorship-biased sample; recorded as a
  promising-but-unvalidated lead (docs/backtest-findings Addendum 8).
- Survivorship sensitivity collapsed the last US signal (Size Runway) to ≈ 0 →
  clean null on US samples confirmed (Addendum 7).

## v0.5.0 — 2026-07-13 (Phase 2 begins: business intelligence)

### Added
- **Business-Quality / Franchise-Durability engine**: decade-scale ROCE
  consistency, margin stability & trajectory, incremental ROIC, earnings-quality
  track, downturn resilience → evidence-backed classification (Durable
  Compounder / Steady / Cyclical / Turnaround / Deteriorating / Unproven).
- **Living Investment Thesis**: falsifiable assumptions with probabilities from
  the company's own track record, explicit falsifiers, bull/base/bear business
  trajectories, thesis confidence.
- **Self-critique (devil's advocate)**: enumerates disconfirming evidence before
  any recommendation; can veto.
- **Longitudinal thesis memory**: every thesis persisted to DuckDB;
  `mbe analyze` reports what changed since the last look (change detection).
- Reports gain a "Business & Investment Thesis" section; franchise available as
  a labelled research score in the backtest harness.
- Phase 2 vision/roadmap (docs/PHASE2_VISION.md): one validated increment at a
  time; every module must prove incremental value or be demoted.

### Measured — and demoted accordingly (Addenda 9-10)
- **Franchise score: validated null predictor** (0/3 samples ≥ base IC; worse
  on India and US replication). Demoted to descriptive-only; never ranks picks.
- **Critique veto: does not avoid worse outcomes** (vetoed names had higher
  mean returns AND higher loss rates — it selects volatility). Relabelled as
  reasoning transparency, explicitly not a validated filter, in every report.
- Model-validation disclosure updated to state both nulls.

## v0.6.0 — 2026-07-13 (P2.2: the scientific spine)

### Added
- **Prediction ledger**: every thesis assumption becomes an accountable 1-year
  prediction (append-only DuckDB ledger; dedup by claim identity; outcomes
  recorded, never rewritten). Return/price forecasts deliberately excluded —
  no validated return edge exists to stake.
- **Resolution engine** + **calibration scoring** (Brier, reliability table),
  `mbe calibration` command, calibration panel on the web terminal home.
- **Retro-calibration** over real history: 2,770 predictions emitted and
  resolved point-in-time on both sides.

### Measured — first validated improvement (Addendum 11)
- Confidences are informative: Brier 0.132 vs 0.25 coin-flip; top bucket
  nearly perfectly calibrated (93% stated / 92% observed, n=1141).
- Systematic underconfidence in middle buckets (+15pp): persistence is
  autocorrelated beyond base rates.
- Bucketwise calibration map learned on US, tested on India out-of-sample:
  **Brier 0.170 -> 0.153 (-10.2%)** — the correction transfers across markets.
  Now applied at emission (raw confidence kept for provenance).

### Fixed
- Web: ticker input sanitization (stray backslash), friendly HTML error pages,
  franchise-score bound overflow on elite compounders (TCS-shaped bug).

## v0.7.0 — 2026-07-13 (P2.3: management & capital-allocation intelligence)

### Added
- **Stewardship engine**: full-history dilution vs buybacks, allocation fit
  (compounding machine vs empire builder), debt-vs-EBIT growth discipline,
  cash-return consistency → evidence-backed classification (Owner-Operator
  Discipline / Balanced / Empire Builder / Serial Diluter / Unproven).
- "Management & capital allocation" section in every research report and on
  the web terminal; `stewardship` available as a labelled research score in
  the backtest harness.

### Measured — demoted per pre-registered rule (Addendum 12)
- Ablation 0/3 samples ≥ base IC — stewardship is descriptive-only, never
  ranks picks. Nuance: it tracks the base score closely (not anti-signal);
  it duplicates rather than adds selection information.

## v0.8.0 — 2026-07-13 (India: deeper history, honest replication)

### Added
- **Legacy NSE results parser**: pre-FY2019 filings (no XBRL) parsed from
  archives HTML pages — India statement depth 6 -> 11 years (FY2013+),
  verified exact vs Reliance FY16. P&L-only for legacy years (surfaced via
  completeness, never imputed).
- Fixed a live-data trap: old entries carry `.../xbrl/-` placeholder URLs that
  pass startswith("http") — real-URL detection added with regression test.

### Measured (Addendum 13)
- India replication first regressed (+0.047 vs +0.232 on 2021-23 windows),
  then the extended 2016-2023 windows showed **both disjoint samples positive
  (+0.100 / +0.138 mean IC, 6/8 windows)** — the first cross-sample-consistent
  signal in the project (the US never had sample agreement). p ≈ 0.07;
  survivorship caveats hold; verdict stays "suggestive, not proven"; no
  recalibration.

## v0.9.0 — 2026-07-18 (P2.4: sector rotation & tailwind intelligence)

### Added
- **Sector rotation & tailwind engine**: industry grouping over a screened
  universe with sector-pool fallback for thin industries (`<Sector> (other)`),
  leave-one-out sector-momentum pillar per stock, `mbe sectors` CLI command,
  and curated descriptive-only theme tags dated `CURATED_AS_OF` (staleness
  always printed alongside them).
- Sector context surfaced in `screen()` output and in every research report.
- Backtest harness gained `multibagger_sector` and `sector` score names
  (for ablation) plus two new caveats now printed in every backtest report:
  present-day sector labels applied to historical cutoffs (mild, disclosed
  lookahead) and survivorship biting sector-momentum harder than stock
  signals (hot sectors are where dead names died).

### Measured — demoted per pre-registered rule (Addendum 14)
- Ablation: augmented (`multibagger_sector`) beat base in only 1/4 samples
  (us-smallcap-sample +0.098→+0.093, us-smallcap-sample2 -0.028→-0.034,
  india-primary +0.163→+0.123, india-replication +0.104→+0.111) — Sector
  Momentum is demoted to descriptive-only per the majority rule fixed before
  results were seen. Sector-alone IC was positive in all four samples
  (+0.034 / +0.042 / +0.081 / +0.319) but too weak to improve the blend at
  the pre-registered 0.12 weight; either-way-recorded discipline maintained.

### Fixed
- NaN in-progress Yahoo price bars are now dropped at ingestion (was
  surfacing as "nan INR" across reports).
- DCF fair value floored at 0 with a `debt_overhang_floor` flag (was showing
  negative per-share values for heavily levered names).

## v0.10.0 — 2026-07-18 (hosted weekly picks: static publish pipeline)

### Added
- **RSS news & policy provider** (`src/mbe/data/news_rss.py`): Google News
  headlines per company and a PIB government-policy feed tagged to sector
  keywords, defusedxml-parsed. A feed failure degrades to an empty list
  rather than failing the weekly build (blast-radius reasoning — context
  must never sink a build); item counts are printed so an empty feed stays
  visible, not silent.
- **Static-site builder** (`src/mbe/publish.py`): `build_data` (top-25 +
  sector table + tags + news + policy → `data.json`), `diff_weeks`
  (week-over-week entered/exited strip), `render_site` (dark-theme
  `index.html` + per-pick static report pages via markdown, autoescape on,
  honest model-validation footer on every page).
- **Delayed quotes function** (`api/quotes.py` + `vercel.json`): stdlib-only
  Vercel serverless function serving ~15-min-delayed quotes for the
  published tickers; whitelist sourced from `site/data.json`, `.NS`-regex +
  30-symbol cap, fails open to regex+cap alone when `data.json` is
  unavailable (deliberate — this is public delayed data).
- **Weekly build orchestration** (`scripts/build_site.py`): throttled
  provider (jittered sleep + 429 backoff retries) to survive datacenter-IP
  rate limits, refuses to publish a degraded ranking (<100 of 250
  analyzed), persists the run to DuckDB, then news → diff → render. First
  live build: 250/250 analyzed, 21/25 picks with headlines, 12 policy
  items.
- **GitHub Actions weekly workflow** (`.github/workflows/weekly.yml`):
  Mondays 02:30 UTC (08:00 IST, pre-open), Actions cache for `data/`,
  commits `site/` to the repo — Vercel's git integration auto-deploys (no
  CLI, no token).

### Fixed
- `.gitignore`'s `data/` and `reports/` patterns anchored to `/data/` and
  `/reports/` — the unanchored forms were false-matching `src/mbe/data/`
  and `site/reports/`, which must stay tracked.
- News RSS: zone-less `pubDate`s (naive datetimes) now normalized to UTC —
  they were crashing `dedupe_recent`'s aware-datetime comparisons.
- News RSS: non-http(s) link schemes dropped at parse time — a
  `javascript:` URI from a feed would otherwise survive autoescape as a
  live clickable link.
- **`src/mbe/data/nse_xbrl.py` was never in git**: the pre-anchor `data/`
  ignore pattern silently excluded the NSE XBRL provider from every commit
  since it was written — nine modules import it, so any fresh clone was
  broken. Surfaced by the anchoring fix; now tracked. A fresh-clone test
  run (188/188) confirms the tracked tree is self-sufficient.
- `render_site` now prunes `site/reports/` pages for tickers that dropped
  out of the top table — a stale report at a live URL would present last
  week's analysis as current.

## v0.11.0 — 2026-07-20 (live search-any-stock)

### Added
- **Live search-any-stock** (`api/analyze.py`): a Vercel serverless function
  that runs the real `analyze_ticker()` + report pipeline on demand for any
  ticker typed by a visitor, and returns the full HTML research report as a
  shareable URL. Ticker format validated before any network call; no disk
  cache (`YahooProvider(cache=None)` — a parquet-backed cache isn't worth
  the deployment weight for a best-effort, warm-instance-only benefit); no
  prediction-ledger persistence (stateless serverless has no database) — an
  honest one-shot report, not a regression from the CLI's ledger feature.
  Errors render clean pages (400 bad ticker, 404 not found, 500 unexpected)
  instead of raw crashes.
- `src/mbe/publish.py` gained `render_report_page(bundle, back_href=...)`, a
  shared, parametrized report-shell wrapper now used by both the weekly
  static reports and the new live-search endpoint (verified byte-identical
  output on the existing weekly path before/after the extraction).
- Root `requirements.txt` + `vercel.json` update: a scoped Python dependency
  list for `api/analyze.py` (pandas, numpy, yfinance, pydantic, jinja2,
  markdown, defusedxml), deliberately excluding scipy/duckdb/pyarrow/
  fastapi/uvicorn/typer/rich — traced against the function's actual import
  graph rather than reusing the full project's dependencies.
- Search form on the hosted weekly-picks page (`site/index.html`): plain GET
  form (no JavaScript) posting to `/api/analyze`, labelled live, not part of
  the weekly ranking, can take 10-30s.

### Fixed
- **Reflected XSS in the analyze error page**: the 400 branch fires exactly
  when a ticker does *not* match `_TICKER_RE`, so the rejected raw string
  was being echoed straight into the error page unescaped —
  `?ticker=<script>...` rendered a live `<script>` tag. Manual adversarial
  review had only checked whether a value *matching* the regex could be
  dangerous, missing that the vulnerable branch is reached precisely when
  it doesn't; caught by automated security review before merge. Fixed by
  HTML-escaping every value interpolated into `_ERROR_PAGE`; the 500 path
  no longer reflects exception details to the client at all (logged
  server-side only, via Vercel's function logs). Two regression tests
  added.

## v0.14.0 — 2026-07-31 (news & policy context)

### Fixed
- **Every report shipped a placeholder.** `Catalysts & Policy Tailwinds`
  rendered the literal text "modules arrive in v0.3 — this section will
  populate automatically" in every report ever published. It never populated.
- **Site policy tagging could never match.** `PIB_RSS_URL` served Hindi
  headlines while `POLICY_KEYWORDS` matched lowercase English, so 0 of 12 items
  tagged in the last build. `Lang=1/2/3` and `Regid=1..6` all return Hindi or an
  empty feed — not a parameter fix. The build printed "12 policy items" either
  way, so the failure was invisible.

### Added
- **Recent News & Policy Context** in every report: dated, sourced, English
  headlines for the company and for its industry's policy environment, with
  explicit "none found" text on every empty branch — silence is what let the
  old version look like it worked.
- `sector_policy()` builds a policy query from the stock's industry against the
  Google News pipeline that already works. **The query is the relevance
  filter**, so no separate keyword-matching step remains that can fail quietly.
- Site policy items now carry source and age, matching the reports; the heading
  carries the same descriptive-only label Sector momentum does. Age is computed
  in `build_data` against `built_at`, because a published page is read for a
  week after it is built and a bare pubDate does not say how stale a headline
  was when the ranking was struck.

### Changed
- The build's policy line reports sectors that returned items
  (`12 policy items from 7/20 sectors queried`) rather than sectors asked.
  "N items across K sectors" overstated coverage — the same class of
  self-flattering build output that let the dead PIB path look healthy.

### Removed
- `policy_items`, `PIB_RSS_URL`, `POLICY_KEYWORDS` and their test. A second
  policy path that has never produced a tagged item is worse than none.

### Validation status
Descriptive only. No pillar, no weight, no risk flag — the same contract as
sector themes, franchise and stewardship. Headlines are evidence a reader
weighs, not catalysts the engine has identified.

## v0.13.0 — 2026-07-30 (market-aware 3-year scenario forecast)

Every name in the top 25 was showing downside in **every** scenario, bull
included, for businesses with 33% ROCE and no debt. Two independent causes,
both fixed.

### Fixed
- **DCF base cash flow was a 3-year mean of a level series**, which
  systematically understates any business whose cash flow is growing and cannot
  absorb a step change at all. HBLENGINE.NS: FCF ran 58.6 -> 196.2 -> 93.9 ->
  588.1 (Rs cr), so the mean was 292.7 against a latest of 588.1 — every
  scenario compounded off 54% of last year's actual cash. Base FCF is now
  current earning power. Measured: no smoothing variant fixes this; normalizing
  on the median FCF margin scores *worse* than the bug.
- **Conservatism sat in the input all three scenarios shared**, so the haircut
  applied three times and the bull case inherited the bear case's pessimism.
  The peak-year risk now lives in the bear scenario, exposed as
  `spike_ratio` rather than baked into the base.
- **The owner-earnings floor was a second copy of the same bug** (floored at
  0.7 x 3y-mean net income). Now 0.7 x latest net income, consistent with the
  base rule.
- **The report's "delivered-growth median" label described a 25% cap**, not the
  median it claimed. Removed with the block it lived in.

### Added
- **3-Year Price Forecast**: bull/base/bear target prices projected from revenue
  x net margin against an exit multiple blended from leave-one-out peer medians,
  the stock's own point-in-time P/E history, and a franchise-quality premium.
  Probability-weighted expected 3y CAGR, with weights drawn from thesis
  assumption support and franchise score. Every assumption renders as an
  argue-with-able line plus a full anchor audit trail.
- **Two-sided sanity guards.** `apply_bull_guard` stops bull stacking sustained
  growth, margin expansion and full re-rating into fantasy (5x in 3 years,
  measured). `BASE_RERATE_CAP` stops the base case assuming near-full
  convergence to peer multiples — BLS trades at 14.2x against 44x peers and was
  anchoring its *base* case at 45.0x, a +217% re-rating giving a +73%/yr "base"
  CAGR. Neither the input nor any single scenario may carry all the pessimism or
  all the optimism.
- **Coherence flags**: `MULTIPLE_AT_LOW` (trading at the bottom decile of its own
  multiple history), `EARNINGS_SPIKE` (bear case is load-bearing),
  `FORECAST_INCOHERENT` (bull assumes less growth than the market already pays
  for — a model error, not a finding). Reported, never scored.
- Signed forecast-accuracy measurement in the backtest harness. Signed rather
  than absolute because the defect being watched for is systematic
  understatement, which an absolute error would conceal.

### Changed
- `margin_of_safety` is now honest, which flows into the Valuation pillar and
  **changes the ranking**. On identical cached data HBLENGINE.NS moved #11 -> #2
  (Valuation pillar 49 -> 69, MoS -45.2% -> +4.7%). Nine names moved by >= 0.4;
  the rest were unaffected, as expected — the fix only bites where latest cash
  flow genuinely diverges from the trailing mean.
- `AnalysisBundle` carries `prices`; forecasts run as a cross-sectional
  post-pass in `screen()`, mirroring the sector-pillar contract.

### Validation status
The forecast **feeds no score**. It is descriptive-only, exactly as
`franchise_score` and the critique veto already are, until the harness shows it
earns a place — consistent with `docs/backtest-findings-2026-07.md`, which
records that none of the current scores show a demonstrated persistent edge. The
Indian sample spans 2021-2025 and holds barely one non-overlapping 3-year
window, so initial accuracy evidence will be weak and should be read that way.

## v0.12.0 — 2026-07-20 (trading-platform UI)

### Added
- **Dual-theme trading-platform UI** across every rendered surface (index,
  weekly report pages, live-search reports, analyze error pages):
  Zerodha-Kite-inspired dark theme (`#1F2022` / `#38A6F0` / Material
  green-red) as the default, Groww-inspired light theme (`#F3F4F6` /
  `#5076EE` / `#039955`-`#D32F2F`) behind a persistent ☀/☾ toggle
  (localStorage, applied pre-paint — no flash). Hand-rolled CSS custom
  properties, deliberately no Tailwind: the pipeline has no build step and
  none was added.
- Index restyled trading-app style: sticky top nav (brand, section tabs,
  in-nav search pill, theme toggle), changes-this-week as gain/loss chips,
  card-contained tables with two-line company rows, quote cells showing
  **LTP + day-change %** (from the existing `/api/quotes` response) with
  the honest "since pick ±x%" line kept underneath. Quotes JS builds DOM
  nodes via `textContent`/`createElement` — no `innerHTML`.
- Validation footer wording unchanged — the styling changed, the honesty
  did not.

### Changed
- Analyze error page migrated from a `str.format` template in
  `api/analyze.py` to a jinja-autoescaped `render_error_page()` in
  `mbe.publish` — escaping is now structural (template engine) rather than
  per-call-site `html.escape`. The XSS regression test was tightened to
  assert the precise property (raw payload absent, escaped form present,
  exactly one script tag — our theme boot) since themed pages legitimately
  carry one script of their own.
