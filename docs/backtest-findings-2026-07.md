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

## Addendum 8 — FIRST INDIA HOME-MARKET BACKTEST (NSE XBRL, exact broadcast-date PIT)

Multibagger score, 50 NIFTY Smallcap 250 names, NSE Ind-AS fundamentals with
exact broadcast-date gating, 2y horizon:

| Cutoff | IC | Top-bottom spread | n |
|---|---|---|---|
| 2021-07 | +0.082 | -4.9% | 28 |
| 2022-07 | +0.394 | +53.0% | 30 |
| 2023-07 | +0.221 | +84.9% | 35 |
| **Mean** | **+0.232** | — | — |

This is the **strongest home-market-relevant number to date** and it is
directionally exciting — but discipline holds: **it is preliminary, not
proven.** The exact same red flags that killed the US +0.16 apply:

1. **Single favorable regime.** 2021-2023 cutoffs at a 2y horizon span the
   post-COVID Indian small-cap bull run. The US samples *also* looked great in
   2021-22 and then collapsed on replication.
2. **Small, survivorship-biased sample.** n=28-35 per cutoff; nifty-smallcap250
   is today's membership — 2021 names that blew up and were dropped are absent.
   57 ticker-cutoffs skipped (NSE XBRL coverage starts ~FY2019, so early cutoffs
   lack statement history).
3. **Only 3 cutoffs, all overlapping regime.** No pre-2019 windows yet.

**Required before any claim of an Indian edge (in order):**
1. Disjoint replication sample (second 50 NIFTY smallcap names).
2. Pre-2019 NSE taxonomy parser -> cutoffs spanning 2010-2020 (non-bull regimes).
3. Delisting-inclusive Indian universe.

**Status: promising lead, explicitly unvalidated.** No recalibration. The US
experience is the cautionary precedent: this is precisely the shape of result
that later evaporated.

## Addendum 9 — Phase 2 / P2.1: franchise-durability score is a VALIDATED NULL predictor

Ablation (multi-score harness, 2y horizon, franchise vs base multibagger vs
Quality vs investment), pre-registered decision rule: franchise becomes a
first-class ranking score only if IC ≥ base in the majority of samples.

| Sample | multibagger IC | franchise IC | franchise ≥ base? |
|---|---|---|---|
| us-smallcap-sample (12 cutoffs) | +0.098 | +0.092 | no |
| us-smallcap-sample2 (12 cutoffs) | -0.025 | **-0.094** | no |
| nifty-smallcap250 (3 cutoffs) | +0.221 | **-0.114** | no |

**Verdict: 0/3. Franchise-durability does NOT predict forward returns better
than the existing score — it is materially worse on the replication and India
panels.** Honoring the rule: `franchise_score` is **demoted** — it is NOT used
to rank or screen picks. It remains only (a) a labelled research quantity in the
backtest store and (b) a *descriptive* business classification in reports.

This is the discipline the directive demands working as intended: a plausible,
investor-intuitive signal (durable high-ROCE franchises) was built, tested, and
found to carry no selection alpha in these samples — and is demoted rather than
shipped on narrative appeal.

**What is retained, and on what basis:** the *thesis + self-critique* layer
makes no return-prediction claim. Its value proposition is (1) research quality
— falsifiable assumptions with track-record probabilities, explicit falsifiers,
devil's-advocate disconfirmers — and (2) **risk avoidance** via the critique
veto. Claim (2) is tested next (veto-avoidance study); if the veto does not
steer away from worse outcomes it too will be demoted.

## Addendum 10 — Self-critique VETO: does not avoid worse outcomes (null / mild negative)

Veto-avoidance study: analyze every name point-in-time, split by whether the
self-critique vetoed, compare 2y forward returns. A useful risk filter should
give vetoed names LOWER mean and HIGHER permanent-loss rate.

| Sample | Vetoed mean / loss-rate | Not-vetoed mean / loss-rate |
|---|---|---|
| us-smallcap-sample | +25.8% / 16% | +25.3% / 10% |
| us-smallcap-sample2 | +38.5% / 13% | +29.7% / 11% |
| nifty-smallcap250 | +94.2% / 8% | +83.6% / 2% |
| **Pooled (n=440 vs 1052)** | **+38.1% / 14%** | **+29.9% / 10%** |

**Verdict: the veto does NOT avoid worse outcomes.** Vetoed names had *higher*
mean returns in every sample and a *higher* permanent-loss rate — the critique
is selecting higher-volatility names (fatter both tails), not steering away
from loss. Vetoing them would have *reduced* returns in these bull-heavy
small-cap samples: the levered/deteriorating names the veto flags were exactly
the high-beta winners of the window.

## P2.1 disposition — honest accounting

Both quantitative hypotheses of P2.1 are **falsified in these samples**:
franchise durability does not predict returns (Addendum 9); the critique veto
does not avoid losses (Addendum 10). Per the directive's rule, neither is
presented as an investment edge:

- `franchise_score`: descriptive classification only; never ranks or screens.
- Critique `veto`: reframed as *transparency* — it surfaces disconfirming
  evidence for the reader and is explicitly labelled as NOT a validated risk
  filter. It no longer masquerades as a decision that improves outcomes.

