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
