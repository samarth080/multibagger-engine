# Market-Aware 3-Year Scenario Forecast

Date: 2026-07-30
Status: approved, ready for implementation planning

## Problem

Every recommendation in the current top-25 shows a negative return **even in the
bull case**, including names whose fundamentals are unambiguously strong. HBL
Engineering (HBLENGINE.NS) is the diagnostic case:

```
Bull:  growth sustains at 30.0%, fair value 522.86 (-30%)
Base:  delivered-growth median of 25.0% continues 5 years, fair value 406.39 (-45%)
Bear:  growth decays to 15.0%, fair value 245.58 (-67%)
```

Against: ROCE 33%, debt/equity 0.03, interest coverage 72x, revenue CAGR 34.5%,
profit CAGR 102%, PEG 0.25, franchise score 91.7/100, and a trailing P/E of
25.2x that is **the lowest value in the stock's entire 3-year price history**
(3y median 74.3x, 10th percentile 50.3x). An engine that reports downside in
every scenario for that set of facts is not conservative; it is wrong.

### Root cause 1: the DCF starts from a two-year-stale cash flow

HBL's FCF by fiscal year (Rs cr): FY23 58.6 -> FY24 196.2 -> FY25 93.9 -> FY26 588.1.

`_base_fcf` in `src/mbe/analysis/valuation.py` takes the 3-year **mean of the
level series** (292.7 cr), which the owner-earnings floor lifts to 320.3 cr.
Latest actual FCF is 588.1 cr. Every scenario compounds off 54% of what the
business produced last year.

Smoothing does not fix this. Measured alternatives:

| base FCF method | base_fcf | bear 15% | base 25% | bull 30% |
|---|---|---|---|---|
| current (3y mean level + NI floor) | 320 cr | 246 (-67%) | 406 (-45%) | 523 (-30%) |
| median FCF-margin x latest revenue | 292 cr | 225 (-70%) | 371 (-50%) | 477 (-36%) |
| mean FCF-margin x latest revenue | 346 cr | 264 (-64%) | 437 (-41%) | 563 (-24%) |
| 50/50 latest + normalized | 440 cr | 331 (-55%) | 552 (-26%) | 712 (-4%) |
| latest FCF | 588 cr | 437 (-41%) | 732 (-1%) | 946 (+27%) |

Normalizing on the median FCF margin is *worse* than the status quo, because
HBL's FCF margin genuinely stepped up (8.83% -> 4.77% -> 17.81%). A four-year
history containing a step change cannot be averaged into a sensible starting
point; any backward-looking mean lags by construction.

### Root cause 2: conservatism sits in the shared input, not in the bear case

All three scenarios compound off one deliberately-haircut cash flow, so the
haircut is applied three times and **the bull case inherits the bear case's
pessimism**. This is the structural reason no name can show upside.

### Root cause 3: bull is not a scenario, it is base x 1.2

`g_bull = min(g_base * 1.2, 0.35)` moves exactly one knob. Discount rate,
terminal growth, fade shape, margins and exit multiple are identical across all
three scenarios.

### Root cause 4: the growth cap makes the report text false

`g_base = min(median(revenue_cagr, profit_cagr, fcf_cagr), 0.25)` takes a median
across three non-comparable series. HBL's are 34.5% / 102.1% / 115.8%, median
102%, clipped to 25%. The report then states *"delivered-growth median of
25.0%"* (`src/mbe/report/markdown.py:198`) — that is the cap, not the median.
Because bull = 1.2 x capped base, no company can ever have a bull case above 30%.

### Root cause 5: the engine's most optimistic case is below the market's

Reverse DCF says the market prices 37% FCF growth. The model's bull case is 30%.
Anything the market likes is therefore "overvalued" by construction.

### Root cause 6: the DCF cannot see what the engine already knows

`compute_valuation` is called at `src/mbe/pipeline.py:75`, before
`assess_business` runs. Franchise score, incremental ROIC, sector momentum and
stewardship are structurally invisible to the valuation.

## Goal

Forecast, for each stock, **a plausible price 3 years out in each of bull, base
and bear**, with an explicit probability-weighted expected 3-year return, built
from separately auditable growth, margin and exit-multiple assumptions.