**What is retained, and why:** the thesis layer — falsifiable assumptions with
track-record probabilities, explicit falsifiers, bull/base/bear business
trajectory, devil's-advocate disconfirmers — is kept as a **research-quality /
reasoning-transparency** upgrade (an explicitly permitted justification in the
directive), because it makes the platform reason and communicate about a
*business* rather than a ticker. It is labelled as unvalidated-for-returns
everywhere it appears. Keep the reasoning scaffolding; drop every unearned
predictive claim.

## Addendum 11 — P2.2 retro-calibration: confidences are informative, and the FIRST VALIDATED IMPROVEMENT

The prediction ledger emitted and resolved **2,770 predictions** across real
history (US small-caps 2016-2023, India 2021-2024), both emission and
resolution strictly point-in-time.

**Result 1 — the platform's confidences carry real information.**
Brier 0.132 overall (0.25 = coin-flip). The 0.8-1.0 bucket (n=1141) is almost
perfectly calibrated (stated 93%, observed 92%).

**Result 2 — a systematic, correctable bias.** Observed frequencies exceed
stated confidence in the middle buckets (+15pp at n=895 and n=237): business
characteristics are *stickier* than naive year-frequencies imply
(autocorrelation — the current state adds information beyond the base rate).

**Result 3 — the correction VALIDATES OUT-OF-SAMPLE.** A bucketwise
calibration map learned on US resolutions only (n=2086), applied to India
(n=684, disjoint market): **Brier 0.170 -> 0.153 (-10.2%)**. This is the
project's first data-derived improvement that survived honest validation, per
the pre-registered rule (gap > 15pp in populated buckets -> earn a correction).

**Shipped accordingly:** `mbe analyze` now emits calibrated confidences (raw
value kept for provenance) once the ledger holds >= 200 resolutions; the web
terminal home shows the live reliability table; the ledger keeps accumulating,
so the map is re-learned from evidence as outcomes arrive.

Caveats: retro window overlaps the bull-heavy 2016-2024 period; assumption
persistence is regime-dependent; the classification-stability prior (0.7) now
has a measured base rate (85%) that the map corrects automatically.

## Addendum 12 — P2.3 stewardship ablation: demoted (0/3), with a nuance

Pre-registered rule, same as Addendum 9. 2y horizon:

| Sample | multibagger IC | stewardship IC |
|---|---|---|
| us-smallcap-sample | +0.098 | +0.076 |
| us-smallcap-sample2 | -0.028 | -0.030 |
| nifty-smallcap250 | +0.232 | +0.218 |

**Verdict: 0/3 — stewardship_score is demoted to descriptive-only** (does not
rank or screen picks). Nuance recorded: unlike the franchise score (which was
anti-signal on India), stewardship *tracks* the base score closely everywhere —
it encodes similar information to the existing quality/strength components, not
incremental information. The report section (dilution record, allocation fit,
Empire Builder / Serial Diluter labels) is retained as risk disclosure and
reasoning transparency, labelled as unvalidated-for-returns like everything else.

## Addendum 13 — India, properly windowed: the first cross-sample-consistent signal

The legacy-parser deepening (FY2013+ statements) enabled 8 cutoffs (2016-2023)
including the non-bull 2016-2019 windows. Multibagger score, 2y horizon, two
disjoint 50-name NIFTY Smallcap 250 samples:

| Sample | 3 cutoffs (2021-23) | 8 cutoffs (2016-23) | Windows positive |
|---|---|---|---|
| india-primary | +0.232 | **+0.100** | 5/8 |
| india-replication | +0.047 | **+0.138** | 6/8 |

Per-window means (both samples averaged): 2016 +0.19, 2017 +0.21, 2018 -0.15,
2019 +0.30, 2020 -0.02, 2021 +0.01, 2022 +0.15, 2023 +0.27 → mean ≈ +0.12,
6/8 windows positive, t ≈ 2.2 (p ≈ 0.07 on 8 independent windows).

**Why this is the strongest evidence yet:** unlike the US (where disjoint
samples *disagreed* across the decade: +0.098 vs -0.028), the two Indian
samples agree in sign and broadly in pattern. The short-window replication
scare (+0.047) resolved upward once non-bull windows were added — the signal
is not purely the post-COVID regime.

**Why claims stay at "suggestive, not proven":**
1. p ≈ 0.07 — short of conventional significance; ~90-93% confidence.
2. Survivorship: current index members only, thinner at old cutoffs (n=19-43).
3. Pre-2019 statements are P&L-only (legacy pages) — early-cutoff scores lean
   on fewer pillars, and that structural change coincides with the windows.
4. Overlapping 2y windows slightly inflate the effective sample.

**Standing verdict:** US small caps ≈ no edge; India small caps ≈ consistent
suggestive edge (~+0.12 IC at 2y) pending survivorship-robust confirmation.
No recalibration on this evidence. Next: delisting-inclusive Indian universe,
all 250 names per cutoff, and 3y horizons.

## Addendum 14 — P2.4 sector-momentum ablation: demoted (1/4), sector-alone consistently positive but weak

Pre-registered rule, same as Addenda 9 and 12: the pillar goes live only if
augmented mean IC >= base mean IC in a strict majority (3+/4 samples), fixed
in the P2.4 spec before results were seen. One identical analysis pass
(`run_backtest_multi`) scored `multibagger` (base), `multibagger_sector`
(+sector at the pre-registered 0.12 weight), and `sector` (sector-alone) per
sample. 2y horizon; US samples = 12 cutoffs 2012-2023 (disjoint S&P600
samples via EDGAR); India samples = 8 cutoffs 2016-2023 (nifty-smallcap250
`[:50]` and `[50:100]` via NSE XBRL).

