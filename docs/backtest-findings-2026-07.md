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
