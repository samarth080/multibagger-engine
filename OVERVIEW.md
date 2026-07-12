# Multibagger Engine — What We've Built

*A plain-language tour of the autonomous equity-research engine, as of 2026-07-12.*

An autonomous equity-research and multibagger-discovery engine, India-first
(NSE/BSE) and US-capable. It ingests real market and filing data, runs a full
analytical stack (fundamentals, technicals, valuation, risk), turns that into
**explainable, confidence-scored** investment scores, writes institutional-style
research reports, serves them in a local web terminal — and, crucially, it
**backtests its own scores honestly** and reports when it has no edge.

At a glance: **42 commits · ~3,600 lines of source · 100 tests (all green) ·
3 live data sources · spec-first + test-driven throughout.**

---

## 1. The one thing that makes this different

Most "stock AI" projects stop at producing a confident-looking score. This one
was built to **hold its own scores to account**. It has a point-in-time
backtesting harness that replays history exactly as an investor would have seen
it (no lookahead), measures whether the scores actually predicted future
returns, and — when they didn't — **says so, in the reports themselves**.

The headline research finding so far is a *null result*: across US samples
2012–2025, the composite scores show **no demonstrated persistent predictive
edge**. That is not a failure of the software — it is the software working. It
caught one of its own false positives (an exciting +0.16 signal that evaporated
on a fresh sample) before it could ever contaminate a recommendation. Every
report the engine generates now carries a "Model validation status" section
stating this plainly. That intellectual honesty is the product.

---

## 2. The pipeline, end to end

```text
ticker ─▶ Data provider (cached) ─▶ 4 analysis engines ─▶ Scoring engine ─▶ Report
          Yahoo / EDGAR / NSE        fundamentals            5 pillars        markdown
                                     technicals              + multibagger    + web page
                                     valuation               + confidence
                                     risk                    + hard gates
```

Feed it a ticker (e.g. `RELIANCE.NS`, `AAPL`), and it:

1. **Fetches** company info, 5–20 years of financial statements, and price
   history — through a swappable provider, cached to disk.
2. **Analyzes** on four independent engines (each a pure, tested function).
3. **Scores** the results into explainable pillar scores, a composite
   Investment Score, a Multibagger Score, and a Confidence level.
4. **Writes** a full research report with an evidence trail for every score.

---

## 3. The analysis engines (`src/mbe/analysis/`)

Each is a pure function — data in, metrics out — with hand-computed test anchors.
Missing data is **surfaced as "unavailable," never guessed**; it lowers
confidence instead of inventing a number.

| Engine | What it computes |
|---|---|
| **Fundamentals** | Revenue/profit/FCF growth (CAGRs), margins and margin trend, ROE / ROCE / ROIC, leverage, interest coverage, cash conversion, **accruals ratio** (earnings quality), reinvestment rate, dilution |
| **Technicals** | In-house pandas indicators (RSI, MACD, ATR, ADX, Bollinger, stochastic, OBV, CMF), a Minervini-style trend-template, 52-week structure, relative strength vs the index, volatility regime, traded-value liquidity — no TA-Lib dependency, every formula unit-tested |
| **Valuation** | Two-stage scenario DCF (bear/base/bull), **reverse DCF** (the growth the market is pricing in), an owner-earnings floor for capex-heavy compounders, plus PEG / EV-EBITDA / P-S / FCF-yield multiples |
| **Risk** | Nine rule families (solvency, coverage, earnings quality, dilution, valuation heat, liquidity, volatility, governance gaps) → a composite risk score and a probability-of-permanent-loss bucket |

---

## 4. The scoring engine (`src/mbe/scoring/`) — explainability by construction

The brief demanded that *every conclusion explain WHY*. That is enforced
structurally:

- **Benchmark tables are data, not code** (`benchmarks.py`). A ROCE of 24%
  scores 75 because the table says `≥20% → 75`. Every threshold is auditable
  and — importantly — recalibratable once evidence justifies it.
- **Five pillars** — Quality, Growth, Financial Strength, Valuation, Momentum —
  each emits an **Evidence row per metric** (value, benchmark applied, points,
  weight, rationale). Missing metrics are dropped and their weight
  renormalized, which lowers that pillar's confidence.
- **Two composite scores.** The *Investment Score* weights the pillars for
  risk-adjusted return (with a haircut for risk). The *Multibagger Score* adds
  Size-Runway and Reinvestment pillars — rewarding small, under-the-radar
  compounders — but **hard-gates** on broken economics (bad accruals, weak
  coverage, heavy dilution, cash burn) so it can never celebrate hype.
- **A Confidence Score** on everything, derived from data completeness,
  statement history length, and price-history depth.

---

## 5. Data layer (`src/mbe/data/`) — three live sources behind one interface

Everything speaks one `DataProvider` protocol, so sources are swappable and
composable. All responses are cached to disk with sensible TTLs.

| Source | Role | Notable strength |
|---|---|---|
| **Yahoo Finance** | prices, company info, quick financials | fast, global, ~5y statements |
| **SEC EDGAR** (`edgar.py`) | US statements from XBRL companyfacts | **15–20 years**, exact filing dates, original-filing values only (restatements ignored to prevent lookahead) |
| **NSE XBRL** (`nse_xbrl.py`) | Indian statements from NSE results filings | **exact broadcast dates**, consolidated-preferred, verified to the crore against Reliance FY24 |

