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