| Sample | base IC | +sector IC | sector-alone IC |
|---|---|---|---|
| us-smallcap-sample | +0.098 | +0.093 | +0.034 |
| us-smallcap-sample2 | -0.028 | -0.034 | +0.042 |
| india-primary | +0.163 | +0.123 | +0.081 |
| india-replication | +0.104 | +0.111 | +0.319 (>= base) |

**Verdict: +sector >= base in 1/4 samples -> Sector Momentum is DEMOTED to
descriptive-only** (pillar evidence stays on the card; the multibagger score
is untouched) — the same demotion treatment as franchise (Addendum 9) and
stewardship (Addendum 12).

**Honest interpretation:**

1. **Sector-alone IC was positive in all four samples** (+0.034 / +0.042 /
   +0.081 / +0.319) — weak but consistently positive standalone signal, a
   genuinely different pattern from franchise (which was outright anti-signal
   on India). Yet blending it into the composite at the pre-registered 0.12
   weight made the composite slightly *worse* in 3/4 samples — a positive
   standalone signal does not automatically improve a blend it is added to.
2. **The india-replication sector-alone reading (+0.319) is an outlier** on a
   50-name sample; it is the only row that beat base, and it should not be
   read as the pillar "actually working" on India — it did not survive the
   pre-registered majority rule and the same sample's own base score
   (+0.104) is far more stable across the two India cuts than sector-alone is.
3. **Base multibagger reconfirmed cross-sample-consistent positive IC on
   India** in this run (+0.163 primary / +0.104 replication) — consistent
   with Addendum 13's standing verdict, on an independent (later) execution.
4. **Two new caveats now print in every backtest report** as a result of this
   work: present-day sector/industry labels applied to historical cutoffs are
   a mild, disclosed lookahead (no historical taxonomy source exists); and
   survivorship bias hits sector-momentum harder than stock-level signals,
   because hot sectors are disproportionately where today's-absent dead names
   died, which overstates sector IC on today's surviving constituents.

**Shipped accordingly:** `SECTOR_PILLAR_LIVE` stays `False`; the sector table,
industry grouping, curated descriptive-only theme tags, and report/CLI context
are retained as risk/context disclosure, labelled unvalidated-for-returns like
franchise and stewardship before it. No recalibration on this evidence.

---

## Addendum 15 — 3-year scenario forecast: accuracy is measurable, and it reads low

**Run:** 2026-07-31, `us-smallcap-sample` and `us-smallcap-sample2`, first 30
tickers each, cutoffs 2016/2018/2020/2022-07-15, horizon 1095 days, EDGAR
fundamentals, strict point-in-time. Metric is the **mean signed error** of the
forecast's base-case target against the realized price
(`realized / predicted - 1`); positive means the forecast came in too low.
Signed rather than absolute on purpose: the defect this release fixed was
systematic understatement, which an absolute error would have concealed.

| cutoff | sample 1 | sample 2 |
|---|---|---|
| 2016-07-15 | +129.9% | +71.2% |
| 2018-07-15 | +81.7% | +128.5% |
| 2020-07-15 | +68.1% | +133.3% |
| 2022-07-15 | +180.2% | +47.2% |
| **mean** | **+115.0%** | **+95.1%** |

**All 8 cutoffs are positive.** The realized price averaged roughly twice the
base-case target. Cross-sample agreement is strong on *direction* and weak on
magnitude (+115% vs +95%, individual cutoffs ranging +47% to +180%).

**Two prerequisite bugs this run surfaced**, both of which had silently
disabled the measurement rather than failing loudly:

1. `analyze_as_of` built its bundle without `prices`, so `build_forecast` found
   no own-P/E history, produced no anchor, and returned `None` for every
   ticker. Forecast accuracy reported `n/a` while appearing to run.
2. `edgar._annual_facts` read only `units["USD"]`. EDGAR files share counts
   under `units["shares"]`, so `shares_diluted` was empty for **every US
   ticker** — a pre-existing bug that made EPS, and therefore any P/E-anchored
   forecast, structurally impossible on the entire EDGAR path. Also left
   `share_count_cagr_3y` unmeasurable for US names.

**Honest interpretation:**

1. **The forecast is not over-optimistic.** That was the live concern after the
   base-case re-rating cap was added (BLS was anchoring its base case at 45.0x
   against a traded 14.2x). 8/8 positive cutoffs across two independent samples
   say the residual bias runs the other way.
2. **Whether it is *too* conservative cannot be settled on this evidence.**
   Both universes are today's constituents, so dead names are absent and
   realized returns are flattered; and 2016-2025 was among the strongest US
   smallcap stretches on record. "The model did not forecast a bull market" is
   not a defect worth correcting by making the model more bullish.
3. **The guards are visibly binding.** `BASE_RERATE_CAP` (1.5x today's
   multiple), `ANCHOR_MAX` (45x) and the base margin path (midpoint of latest
   and the 3-year mean) each pull the base case down, and on a survivorship-
   biased bull sample they pull it below what happened. That is the designed
   behaviour, not evidence they are miscalibrated.