## Non-goals

- The forecast does not feed any score in this change (see Scoring).
- No new data sources. Everything is derived from cached statements, prices and
  the existing cross-sectional peer grouping.
- No changes to the DCF's two-stage structure, discount rate or terminal rate.

## Design

### Part 1 — Honest base cash flow (valuation.py)

**Principle: conservatism belongs in the bear scenario, not in the input all
three scenarios share.** The base cash flow is the engine's best estimate of
current earning power. "FY26 might have been a peak" is a *bear assumption* and
must live where it can be seen and argued with.

`_base_fcf(fin) -> (base_fcf, proxy_used, spike_ratio)`:

1. If latest FCF > 0, use it. This is current earning power, including when
   latest is *below* the 3y mean (a declining business should read as declining).
2. Else if the 3y mean FCF > 0, use the mean.
3. Else if the 3y mean net income > 0, use `0.8 x` it and set `proxy_used`.
4. `spike_ratio = latest_fcf / mean3_fcf`, or `None` when `mean3_fcf <= 0`.

The owner-earnings floor is unchanged — it only ever lifts the base, so it
remains a valid guard for reinvestment-phase compounders.

`spike_ratio` is recorded in `ValuationResult.assumptions` and **does not
haircut the base**. It is consumed by the bear scenario (Part 2) and by the
`EARNINGS_SPIKE` risk flag (Part 4).

Consequence: `margin_of_safety` becomes honest. For HBL it moves from -45% to
about -1%, which lifts the Valuation pillar from 5/100 (weight 0.4) to roughly
55/100 and **reshuffles the ranked top 25**. This is intended and approved.

### Part 2 — 3-year scenario forecast

New `src/mbe/models/forecast.py`:

```python
class MultipleAnchor(BaseModel):
    peer_pe: float | None          # leave-one-out peer median
    peer_n: int                    # peers contributing
    own_pe_median: float | None    # own trailing P/E median over price history
    own_pe_percentile_now: float | None   # today's P/E within own history, 0..1
    own_pe_capped: float | None    # own median after the peer-relative cap
    quality_multiplier: float
    anchor: float | None           # final base-case exit multiple
    notes: list[str]               # audit trail, e.g. clamps applied

class ScenarioPath(BaseModel):
    name: str                      # "bull" | "base" | "bear"
    probability: float
    growth_start: float
    growth_end: float              # after 3-year linear fade
    terminal_net_margin: float
    exit_multiple: float
    revenue_fy3: float
    eps_fy3: float
    target_price: float
    cagr_3y: float
    evidence: list[str]            # one line per assumption, report-ready

class PriceForecast(BaseModel):
    ticker: str
    horizon_years: int = 3
    base_fiscal_year: int
    price: float
    anchor: MultipleAnchor
    scenarios: list[ScenarioPath]  # ordered bull, base, bear
    expected_target: float | None
    expected_cagr_3y: float | None
    downside_probability: float    # total probability of targets below price
    completeness: float
```

New `src/mbe/analysis/forecast.py`. Constants, all module-level and named:

```
HORIZON_YEARS       = 3
GROWTH_CAP          = 0.40    # cap on the starting revenue growth rate
TERMINAL_GROWTH_MIN = 0.04
TERMINAL_GROWTH_MAX = 0.15
TERMINAL_GROWTH_FALLBACK = 0.10
PEER_PE_MIN, PEER_PE_MAX = 5.0, 80.0     # sanity filter on peer P/E inputs
OWN_PE_CAP_VS_PEER  = 1.5
ANCHOR_MIN, ANCHOR_MAX = 8.0, 45.0
MULT_BEAR, MULT_BASE, MULT_BULL = 0.6, 1.0, 1.4
BULL_CAGR_CAP       = 0.45     # ~3x in 3 years, the two-sided sanity guard
SPIKE_THRESHOLD     = 1.5
```

**Step 1 — starting point.** Latest fiscal year only, no smoothing: revenue,
net margin `m0 = NI / revenue`, diluted share count.

