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

## Addendum 4: replication — the signal weakens out-of-sample

| Test (multibagger score) | Sample | Mean IC | Detail |
|---|---|---|---|
| 2y horizon | primary 80 (S&P600) | +0.160 | 6/6 cutoffs positive |
| 3y horizon | primary 80 | +0.218 | 5/5 positive (overlapping windows — not independent) |
| **2y horizon** | **disjoint replication 80** | **+0.044** | one -0.25 cutoff; 2021/22 positive in both samples |

**Synthesis (all 2y evidence pooled, 12 cutoff-samples): mean IC ~ +0.10,
p ~ 0.05 before adjusting for the fact that both samples share the same
6 calendar windows — effectively ~6 independent regime observations, so the
true significance is weaker.**

Disciplined conclusion:
1. There is a **suggestive positive tendency** for the multibagger score on
   US small caps at multi-year horizons, strongest in 2021-2022 windows —
   and it is **not yet robust**: the primary sample's +0.16 was partly
   winner's luck (classic regression to the mean on replication).
2. The horizon gradient (mega caps ~0 -> small caps 1y +0.10/2y pooled +0.10)
   remains thesis-coherent, but claims stay at "suggestive".
3. **No recalibration, no weight changes.** Evidence base needed before any:
   delisting-inclusive constituent history (kills survivorship bias),
   Indian small-cap replication (needs an Indian filings provider), and
   more independent time windows (older cutoffs — EDGAR supports ~2010+).

This file is the permanent record: every claim the engine makes about its own
predictive power must cite it or supersede it with better evidence.

## Addendum 5 — FINAL SYNTHESIS: the decade-long matrix (null result)

Multibagger score, 2y horizon, 12 annual cutoffs 2012-2023, two disjoint
80-name S&P 600 samples, EDGAR fundamentals, full-depth prices:

| Sample | Mean IC | Positive cutoffs | 2012-2018 | 2021-22 |
|---|---|---|---|---|
| primary | +0.098 | 9/12 | mixed | +0.35 / +0.30 |
| replication | **-0.028** | 4/12 | nearly all negative | +0.21 / +0.25 |

**Conclusion: no demonstrated persistent edge.** The two samples disagree
across most of the decade; they agree only in the 2021-2022 windows — a
regime effect (post-COVID quality repricing), not a durable stock-selection
signal. The initial +0.16 (Addendum 3) was sample-specific luck, caught by
replication + window extension. Additional caveat: at older cutoffs,
current-constituent samples are increasingly survivorship-tilted (n drops
from ~75 to ~44), which should *flatter* quality scores — making the null
even firmer.

**Actions taken:**
1. Every research report now carries a "Model validation status" section
   stating the null result and linking this record (wired into the template,
   test-enforced).
2. Benchmark tables remain documented priors — explicitly unvalidated.

**Where signal could still hide (next research directions, in value order):**
1. **Pillar-level attribution** — test each pillar score separately; a null
   composite can hide a working component cancelled by a broken one.
2. **Indian small/mid caps** — different market efficiency regime; blocked on
   an Indian fundamentals source (BSE annual-report PDF extraction pipeline
   is the identified path; NSE API bot-walled; structured BSE endpoints not
   publicly addressable).
3. Delisting-inclusive universes; quarterly rebalance; interaction filters
   (e.g. quality only within uptrends).

## Addendum 6 — pillar attribution (single-pass, 9 scores x 2 samples x 12 cutoffs, 2y)

| Component | Primary IC | Replication IC | Replicates? |
|---|---|---|---|
| **Size Runway** | **+0.277 (11/12)** | **+0.221 (10/12)** | **yes — but see caveat** |
| Valuation | +0.102 | -0.006 | no |
| Quality | +0.084 | -0.094 | no |
| Financial Strength | +0.074 | -0.070 | no |
| Growth | +0.058 | -0.012 | no |
| Reinvestment | +0.064 | -0.019 | no |
| Momentum | -0.074 | -0.064 | negative in both |
| multibagger (composite) | +0.098 | -0.028 | no |
| investment (composite) | +0.110 | -0.074 | no |

Readings:

1. **Size Runway is the only replicating signal — and it is exactly the one
   current-constituent survivorship inflates most.** A stock that was tiny in
   2012 and is still an S&P 600 member today survived and grew by construction;
   small losers were delisted and are invisible. Direction plausible (size
   effect within small caps), magnitude untrustworthy. A delisting-inclusive
   constituent history is now the single most valuable data acquisition for
   this engine.
2. **No fundamental pillar (Quality/Growth/Strength/Valuation) carries
   replicable 2y signal** in these samples — the composite null decomposes
   into component nulls, not into cancellation.
3. **Momentum is negative in BOTH samples at 2y** — coherent with the
   literature (momentum works at 3-12 months and mean-reverts at 2-5 years);
   annual-sampled 1y momentum was ~0. If momentum is ever used for entry
   timing, its horizon must be far shorter than the holding thesis.

Attribution is stored per-score in the DuckDB backtests table
(`attribution_run: true`) and reproducible via `scripts/attribution_backtest.py`.

## Addendum 7 — survivorship sensitivity: the size signal is bias-compatible

Ghost-injection grid (synthetic delisted names at the top size tier, forward
return swept over plausible removal outcomes), applied to the Size Runway
panels from Addendum 6:

| Assumption (delisted share, ghost return) | Sample1 IC | Sample2 IC |
|---|---|---|
| observed (no ghosts) | +0.277 | +0.221 |
| mild (5%, -20%) | +0.130 | +0.079 |
| **central (10%, -20%)** | **+0.024** | **-0.023** |
| adverse (15%, -40%) | -0.154 | -0.195 |

S&P 600 turnover runs ~6-10%/yr (=> ~12-20% over a 2y window); removal
outcomes blend bankruptcies/deletions (very negative) with buyouts (positive
premium), plausibly netting -10% to -30%. At those central assumptions the
observed size IC is **indistinguishable from zero**.

**Verdict: the last surviving signal is fully compatible with survivorship
bias. The complete v0.1 scoring system has no demonstrated predictive edge in
US samples, 2012-2025, at 1-3y horizons.** This is now a clean,
rigorously-established null — the correct foundation for what comes next.

(Process note: the first grid run produced ICs that *rose* under adverse
assumptions — a rank-placement bug (ghosts jittered below the top tier
instead of above). Caught because the result contradicted arithmetic
intuition; fixed and rerun. Surprising results get audited before recording.)

## Strategic pivot recorded

NSE's financial-results API + archives XBRL are openly accessible (no bot
wall on these endpoints): 20 years of annual Ind-AS filings per company with
exact broadcast timestamps — full P&L and cash-flow line items confirmed for
RELIANCE. **This is the Indian fundamentals provider path** (better than the
BSE PDF pipeline), enabling the home-market replication the thesis actually
targets. Queued as the next build.