4. **IC is unchanged in character**: +0.429 / +0.071 / -0.048 / -0.049 and
   -0.232 / +0.184 / +0.245 / +0.204 — no consistent sign across samples,
   consistent with the standing verdict that no score here shows a demonstrated
   persistent edge.

**Shipped accordingly:** the forecast feeds **no score** and stays
descriptive-only, the same treatment as franchise (Addendum 9), stewardship
(Addendum 12) and sector (Addendum 14). No recalibration on this evidence — a
survivorship-biased sample in a bull regime is not grounds to loosen guards
that exist to stop the model assuming the market is wholesale wrong. Re-testing
against a survivorship-free sample is the open item.

---

## Addendum 16 — stewardship re-run after the EDGAR share-count fix: not promoted, and the protocol was not reproducible

Addendum 15 found that `edgar._annual_facts` read only `units["USD"]` while EDGAR
files share counts under `units["shares"]`, so `shares_diluted` was empty for
every US ticker. That is not a peripheral gap for stewardship — it is the
module's largest input:

| stewardship component | weight | status before the fix |
|---|---|---|
| `dilution_discipline` | **0.30** | **absent entirely** |
| `allocation_fit` | 0.30 | fine |
| `debt_discipline` | 0.25 | fine |
| `shareholder_returns` | 0.15 | degraded — `max(dividends, buybacks)` with buybacks always `None` |

US stewardship was therefore scored on at most 0.70 of its weight, and the
**"Serial Diluter" classification was unreachable** on US data: both branches
depend on share counts. ADEA dilutes 12.7%/yr across 57% of its years and
scored as though none of it were happening. Addendum 12's verdict was measured
against a score that could not see dilution at all.

**Re-run, 2026-07-31**, same script and pre-registered rule:

| Sample | base IC (A12 → now) | stewardship IC (A12 → now) |
|---|---|---|
| us-smallcap-sample | +0.098 → **−0.012** | +0.076 → **+0.079** |
| us-smallcap-sample2 | −0.028 → **+0.014** | −0.030 → **+0.019** |
| nifty-smallcap250 | +0.232 → **+0.221** | +0.218 → **+0.170** |

Nominal verdict: **2/3 → promote to first-class score.** Not acted on.

**Why the flip is not trustworthy:**

1. **India moved too, and India cannot have been affected.** NSE derives share
   counts from paid-up capital ÷ face value and was never touched by the bug,
   yet its base IC shifted +0.232 → +0.221. Something other than the EDGAR fix
   differs between runs.
2. **That something is universe drift.** `sample_evenly` is deterministic given
   a pool, but the pool is a live Wikipedia/NSE constituents page cached for
   168h. Any two ablation runs more than a week apart compare *different
   companies*. This run drew a different 80 names than Addendum 12 did.
3. **One "win" is by 0.005** (+0.014 vs +0.019), and every US IC sits within
   ±0.08 on 80-name samples — indistinguishable from zero.
4. **On the only sample with meaningful signal, base wins**: India +0.221 vs
   +0.170. Promoting here would repeat Addendum 14's own lesson, that a
   positive standalone reading does not make a blend better.

**The larger finding: no recorded ablation verdict was reproducible.**
Franchise (A9), stewardship (A12) and sector (A14) were each measured against a
silently-redrawing sample, so none could be re-derived or challenged. Fixed in
this commit: `get_universe(..., pinned=True)` reads a version-controlled
snapshot under `universes/` and **raises rather than falling back**, so a run is
either reproducible or loudly not. Production screening (`scripts/build_site.py`)
deliberately stays unpinned — the weekly site should track today's index. All
nine evidence scripts now pin. Snapshots frozen 2026-07-31: 80 / 80 / 250.

**Open thread:** base multibagger IC on `us-smallcap-sample` fell +0.098 →
−0.012 when `share_count_cagr_3y` (weight 0.10 in Financial Strength) re-entered
the pillar. That is either drift or evidence that the dilution metric is an
anti-signal on US smallcaps. Now answerable, against the pinned sample.

**Shipped accordingly:** stewardship stays descriptive-only. No promotion, no
recalibration. The verdict is re-testable for the first time.

---

## Addendum 17 — the dilution signal: the base-IC drop was drift, and the signal is kept

Closes the Addendum 16 open thread. First controlled A/B run against **pinned**
universes: identical companies, cutoffs, data and code, with only the dilution
signal toggled.

**The metric reaches the two scores by different routes**, which the first
attempt at this got wrong and is worth recording:

- `multibagger` sees it **only** through the hard gate (`engine._hard_gates`,
  caps at `HARD_GATE_CAP` for >8%/yr dilution). **Financial Strength is not in
  `MULTIBAGGER_WEIGHTS` at all** — so the pillar, and every metric in it, has
  zero influence on the published ranking.
- `investment` sees it **only** through the Financial Strength pillar (0.18 of
  that composite, 0.10 within the pillar). No gate applies.

A first pass toggled only the pillar and returned deltas of exactly 0.000 on
multibagger across 27 cutoffs. That is the correct answer for the pillar route
and the tell that the wrong path was being measured — a result that clean is
evidence of disconnection, not of no effect.

**Result:**