**Step 2 — revenue growth paths.** The driver is `fund.revenue_cagr_3y` alone,
never the median across revenue/profit/FCF. `g0 = clamp(revenue_cagr_3y, 0.0,
GROWTH_CAP)`. The fade target `g_term` is the leave-one-out peer median revenue
CAGR clamped to `[TERMINAL_GROWTH_MIN, TERMINAL_GROWTH_MAX]`, falling back to
`TERMINAL_GROWTH_FALLBACK` when no peer set exists. Each path fades linearly
over the three years:

| scenario | start | end |
|---|---|---|
| bull | `g0` | `max(g0 * 0.7, g_term)` |
| base | `g0` | `g_term` |
| bear | `g0 * bear_mult` | `g_term * 0.5` |

`bear_mult` is 0.4, tightened to 0.2 when the NI spike ratio (latest NI / 3y
mean NI) is at or above `SPIKE_THRESHOLD`. This is where root cause 2 is paid
for: the peak-year risk is priced in the bear path, visibly.

**Step 3 — net margin paths.** `m0` is the latest fiscal year's net margin;
`m3` is the mean of the net-margin *ratio* over the last three fiscal years (a
mean of ratios, not a ratio of means). This is where "was FY26 a peak, or the
new normal?" gets argued explicitly instead of being buried in a smoothed input.

| scenario | terminal net margin |
|---|---|
| bull | `min(m0 * 1.05, best net margin in any available fiscal year)` |
| base | `(m0 + m3) / 2` |
| bear | `min(m0, m3)` |

**Step 4 — exit multiple.** Own trailing P/E series is computed from the price
history and the statement history, using `backtest.pointintime.availability_date`
and `fin.filed` so a fiscal year's earnings are only used from the date they
were actually available. Peer P/E comes from the leave-one-out group members'
`val.pe`, filtered to `[PEER_PE_MIN, PEER_PE_MAX]`.

```
quality_multiplier = 0.85 + 0.35 * (business.franchise_score / 100)   # [0.85, 1.20]

both present:  own_capped = min(own_pe_median, OWN_PE_CAP_VS_PEER * peer_pe)
               raw = 0.6 * peer_pe + 0.4 * own_capped
peer only:     raw = peer_pe
own only:      raw = min(own_pe_median, ANCHOR_MAX)
neither:       no anchor is derivable -> build_forecast returns None and
               bundle.forecast stays None; the report says so explicitly
               rather than emitting a forecast built on nothing

anchor = clamp(raw * quality_multiplier, ANCHOR_MIN, ANCHOR_MAX)
exit_multiple = anchor * {bear: 0.6, base: 1.0, bull: 1.4}
```

The `OWN_PE_CAP_VS_PEER` cap exists because our price window is short and
regime-bound. HBL's own 3y median of 74.3x is a 2023-26 Indian smallcap bull
artifact and would wreck the forecast if taken at face value. Every clamp that
binds is appended to `MultipleAnchor.notes`.

**Step 5 — targets, and the two-sided guard.** Share count grows at
`max(share_count_cagr_3y, 0)`.

```
revenue_fy3 = revenue_0 * prod(1 + g_t)   for the three faded years
eps_fy3     = revenue_fy3 * terminal_net_margin / shares_fy3
target      = eps_fy3 * exit_multiple
cagr_3y     = (target / price) ** (1/3) - 1
```

**Scenarios may not set every knob to an extreme simultaneously.** Stacking
sustained growth, expanded margins and a full re-rating produced a bull target
of 5x in three years for HBL — the same error as the current code with the sign
flipped. Guard: if the bull `cagr_3y` exceeds `BULL_CAGR_CAP`, scale the bull
exit multiple down until the cap is met exactly, and record the trim in that
scenario's `evidence` (e.g. *"bull exit multiple trimmed 59x -> 44x to respect
the 45%/yr sanity bound"*). One knob is trimmed and the report says so.

The trim never takes the bull exit multiple below the base case's — that would
invert the scenario ordering. If the cap is still breached at the base multiple,
the bull target is left as computed and its `evidence` says the bound could not
be honoured without inverting the scenarios. That combination means the
*earnings* path alone implies a tripling, which is a finding worth surfacing
rather than hiding behind a clamp.

