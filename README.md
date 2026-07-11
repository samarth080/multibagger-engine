# Multibagger Engine

Autonomous equity research & multibagger discovery engine. India-first (NSE/BSE),
US-capable. Evidence-driven: every score is traceable to a metric, a benchmark
threshold, and a rationale; every analysis carries a confidence level derived
from data completeness.

## Quickstart

```bash
uv sync
uv run mbe analyze RELIANCE.NS          # full research report -> reports/
uv run mbe screen india-midsmall       # rank a universe by Multibagger Score
uv run mbe universes                    # list available universes
uv run pytest                           # 51 offline tests
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

## Roadmap

- **v0.2** — full NSE/BSE universe ingestion, DuckDB store, backtesting harness
  to calibrate benchmark tables against historical multibagger outcomes.
- **v0.3** — macro dashboard, government-policy/PLI mapping, news & sentiment,
  filings ingestion (annual reports, con-calls), promoter pledging via NSE data.
- **v0.4** — web UI, scheduling, portfolio construction, continuous-improvement loop.

## Known limitations (v0.1)

- Yahoo Finance only: ~5 years of statements, no promoter pledging/FII-DII
  detail, occasional stale `info` fields.
- DCF conservatism understates fair value for high-multiple quality names.
- No macro/policy/sentiment signal yet (sections are stubbed in the report).

## Disclaimer

Research tooling, not investment advice. Model outputs carry stated assumptions
and incomplete data; verify independently before any investment decision.
