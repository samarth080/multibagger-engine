# Multibagger Engine — v0.1 Core Design

**Date:** 2026-07-12
**Status:** Approved (autonomous mode — user directive: never pause for approval)
**Scope:** Sub-project 1 of the Autonomous Equity Research & Multibagger Discovery Engine

## 1. Mission context

The full brief describes a multi-year platform (fundamentals, technicals, valuation,
macro, policy, trends, risk, scoring, reports, continuous improvement). That is too
large for one spec, so it is decomposed into sub-projects:

| Phase | Sub-project | Status |
|-------|-------------|--------|
| v0.1 | Core engine vertical slice: data connectors → analysis engines → explainable scoring → screener → reports | **this spec** |
| v0.2 | Universe expansion (full NSE/BSE lists), persistent store (DuckDB), score backtesting/validation harness | next |
| v0.3 | Macro dashboard, policy/news ingestion, sentiment, filings (annual reports, con-calls) | later |
| v0.4 | Web UI, scheduling, portfolio construction, continuous-improvement loop | later |

v0.1's goal: for any ticker (India-first: `.NS`/`.BO`; also US), produce an
evidence-backed, confidence-scored investment analysis and rank a universe of
candidates by Multibagger Score.

## 2. Guiding principles (from the brief)

- Optimize for **highest expected risk-adjusted return**, never raw return.
- **Every score explainable**: each carries evidence items (metric, value, benchmark, contribution, rationale).
- **Confidence levels everywhere**: driven by data completeness, history length, and estimate dispersion.
- **Missing data is surfaced, never silently imputed.** It lowers confidence instead.
- No hype-chasing: quality/risk gates precede any growth/momentum enthusiasm.

## 3. Approaches considered

1. **Monolithic script + notebook** — fastest to demo; rejected: unmaintainable, untestable, contradicts "highest quality architecture".
2. **Microservices (like the QA platform)** — rejected for v0.1: premature; a research engine is batch/CLI-shaped, not request-shaped. Revisit at v0.4 (UI).
3. **Modular Python package (src layout) with protocol-based connectors and pure-function analysis engines** — **chosen.** Testable, swappable data providers, easy to grow into services later.

## 4. Architecture

```
multibagger-engine/
├── src/mbe/
│   ├── models/          # pydantic domain models (frozen, validated)
│   │   ├── company.py   # CompanyInfo, FinancialHistory, PriceHistory
│   │   ├── analysis.py  # FundamentalMetrics, TechnicalState, ValuationResult, RiskAssessment
│   │   └── scoring.py   # Evidence, PillarScore, ScoreCard (investment + multibagger + confidence)
│   ├── data/
│   │   ├── provider.py  # DataProvider Protocol (get_info/get_financials/get_prices)
│   │   ├── yahoo.py     # YahooProvider (yfinance) — v0 source, NSE/BSE/US
│   │   └── cache.py     # on-disk JSON/parquet cache with TTL (polite + fast + offline reruns)
│   ├── analysis/
│   │   ├── fundamentals.py  # growth CAGRs, margins, ROE/ROCE/ROIC, leverage, coverage,
│   │   │                    # FCF, cash conversion, accruals (earnings quality), dilution
│   │   ├── technicals.py    # in-house pandas indicators: SMA/EMA, RSI, MACD, ATR, ADX,
│   │   │                    # Bollinger, Donchian, OBV, CMF, stochastic, 52w structure,
│   │   │                    # relative strength vs benchmark, trend/volatility regime
│   │   ├── valuation.py     # scenario DCF (bear/base/bull), reverse DCF (implied growth),
│   │   │                    # relative valuation vs own history, margin of safety, expected CAGR
│   │   └── risk.py          # rule-based risk flags + composite risk score
│   ├── scoring/
│   │   ├── pillars.py   # Quality, Growth, Financial Strength, Valuation, Momentum → 0–100
│   │   ├── engine.py    # combines pillars → Investment Score, Multibagger Score, Confidence
│   │   └── benchmarks.py# metric → score mapping tables (explicit, documented thresholds)
│   ├── report/
│   │   └── markdown.py  # institutional-style report (all brief sections) + screener table
│   ├── pipeline.py      # orchestrates: fetch → analyze → score → report for ticker/universe
│   ├── universe.py      # curated starter universes (india-largecap, india-midsmall, us-tech)
│   └── cli.py           # `mbe analyze TICKER`, `mbe screen UNIVERSE`, `mbe indicators TICKER`
├── tests/               # pytest; synthetic fixtures (no network); marked network tests
├── reports/             # generated output (gitignored)
├── data/cache/          # provider cache (gitignored)
└── docs/                # this spec, plans, CHANGELOG
```

### Data flow
`ticker → DataProvider (cached) → {FundamentalMetrics, TechnicalState, ValuationResult, RiskAssessment} → ScoringEngine → ScoreCard (+Evidence) → Report`

Each analysis engine is a **pure function of its inputs** (dataframes/models in,
model out) — deterministic and unit-testable without network.

## 5. Key design decisions

- **Python 3.12 via uv** (pandas-ecosystem stability; system 3.14 too fresh for some wheels).
- **Deps:** pandas, numpy, yfinance, pydantic v2, typer, rich, jinja2 (reports), pytest.
- **Indicators in-house** (pure pandas): no TA-Lib binary dependency; every formula unit-tested against known values.
- **Connector protocol**: `DataProvider` is a `Protocol`; Yahoo is the first implementation. NSE/Screener/filings providers can be added without touching engines (brief: "modular connector architecture").
- **Scoring is table-driven**: thresholds live in `benchmarks.py` as data (e.g. ROCE ≥ 25 → 90pts, 20→75, 15→60 …) so they're auditable and tunable — a prerequisite for v0.2 backtest-driven calibration.
- **Multibagger Score ≠ Investment Score.** Investment Score weights quality/valuation/strength for risk-adjusted return. Multibagger Score additionally rewards: small market cap (runway), high reinvestment at high incremental ROIC, revenue acceleration, low institutional discovery (float/coverage proxy), and long reinvestment runway — while **hard-gating** on solvency and earnings-quality red flags (no hype).
- **Confidence Score** = f(fields available / fields expected, years of financial history, price history length). Reported per pillar and overall.
- **Governance data gap acknowledged:** Yahoo lacks promoter pledging / detailed Indian shareholding. These fields are modeled as `None` → surfaced in the report as "data unavailable" and lower confidence. Filled by a future NSE/BSE provider (v0.3).
- **Error handling:** provider failures raise typed errors; pipeline degrades gracefully per-ticker in screening (a bad ticker is reported as failed, never crashes the batch); analysis engines never throw on missing fields — they emit `None` metrics + completeness accounting.

## 6. Testing strategy

- Unit tests per engine with synthetic fixtures (hand-computed expected values for CAGR, RSI, DCF, scores).
- Golden tests: known input → full ScoreCard snapshot.
- Integration test hitting Yahoo, marked `@pytest.mark.network`, excluded from default run.
- TDD for all engine code.

## 7. Success criteria for v0.1

1. `mbe analyze RELIANCE.NS` produces a full markdown research report with scores, evidence, confidence, valuation scenarios, entry/risk framing.
2. `mbe screen india-midsmall` ranks a starter universe by Multibagger Score with a summary table.
3. All unit tests pass offline; formulas verified against hand-computed values.
4. Any pillar score can be traced to its evidence items and thresholds.