**Invariant:** `bear.target < base.target < bull.target`, always. If the
computed targets violate it, that is a bug and the tests must catch it.

**Step 6 — probabilities.** Drawn from evidence the engine already computes.
`mean_assumption_support` is the mean of `historical_support` across
`thesis.assumptions`, i.e. the same quantity `build_thesis` already uses for
`thesis_confidence`; it is 0.5 when there are no assumptions.

```
quality = 0.5 * mean_assumption_support + 0.5 * (franchise_score / 100)
p_bull  = 0.10 + 0.30 * quality
p_bear  = 0.40 - 0.25 * quality
p_base  = 1 - p_bull - p_bear
if critique.veto: move 0.15 from p_bull to p_bear (each clamped to >= 0)
```

For HBL (mean support 0.87, franchise 91.7): 0.368 / 0.455 / 0.177.

```
expected_target      = sum(p_i * target_i)
expected_cagr_3y     = (expected_target / price) ** (1/3) - 1
downside_probability = sum(p_i for scenarios with target_i < price)
```

Expected value is computed on **prices, then annualized** — averaging CAGRs
directly would be wrong, since CAGR is non-linear in price.

**Completeness** is the fraction present of: peer P/E, own P/E, revenue CAGR,
net margin, share count, franchise score, assumption support.

### Part 3 — Pipeline wiring

`AnalysisBundle` gains `forecast: PriceForecast | None = None`.

- `screen()` calls a new `apply_forecasts(bundles, context)` post-pass
  immediately after `apply_sector_pillar` (`src/mbe/pipeline.py:104`). Running
  as a post-pass is what gives the forecast access to franchise score, thesis
  assumption support and leave-one-out peer multiples off completed bundles.
- `analyze_ticker` calls `build_forecast(bundle, peers=None)` so
  `mbe analyze TICKER` (`src/mbe/cli.py:44`) still emits a forecast; the peer
  term is simply absent and `completeness` records it.
- No existing call is reordered. This mirrors the cross-sectional precedent
  already documented in `src/mbe/analysis/sector.py`: the same stock legitimately
  gets a different peer anchor in a different universe.

### Part 4 — Report and risk flags

The "Bull / Base / Bear" block (`src/mbe/report/markdown.py:195-199`) is
replaced by a **3-Year Price Forecast** section containing:

- the scenario table: growth path, terminal margin, exit multiple, FY+3 EPS,
  target price, 3y CAGR, probability;
- the probability-weighted expected target, expected 3y CAGR and downside
  probability;
- an anchor audit sub-table showing peer / own-history / quality inputs, today's
  P/E percentile within own history, and any clamps that bound.

The DCF Valuation section stays, now with a correct base FCF and `spike_ratio`
disclosed. This also removes the false *"delivered-growth median of 25.0%"* line.

Three new coherence flags. `assess_risk` runs at `src/mbe/pipeline.py:76`, before
the forecast exists, and it receives no price history — so these flags cannot
live in `risk.py`. They are produced by `forecast_flags(bundle) -> list[RiskFlag]`
in `forecast.py`, called immediately after the forecast is built and appended to
`bundle.risk.flags`, in both the `screen()` post-pass and `analyze_ticker`. This
keeps `assess_risk`'s signature untouched and all three checks in one place.

| code | condition | severity |
|---|---|---|
| `MULTIPLE_AT_LOW` | today's P/E at or below the 10th percentile of its own history | 1 (info) |
| `EARNINGS_SPIKE` | latest NI / 3y mean NI >= `SPIKE_THRESHOLD` — the bear case is load-bearing | 1 (info) |
| `FORECAST_INCOHERENT` | bull scenario implied growth below `val.implied_growth` — a model error, not a finding | 2 (warning) |

These flags are reported but **do not alter `risk_score`**, which is already
computed by the time they are known. That is consistent with Part 5: the only
scoring change in this spec is the one flowing from `margin_of_safety`.

`MULTIPLE_AT_LOW` fires for HBL today. `FORECAST_INCOHERENT` exists so the
failure mode this whole spec addresses cannot recur silently.

### Part 5 — Scoring

The Part 1 fix flows into `margin_of_safety` and therefore the Valuation pillar
and the ranking. Approved and expected.

