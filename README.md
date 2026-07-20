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
uv run python scripts/build_site.py     # build the weekly picks site -> site/
uv run pytest                           # offline test suite
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

## Hosted weekly picks (v0.10)

Every Monday, GitHub Actions builds a public read-only page of the NIFTY
Smallcap 250 multibagger ranking — the lab (`mbe serve`, CLI, backtests)
stays local; the site is only its published output. As of v0.12 the site
wears a dual-theme trading-platform UI: Zerodha-Kite-inspired dark by
default, Groww-inspired light behind a persistent ☀/☾ toggle.

- **What the page shows** — the top-25 multibagger/investment ranking,
  week-over-week entries/exits, sector-momentum context, 3-5 recent
  headlines per pick, government-policy (PIB) items mapped to the top
  sectors, and delayed (~15 min) quotes.
- **Architecture** — a GitHub Actions job runs the weekly build every
  Monday pre-open IST and commits the rebuilt `site/` back to the repo;
  Vercel's git integration auto-deploys on that push (no CLI, no token).
  Delayed quotes are served by a single stdlib-only Vercel serverless
  function scoped to the published tickers. If Yahoo ever rate-limits
  GitHub's runners outright (the degraded-build guard will fail the job
  loudly), the fallback is a scheduled local run of the identical
  `scripts/build_site.py` followed by `git push` — same output, different
  trigger.
- **Honesty carried over from the reports** — descriptive layers (sector
  momentum, theme tags, news, policy) are shown, never scored; a build
  that can't analyze at least 100 of the 250 names refuses to publish
  rather than ship a degraded ranking; every page carries the same
  model-validation footer as the research reports.

## Live search-any-stock (v0.11)

Type any ticker into the search box on the hosted page and get the full
live research report — not just the weekly top-25, any name Yahoo covers.

- **What it does** — a plain GET form on the hosted index posts a ticker to
  `/api/analyze`, which runs the same `analyze_ticker()` pipeline as the CLI
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

## Roadmap

- **v0.3** — macro dashboard, government-policy/PLI mapping, news & sentiment,
  filings ingestion (annual reports, con-calls), promoter pledging via NSE data;
  benchmark-table recalibration fed by accumulated backtest evidence.
- **v0.4** — web UI, scheduling, portfolio construction, continuous-improvement loop.

## Known limitations (v0.1)

- Yahoo Finance only: ~5 years of statements, no promoter pledging/FII-DII
  detail, occasional stale `info` fields.
- DCF conservatism understates fair value for high-multiple quality names.
- No macro/policy/sentiment signal yet (sections are stubbed in the report).

## Disclaimer

Research tooling, not investment advice. Model outputs carry stated assumptions
and incomplete data; verify independently before any investment decision.