| route | us-smallcap-sample | us-smallcap-sample2 | nifty-smallcap250 |
|---|---|---|---|
| multibagger (hard gate) | −0.010 | +0.005 | **+0.055** |
| investment (pillar) | +0.002 | −0.008 | **+0.042** |

Both verdicts 2/3 → **keep**.

**Decomposing the Addendum 16 drop.** Base multibagger IC on
`us-smallcap-sample` fell +0.098 → −0.012 after the EDGAR fix. On the pinned
sample, removing dilution moves it only to −0.002:

| | base IC |
|---|---|
| A12: old universe, dilution unavailable | +0.098 |
| pinned universe, dilution removed | −0.002 |
| pinned universe, dilution present | −0.012 |

**−0.100 of the −0.110 swing was universe drift; −0.010 was the signal.** ~91%
drift. The metric is not an anti-signal on US smallcaps, and the alarm raised in
Addendum 16 is resolved.

**Honest interpretation:**

1. **US deltas (±0.010) are noise** on near-zero ICs — no conclusion either way
   from those samples.
2. **India carries the result**: +0.055 (multibagger) and +0.042 (investment),
   the only sample with meaningful base signal. India runs on NSE, which never
   had the share-count bug, so this is a pre-existing effect the EDGAR fix
   neither created nor flattered.
3. **The pillar route cannot affect the ranking.** Worth knowing independently:
   any future work tuning Financial Strength is tuning `investment` only.

**Shipped accordingly:** no change. The dilution gate and the pillar metric both
stay as they are. First verdict in this document derived against a pinned,
re-runnable sample.

---

## Protocol amendment (pre-registered 2026-07-31, before reading the franchise/sector re-runs)

**The promotion rule now requires a margin.** A sample counts as a win for a
candidate score only when `IC_score >= IC_base + 0.05`. Majority-of-samples is
unchanged.

**Why.** The original rule counted any `IC_score >= IC_base` as a win, with no
regard for effect size. Spearman IC has a standard error near `1/sqrt(n-3)` per
cutoff, and averaging over `k` cutoffs divides it by `sqrt(k)`:

| sample | n/cutoff | cutoffs | SE of mean IC |
|---|---|---|---|
| us-smallcap-sample | ~30 | 12 | ±0.055 |
| nifty-smallcap250 (3 cutoffs) | 50 | 3 | ±0.084 |
| nifty-smallcap250 (8 cutoffs) | 50 | 8 | ±0.052 |

Differences below ~0.05 are indistinguishable from noise at these sample sizes.
Addendum 16's stewardship re-run produced a "win" of **0.005** — about one tenth
of one standard error — which under the old rule counted as evidence toward
wiring a score into the published ranking. 0.05 is chosen as roughly one SE: a
weak bar, deliberately, since two SEs (~0.10-0.16) would be unmeetable on
samples this small.

**Recorded before the franchise and sector re-runs were read**, so it cannot be
fitted to their outcome. This is the whole point: the previous rule's failure
was only visible after it returned an absurd verdict, and adjusting it then
would have been hindsight.

**Retroactive effect on Addendum 16 (stewardship):** margins were +0.091,
+0.005, −0.051 → **1/3, demoted.** The judgment call made there — decline the
nominal 2/3 promotion — is what the amended rule produces mechanically. Verdict
unchanged; it now follows from the protocol rather than from an override.

---

## Addendum 18 — franchise and sector re-run on pinned universes: both verdicts hold, one supporting claim does not

First re-run of the two remaining ablations against **pinned** samples, under
the amended rule (win requires `IC_score >= IC_base + 0.05`).

### Franchise: 0/3, demoted — confirmed

| sample | base multibagger | franchise | margin |
|---|---|---|---|
| us-smallcap-sample | −0.012 | −0.036 | −0.024 |
| us-smallcap-sample2 | +0.014 | −0.022 | −0.036 |
| nifty-smallcap250 | +0.221 | **−0.166** | −0.387 |

Negative in every sample. Addendum 9's verdict holds, and the margin threshold
does not change it — 0/3 under either rule. This is the first time that
conclusion has been confirmed against a sample another person can reproduce.

Also from this run: **Quality alone scored +0.280 on India against a +0.221
composite** — margin +0.059, clearing the new threshold. Only 1/3 samples
(Quality is −0.066 and −0.056 on the US ones), so no promotion. Noted because it
is the second India reading suggesting a *component* may beat the *blend* it
sits in.

### Sector blend: 0/4, demoted — confirmed

| sample | base | +sector | margin |
|---|---|---|---|
| us-smallcap-sample | −0.012 | −0.021 | −0.009 |
| us-smallcap-sample2 | +0.014 | +0.009 | −0.005 |
| india-primary | +0.099 | +0.098 | −0.001 |
| india-replication | +0.137 | +0.128 | −0.009 |

`SECTOR_PILLAR_LIVE` stays `False`. Unchanged under either rule.

### But Addendum 14's standalone claim does not replicate

A14's first interpretation point read: *"Sector-alone IC was positive in all
four samples (+0.034 / +0.042 / +0.081 / +0.319) — weak but consistently
positive standalone signal, a genuinely different pattern from franchise."*

On pinned samples:

| sample | A14 sector-alone | now |
|---|---|---|
| us-smallcap-sample | +0.034 | +0.026 |
| us-smallcap-sample2 | +0.042 | **−0.033** |
| india-primary | +0.081 | **−0.103** |
| india-replication | +0.319 | +0.140 |