A **CompositeProvider** mixes them (e.g. EDGAR statements + Yahoo prices).
**Universes** are pulled live too: NSE index constituents (NIFTY 50/500/Midcap
150/Smallcap 250) and US S&P 600/400 samples from Wikipedia — plus deterministic
"disjoint replication" sampling for honest out-of-sample tests.

---

## 6. The backtesting harness (`src/mbe/backtest/`) — the scientific core

This is what elevates the project from a scorer to a research instrument.

- **Point-in-time discipline** (`pointintime.py`): statements are gated by their
  real first-public date (exact from XBRL, or a fiscal-year-end + 90-day
  heuristic otherwise); prices are truncated at the cutoff; present-day fields
  that have no history (holdings %, trailing P/E, beta) are nulled so they can't
  leak. **No lookahead, by construction and by test.**
- **The measurement** (`harness.py`): for each historical cutoff it ranks the
  universe by a chosen score and correlates that against realized forward
  returns — reporting the **Spearman information coefficient (IC)**, top-vs-bottom
  quantile spread, and hit rate. A single analysis pass can score every pillar
  at once (attribution) and expose the raw panel (sensitivity analysis).
- **Honest caveats in every report**: survivorship bias, sample size, no
  transaction costs. It is a validation instrument, not a strategy simulator.

### What the backtests actually found (`docs/backtest-findings-2026-07.md`)

1. **Mega caps & annual momentum: no edge** (IC ≈ 0).
2. **US small caps looked promising** — 2-year IC +0.16, then...
3. **...a disjoint replication sample cut it to +0.04.** Winner's curse, caught.
4. **Pillar attribution**: only *Size Runway* replicated — but that is exactly
   the pillar most inflated by survivorship bias.
5. **Survivorship sensitivity analysis**: injecting plausible "ghost" delisted
   names collapses even the size signal to ≈ 0. **Clean, rigorous null.**

6. **First India home-market backtest** (NSE data, 50 NIFTY smallcaps): mean
   2-year IC **+0.232**, all three cutoffs positive — the strongest
   home-market-relevant number yet. But it is **preliminary, not proven**: only
   three cutoffs, all inside the post-COVID small-cap bull run, on a small
   survivorship-biased sample — the *exact* shape of the US result that later
   evaporated on replication. Recorded as a promising lead, explicitly
   unvalidated, pending a disjoint sample and pre-2019 (non-bull) cutoffs.

---

## 7. Reports, storage, and the web terminal

- **Research reports** (`report/markdown.py`): institutional-style markdown —
  executive summary, thesis, financials table, technicals, valuation scenarios,
  risk table, bull/base/bear, entry & exit framework, position sizing, a full
  score-evidence appendix, data gaps, and the model-validation disclosure.
- **Persistent store** (`storage.py`): a DuckDB database records every run, so
  scores become a queryable time series and backtest results accumulate.
- **Local web terminal** (`web/app.py`, `mbe serve`): a server-rendered
  dashboard on `http://127.0.0.1:8000` — stored rankings with score meters,
  in-browser reports for any ticker, per-ticker history, and the backtest
  evidence table. Dark "research terminal" aesthetic, no build step.

---

## 8. Using it

```bash
uv sync
uv run mbe analyze RELIANCE.NS                 # full report → reports/
uv run mbe analyze AAPL --fundamentals edgar   # 20y US statements
uv run mbe screen nifty-midcap150              # rank an NSE index
uv run mbe snapshot india-midsmall             # screen + persist to DuckDB
uv run mbe history MCX.NS                       # score time series
uv run mbe backtest us-smallcap-sample --fundamentals edgar   # does it predict?
uv run mbe serve                                # web terminal at :8000
uv run pytest                                   # 100 tests
```

---

## 9. How it was built

Every increment followed the same discipline: **write a spec → write a plan →
test-driven implementation (red/green/commit) → verify against live data →
record findings honestly.** Specs and plans live in `docs/superpowers/`, the
research record in `docs/backtest-findings-2026-07.md`, and the version history
in `CHANGELOG.md` (v0.1 → v0.3.1, with the NSE milestone landing as v0.4).

---

## 10. Where it's headed

The engine is instructed to keep improving autonomously. The queued priorities,
in value order:

1. **Indian home-market backtest** (running now) — the first evidence on the
   Priority-1 market, using exact NSE broadcast-date discipline.
2. **Deepen NSE history** to ~20 years (a pre-2019 taxonomy parser).
3. **Delisting-inclusive universes** to finally settle the survivorship question.
4. **Pillar-level and interaction strategies** (e.g. quality only within uptrends).
5. Then the v0.3b/v0.4 horizon: macro & government-policy signals, news &
   sentiment, scheduling, and portfolio construction.

---

*This engine is research tooling, not investment advice. Its scores are model
artifacts with stated assumptions and — as its own backtests show — no proven
predictive edge yet. That honesty is the point.*
