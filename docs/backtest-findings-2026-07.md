# Backtest findings — July 2026 (first calibration evidence)

Setup: NIFTY Midcap 150 (first 60 constituents), point-in-time cutoffs
2024-07-15 and 2025-07-15, 365-day forward returns, n = 54/57 per cutoff
(9 ticker-cutoffs skipped for insufficient point-in-time data).

| Score | IC @2024-07 | IC @2025-07 | Mean IC | Spread @2024 | Spread @2025 |
|---|---|---|---|---|---|
| multibagger | 0.007 | 0.024 | **0.016** | -7.6% | +0.7% |
| investment | 0.038 | -0.021 | **0.009** | -1.1% | +0.7% |
| momentum | -0.138 | +0.083 | **-0.027** | -20.0% | +13.6% |

## Honest interpretation

1. **No demonstrated 1-year edge.** All mean ICs are indistinguishable from zero
   at this sample size (2 cutoffs, ~55 names). This is the truthful baseline,
   not a failure of the harness — it ran exactly as designed.
2. **The momentum sign-flip is informative.** Momentum crashed in the 2024→2025
   window (the midcap correction: top momentum quintile -20% vs bottom) and
   worked in 2025→2026 (+13.6%). Classic factor-crash signature; single-factor
   momentum is regime-dependent, which supports keeping its weight moderate
   (currently 14% of Investment Score) rather than increasing it.
3. **Structural caveats bound what these numbers can say:** multibagger theses
   play out over 3-5+ years but Yahoo's ~5-year statement depth only allows
   1-2 year forward windows; the 2024 cutoff had only ~3 statement years, so
   growth CAGRs were largely absent from scoring; survivorship bias (today's
   index list) flatters everything.

## Decisions taken

- **No recalibration on this evidence.** Two cutoffs is curve-fitting territory.
  Benchmark tables stay as documented priors until the evidence base grows.
- The harness + DuckDB store now accumulate every run; each future snapshot and
  backtest extends the evidence base for a properly-powered calibration.
- Priority raised for a deeper fundamentals provider (10+ years of statements)
  — it directly multiplies usable cutoffs and enables the 3-5y horizons the
  multibagger thesis actually claims.

## Addendum: powered momentum backtest (8 annual cutoffs, 2018-2025)

Momentum score, 60 NIFTY Midcap 150 names, 365-day forward returns,
n = 45-57 per cutoff (72 ticker-cutoffs skipped: young listings / short windows).

| Cutoff | IC | Top-bottom spread |
|---|---|---|
| 2018-07 | +0.120 | +14.2% |
| 2019-07 | -0.065 | -15.3% |
| 2020-07 | -0.051 | +56.9% |
| 2021-07 | +0.066 | -10.6% |
| 2022-07 | -0.299 | -12.7% |
| 2023-07 | +0.203 | +77.0% |
| 2024-07 | -0.138 | -20.0% |
| **Mean** | **-0.010** | — |

Interpretation (with 2025-07 included, mean IC -0.010):

1. **No stable 1-year momentum edge in Indian midcaps at annual rebalance.**
   IC whipsaws between -0.30 and +0.20 across regimes — momentum decays over
   months, so annual sampling aliases the signal badly.
2. This is consistent with the decision to keep Momentum at a moderate 14%
   of the Investment Score rather than raising it.
3. The harness is now demonstrably capable of powered multi-cutoff tests —
   the constraint for testing the core quality/growth thesis remains
   statement depth, not tooling.

## Addendum 2: deep US backtests via SEC EDGAR (exact filing-date gating)

First backtests with real point-in-time discipline from XBRL filing dates
(no +90d heuristic). Universe: us-largecap60, n = 56-58 per cutoff.

| Test | Cutoffs | Mean IC | Range |
|---|---|---|---|
| multibagger, 1y horizon | 7 (2018-2024) | +0.004 | -0.15 .. +0.19 |
| investment, 1y horizon | 7 (2018-2024) | -0.025 | — |
| multibagger, 2y horizon | 6 (2018-2023) | -0.001 | -0.26 .. +0.24 |

Interpretation:

1. **Still no demonstrated edge — but this test is structurally biased against
   the thesis.** Every name in us-largecap60 is a large cap, so the Size-Runway
   pillar simply shorts the biggest names — which led the 2023-25 mega-cap/AI
   rally (the 2023 cutoff shows IC -0.26, top-bottom spread -47%). A multibagger
   score tested on mega caps mostly measures the size tilt against a
   mega-cap-led regime. The **correct test universe is US small/mid caps**, and
   for India the small/microcap indices — queued as the next harness run.
2. Quintile buckets of ~11 names make spreads extremely noisy (-73% in the
   2019+2y window spans the COVID crash); IC is the more stable statistic.
3. **Infrastructure conclusion:** EDGAR gives 15-20 statement years per company
   with exact first-public dates — cutoffs back to ~2010 are now possible for
   US universes. Statement depth is no longer the binding constraint for US
   tests; universe breadth (small/mid cap lists) is.

## Addendum 3: US small caps — first thesis-consistent signal

Universe: us-smallcap-sample (80 mechanically-sampled current S&P 600 members),
EDGAR fundamentals (exact filing dates), n = 57-76 per cutoff.

| Test | Cutoffs | Mean IC | Cutoffs positive | t-stat |
|---|---|---|---|---|
| multibagger, 1y | 7 (2018-2024) | **+0.095** | 5/7 | ~1.8 (p~0.13) |
| **multibagger, 2y** | 6 (2018-2023) | **+0.160** | **6/6** | **~2.9 (p~0.03)** |
| investment, 1y | 7 (2018-2024) | +0.067 | — | — |

The full picture across all backtests now reads:

| Configuration | Mean IC |
|---|---|
| multibagger · mega caps · 1-2y | ~0.00 |
| momentum · Indian midcaps · 1y | -0.01 |
| multibagger · small caps · 1y | +0.10 |
| multibagger · small caps · 2y | +0.16 |

**Why this is credible:** the gradient matches the pre-registered thesis, not a
data-mined grid point — the score was designed for small caps (size-runway,
reinvestment pillars) and multi-year horizons, and that is precisely where the
signal concentrates. The 1y negative years are regime-coherent (2020 junk
rally, 2024 rate-cut rotation). At 2y, every cutoff including the COVID window
is positive.

**Why restraint still applies:**
1. Survivorship bias: current constituents only — delisted losers are absent.
   This likely flatters quality scores (survivors skew healthy).
2. One 80-name sample; several configurations were run this session (multiple
   testing inflates the best result).
3. Not yet replicated on Indian small caps (blocked on Yahoo's 5y statement
   depth; an Indian filings provider unlocks it).

**Decision: still no benchmark-table recalibration.** Next evidence steps, in
order: (a) rerun on a second disjoint S&P 600 sample (cheap, cached universe),
(b) 3y horizon, (c) an Indian fundamentals source for the home-market test.