**Two of four flip sign.** "Consistently positive in all four samples" was an
artifact of the drifting universe, not a property of the signal. The +0.319
outlier A14 already distrusted lands at +0.140 on the pinned sample, which is
the direction that scepticism predicted.

The *shipped decision* was right either way — sector was demoted on the blend
test, not on the standalone reading. But the standalone reading was used to
argue sector was qualitatively unlike franchise, and that argument no longer
stands: on pinned data, sector-alone is 2-positive/2-negative, which is not
meaningfully different from noise.

**Honest interpretation:**

1. **All three demotions survive pinning.** Franchise (A9), stewardship (A16
   under the amended rule) and sector (A14) are unchanged. No shipped decision
   in this document was wrong.
2. **One supporting argument was drift.** The claim that sector-alone was
   consistently positive does not replicate. Directional claims drawn from
   redrawing samples were never safe, and this is the concrete example.
3. **The base score's own India IC is windowing-sensitive, as Addendum 13
   found**: +0.221 on 3 cutoffs (2021-23) vs +0.099/+0.137 on 8 (2016-23).
   Consistent, and a reminder that cutoff choice moves these numbers more than
   most of the signals being tested do.

**Shipped accordingly:** no change to any score, weight or flag. Addendum 14's
interpretation point 1 is retracted; its verdict stands.

---

## Addendum 19 — blend vs parts: Size Runway dominates, and it is the most survivorship-exposed signal we have

Two readings had hinted a single pillar might outperform the composite it sits
in. This tests every component of `MULTIBAGGER_WEIGHTS` against the blend on
pinned universes, under the pre-registered 0.05 margin. Descriptive only.

**Component IC minus blend IC** (`*` = beat the blend by >= 0.05):

| component | weight | us-sample | us-sample2 | india-primary | india-repl | wins |
|---|---|---|---|---|---|---|
| Growth | 0.26 | +0.018 | −0.053 | −0.060 | −0.120 | 0/4 |
| Quality | 0.24 | −0.054 | −0.069 | **+0.181\*** | −0.151 | 1/4 |
| **Size Runway** | 0.16 | **+0.268\*** | **+0.252\*** | **+0.269\*** | **+0.304\*** | **4/4** |
| Valuation | 0.14 | +0.046 | +0.014 | **+0.054\*** | −0.024 | 1/4 |
| Momentum | 0.10 | −0.037 | −0.018 | −0.209 | −0.100 | 0/4 |
| Reinvestment | 0.10 | +0.003 | +0.000 | −0.043 | −0.025 | 0/4 |

Absolute Size Runway ICs: **+0.256 / +0.266 / +0.368 / +0.440**, against blend
ICs of −0.012 / +0.014 / +0.099 / +0.137. It is the strongest and most
consistent signal anywhere in this document, by a wide margin.

`Size Runway` is a single-metric pillar: a market-cap bucket, smaller scoring
higher (`_size_pillar` / `score_size_runway`). So the finding restates as: at
these cutoffs, on these samples, **smaller market cap predicted higher forward
return far better than the composite did.**

**Why this must not be acted on yet.** Survivorship bias does not merely inflate
this result — it *manufactures exactly this pattern*. Universe membership is
today's index. A company that was tiny at a 2012 cutoff appears in today's
smallcap list only if it survived; the tiny names that went to zero are absent
by construction. "Small at cutoff → high realized return" is the precise shape
that a survivor-only sample produces from noise.

Cross-sample agreement does **not** rescue it. All four samples are drawn
today, so all four share the identical bias mechanism. Four samples agreeing
about an artifact is what an artifact looks like.

**Consequence: `scripts/survivorship_sensitivity.py` is now the critical path,
not an optional extra.** Until it runs, the largest signal in this document is
indistinguishable from its largest known bias. That reverses the priority
recorded in Addendum 15, which treated survivorship work as a low-stakes
follow-up to the forecast.

**Two side findings:**

1. **Addendum 18's Quality hint does not replicate.** Quality beat the blend by
   +0.181 on india-primary and *lost* by −0.151 on india-replication — two
   disjoint halves of the same index over the same cutoffs. That is the cleanest
   possible demonstration that a single-sample margin, even one clearing the
   pre-registered threshold, is not evidence. Resolved negative.
2. **Momentum is an anti-signal in all four samples** (−0.018 to −0.209),
   carrying weight 0.10 in the blend. Consistent in sign across two countries
   and two disjoint samples each. Unlike the size result, survivorship bias has
   no obvious mechanism for manufacturing this one, which makes it the more
   trustworthy of the two — and it argues the blend is being actively harmed by
   a component, not merely diluted.

**Shipped accordingly:** no weight changed, no score promoted or demoted.
Reweighting toward Size Runway on this evidence would be fitting to a probable
artifact — the exact error this document exists to prevent.

---

## Addendum 20 — Size Runway does not survive its own survivorship bound

Addendum 19 found Size Runway beating the full composite in 4/4 samples by
+0.25 to +0.30, the strongest reading in this document, and flagged that
survivorship bias manufactures exactly that pattern. This bounds it.