**The forecast itself feeds no score in this change.** It is descriptive-only,
exactly as `franchise_score` and the critique veto already are, until the
backtest harness shows it earns a place. Per
`docs/backtest-findings-2026-07.md`, none of the current scores show a
demonstrated persistent edge; wiring an unvalidated 3-year forecast straight
into the ranking would repeat a documented mistake.

### Part 6 — Validation

`src/mbe/backtest/harness.py` gains a forecast-accuracy mode: predicted 3-year
return vs realized, point-in-time, reusing `truncate_financials` /
`truncate_prices`.

Stated up front: the Indian sample spans 2021-2025 and therefore contains
barely one non-overlapping 3-year window. The US 2012-2025 sample will carry
almost all of the evidence, and initial results should be expected to be weak.
The report describes the forecast as a scenario model with stated assumptions,
not as a prediction.

## Testing

TDD. `tests/test_forecast.py` (new), plus additions to `tests/test_valuation.py`
and `tests/test_pipeline.py`.

Base cash flow:
- A step-change fixture (HBL-shaped: revenue +68%, net margin 12.6% -> 24.7%)
  is not haircut to its trailing mean; base FCF equals latest FCF.
- A declining-FCF fixture uses latest FCF, not the flattering 3y mean.
- Negative latest FCF still falls through to the mean, then the NI proxy —
  existing `test_negative_fcf_uses_ni_proxy` behaviour preserved.
- The owner-earnings floor still only lifts, never lowers.

Scenarios:
- Invariant `bear.target < base.target < bull.target` holds across fixtures.
- A peak-year fixture (NI spike ratio >= 1.5) produces a materially harsher bear
  path than an otherwise identical steady grower.
- The bull guard binds: a fixture that would produce >45%/yr has its bull exit
  multiple trimmed, the resulting CAGR equals the cap, and the trim appears in
  `evidence`.
- The own-history multiple cap binds when own median exceeds 1.5x peer median,
  and the clamp is recorded in `MultipleAnchor.notes`.
- Probabilities sum to 1.0 within tolerance; a vetoed thesis shifts weight to bear.
- Expected value is computed on prices, not by averaging CAGRs (a fixture with
  a wide spread distinguishes the two).
- No-peers path produces a forecast with reduced, correctly-recorded completeness.
- Neither peer nor own P/E available: no forecast, no crash.

Coherence flags:
- Each of the three new codes fires on a fixture that should trigger it and
  stays silent otherwise.
- `risk_score` is unchanged by their presence.

Pipeline:
- `screen()` populates `forecast` on every bundle; `analyze_ticker` populates it
  with lower completeness.
- Coherence flags are appended to `bundle.risk.flags` on both paths.

## Files touched

| file | change |
|---|---|
| `src/mbe/models/forecast.py` | new — `MultipleAnchor`, `ScenarioPath`, `PriceForecast` |
| `src/mbe/analysis/forecast.py` | new — anchor, paths, targets, probabilities, guards, `forecast_flags` |
| `src/mbe/analysis/valuation.py` | base FCF fix, `spike_ratio` in assumptions |
| `src/mbe/pipeline.py` | bundle field, `apply_forecasts` post-pass, single-ticker call, flag append |
| `src/mbe/report/markdown.py` | 3-Year Price Forecast section, remove false median line |
| `src/mbe/backtest/harness.py` | forecast-accuracy mode |
| `tests/test_forecast.py` | new — scenarios, anchor, guards, probabilities, flags |
| `tests/test_valuation.py`, `tests/test_pipeline.py` | extended |

## Expected effect on the HBL case

DCF base case moves from 406.39 (-45%) to roughly 732 (-1%), bull from 523
(-30%) to roughly 946 (+27%). The new forecast section reports three 3-year
target prices with a probability-weighted expected 3-year CAGR, an
`EARNINGS_SPIKE` flag noting the bear case is load-bearing, and a
`MULTIPLE_AT_LOW` flag noting the stock trades at the bottom of its own 3-year
multiple range. Rankings across the top 25 shift as the Valuation pillar
stops penalising high-growth compounders for the arithmetic of their own growth.