Method unchanged from the existing sensitivity harness: free
delisting-inclusive data does not exist, so synthetic "ghost" delisted names are
injected at each cutoff — smallest bucket, top size tier — across a grid of
delisting rates and ghost forward returns. Extended in this run to cover the two
India samples, which carried the strongest observed ICs and so most needed it.

**Observed:** +0.256 / +0.266 / +0.368 / +0.440.

**Adjusted IC at the stated realistic band** (10-15% delisted over a 2y window;
S&P 600 turnover ~5-8%/yr, skewed small):

| sample | 10% @ −40% | 10% @ −20% | 15% @ −40% | 15% @ −20% |
|---|---|---|---|---|
| us-smallcap-sample | −0.044 | +0.014 | −0.147 | −0.071 |
| us-smallcap-sample2 | −0.043 | +0.024 | −0.154 | −0.063 |
| india-primary | +0.023 | +0.075 | −0.080 | −0.013 |
| india-replication | +0.086 | +0.139 | −0.032 | +0.050 |

**Break-even ghost return** — if delisted names averaged worse than this, the
signal is gone entirely:

| sample | 5% | 10% | 15% | 20% |
|---|---|---|---|---|
| us-smallcap-sample | never | −25% | −9% | −2% |
| us-smallcap-sample2 | never | −27% | −10% | −4% |
| india-primary | never | −50% | −18% | −5% |
| india-replication | never | never | −32% | −10% |

**Interpretation:**

1. **The dominance does not survive.** At 10-15% delisting with plausibly
   negative ghost returns, the +0.26 to +0.44 observed collapses to a band
   straddling zero (−0.15 to +0.14). In no sample does Size Runway remain the
   dominant signal Addendum 19 showed.
2. **The break-evens sit inside the plausible range.** At 15% delisting the
   signal dies if delisted names averaged worse than −9% to −32%. Smallcap index
   removals mix bankruptcies (−100%) with premium buyouts (+20-40%), and the
   performance-related mix skews negative. A −10% to −30% average is not a
   pessimistic assumption; it is arguably the central one.
3. **India degrades less but not enough.** `india-replication` is the most
   robust — still positive at 10% under every ghost return tested — yet even it
   falls from +0.440 to +0.086 at 10%/−40%, losing ~80% of its magnitude, and
   goes negative by 15%/−60%.
4. **The result is contingent on an unmeasured parameter** that free data cannot
   supply. This is a bound, not a measurement, and it cannot be tightened
   without paid delisting-inclusive data (CRSP or equivalent).

**Shipped accordingly:** no weight changed. `Size Runway` keeps its 0.16 in
`MULTIBAGGER_WEIGHTS`, but **its backtest performance is withdrawn as evidence
for that weight.** Whatever justifies a size tilt has to come from the prior
literature on the size premium, where the effect is real and far smaller than
+0.27 IC — not from these samples, which cannot distinguish the effect from the
bias. Addendum 19's finding stands as measured and is explained here.

**Standing consequence:** every IC in this document is computed on
current-constituent samples. Size Runway is the most exposed because it is
literally a size bucket, but the exposure is universe-wide. Cross-sample
agreement never rescues a bias that all samples share — the four-sample
agreement in Addendum 19 is exactly what a shared artifact produces.

---

## Addendum 21 — weight variants: no change justified, and the blend's own IC is partly artifact

Tests whether dropping a component improves the blend, on pinned universes,
in-process so hard gates apply exactly as in production. Pre-registered margin
(>= 0.05) applies.

**Mean IC by variant:**

| variant | us-sample | us-sample2 | india-primary | india-repl |
|---|---|---|---|---|
| baseline | −0.012 | +0.014 | +0.099 | +0.137 |
| no-Momentum | +0.002 | +0.019 | +0.141 | +0.134 |
| no-Size | −0.036 | −0.002 | +0.072 | +0.081 |
| no-Momentum-no-Size | −0.021 | +0.002 | +0.147 | +0.080 |

**Delta vs baseline** (positive = dropping helped):

| variant | us-sample | us-sample2 | india-primary | india-repl | clears margin |
|---|---|---|---|---|---|
| no-Momentum | +0.014 | +0.006 | +0.041 | −0.003 | **0/4** |
| no-Size | −0.024 | −0.015 | −0.028 | −0.056 | **0/4** |
| no-Momentum-no-Size | −0.009 | −0.012 | +0.048 | −0.057 | **0/4** |

**Momentum: no change.** Removing it is directionally positive in 3/4 samples
(+0.014, +0.006, +0.041) but the largest gain is +0.041, below the 0.05 bar, and
it is mildly negative on india-replication. Consistent with Momentum being a
mild drag rather than a real cost. The Addendum 19 reading — anti-signal in 4/4
— survives as a *relative* statement about component vs blend, but does not
translate into a measurable improvement from deleting it. No weight changed.

**Size Runway: removing it makes the blend worse in 4/4 — and this is not
evidence it should stay.** The reasoning is circular and worth stating plainly.
Addendum 20 showed Size Runway's standalone signal does not survive its
survivorship bound. Blend IC is measured on the *same* survivorship-biased
samples. So deleting the artifact necessarily deletes the artifact's
contribution to the blend's measured IC. A component that helps a biased metric
because both share the bias has not been validated by that fact.

**The consequence is the real finding here.** Size Runway accounts for a large
share of what little IC the blend has:

| sample | blend | without Size | Size's share |
|---|---|---|---|
| us-smallcap-sample2 | +0.014 | −0.002 | **114%** (blend goes negative) |
| india-primary | +0.099 | +0.072 | **27%** |
| india-replication | +0.137 | +0.081 | **41%** |
| us-smallcap-sample | −0.012 | −0.036 | n/a (blend already negative) |

So roughly **a quarter to two-fifths of the blend's already-weak India IC — and
all of its US sample2 IC — is inherited from the one component whose standalone
signal fails its survivorship bound.** The contamination Addendum 20 identified
in `Size Runway` is not confined to that pillar; it propagates into the
composite score the site publishes.

**Shipped accordingly:** no weight changed. Nothing clears the pre-registered
margin, and changing weights on sub-threshold deltas is the error this protocol
exists to prevent. But the standing claim about the composite weakens further:
its measured edge was already near zero, and a substantial fraction of what
remains traces to a probable artifact.

**This is now the strongest argument for buying survivorship-free data.** Every
question left — does the blend have any edge, does Momentum cost anything, is
the size tilt real — is answerable with delisting-inclusive data (Sharadar,
Norgate, CRSP) and unanswerable without it. No further re-running of free
current-constituent samples will resolve any of them.

---

## Addendum 22 — the multibagger test: no detectable ability to find multibaggers

Every prior backtest here measures 2-year rank correlation. Rank correlation and
"did this 5x" are different questions — a score can rank tolerably and never
surface a single 10-bagger, or rank poorly while catching the few that matter.
The engine had never been evaluated against the outcome it is named for. This
does that.

**Method.** For each cutoff, take the top quintile by multibagger score, hold
**5 years**, count the fraction clearing 2x / 3x / 5x, and compare against the
base rate over the whole scored universe at the same cutoff. Cutoffs 2012-2021
(US) and 2016-2021 (India), pinned universes.

Absolute hit rates are inflated by survivorship — these are today's
constituents. But the top quintile and the universe are drawn from the *same*
biased pool, so **the lift between them largely cancels the bias** that broke
Addendum 20. Read the lift, not the hit rate.

**Pooled results:**

| sample | top-q n | 2x lift | 3x lift | 5x lift | median 5y: top-q vs universe |
|---|---|---|---|---|---|
| us-smallcap-sample | 117 | 1.06x | 1.18x | 0.63x | +53.4% vs +42.8% |
| us-smallcap-sample2 | 115 | 1.06x | 0.97x | 0.61x | +39.6% vs +38.3% |
| india-primary | 28 | 1.11x | 1.25x | 1.29x | +219.0% vs +167.8% |
| india-replication | 32 | 1.08x | 1.10x | 1.09x | +196.5% vs +164.0% |

**Every lift is statistically indistinguishable from 1.00x.** Binomial tests
against the per-sample base rate, all twelve cells:

| p-value range | count |
|---|---|
| p < 0.05 | **0 of 12** |
| p < 0.25 | **0 of 12** |
| p >= 0.25 | 12 of 12 |

The most extreme reading — 0.63x at 5x on `us-smallcap-sample`, which looks like
active harm — is **3 hits against 4.8 expected, p = 0.64.** Noise. So is the
1.29x on india-primary (8 vs 6.2, p = 0.37).

**What the test could have detected**, at p<0.05:

| sample | 2x | 3x | 5x |
|---|---|---|---|
| us-smallcap-sample | 1.31x | 1.51x | 2.08x |
| us-smallcap-sample2 | 1.32x | 1.64x | 2.17x |
| india-primary | 1.27x | 1.49x | 1.78x |
| india-replication | 1.26x | 1.46x | 1.70x |

So the honest statement is **not** "the engine does not find multibaggers." It
is: *if the top quintile produced 5-baggers at up to twice the base rate, this
test would not have noticed.* At the 5x threshold the samples contain 2-9 events
each. That is not a measurement, it is an anecdote with a percentage sign.

**Interpretation:**

1. **No demonstrated tail-finding ability, and no demonstrated harm either.**
   Twelve cells, four samples, 292 top-quintile stock-years, nothing significant.
2. **The one directionally consistent signal is the median**, which the top
   quintile beat in 4/4 samples (+10.6pp, +1.3pp, +51.2pp, +32.5pp). A sign test
   on 4/4 gives p = 0.125 — suggestive, not significant, and the US uplift is
   small enough to vanish under costs.
3. **The 2x lift clusters tightly at 1.06-1.11x across all four samples.** If
   that is real it is a ~6-11% improvement over picking at random from the same
   list. Detecting it reliably would need roughly 4-8x the current sample.
4. **Consistent with the score selecting for durability rather than
   convexity.** Quality, low leverage and established profitability are close to
   the opposite of the lottery-ticket profile that produces 5x moves in
   smallcaps. That is a defensible objective — it is simply not the one the name
   promises.

**Shipped accordingly:** nothing changed. Recorded so the product's central
claim has a measured answer instead of an implied one. The site ranks 25 names
by a score with no demonstrated ability to find multibaggers at any threshold;
the disclaimer already says scores are not validated return predictors, and this
is the specific evidence behind that sentence.

**Power is the binding constraint, not signal.** Every cell here is
under-powered, and the fix is more independent observations — which means
delisting-inclusive data covering a wider universe and more cutoffs, not more
re-runs of 80-name current-constituent samples.
