# Market-Aware 3-Year Scenario Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current bull/base/bear block — which shows downside in every scenario for even the strongest businesses — with an honest DCF base cash flow plus a 3-year scenario forecast that projects target prices from revenue, margin and exit multiple.

**Architecture:** Two independent changes. (1) `analysis/valuation.py` stops smoothing the DCF's base cash flow, moving the peak-year risk out of the shared input and into the bear scenario. (2) A new `analysis/forecast.py`, run as a cross-sectional post-pass in `screen()`, projects FY+3 EPS from revenue × net margin and applies a blended peer/own-history/quality exit multiple, producing three probability-weighted target prices with two-sided sanity guards.

**Tech Stack:** Python 3.12, pydantic v2 models, pandas for price series, pytest, jinja2 report templates. Run tests with `.venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-07-30-market-aware-scenario-forecast-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/mbe/models/forecast.py` | new — `MultipleAnchor`, `ScenarioPath`, `PriceForecast`. Data only, no logic. |
| `src/mbe/analysis/forecast.py` | new — own-P/E series, exit-multiple anchor, growth/margin paths, target projection, guards, probabilities, coherence flags. |
| `src/mbe/analysis/valuation.py` | modify — `_base_fcf` returns current earning power + `spike_ratio`. |
| `src/mbe/pipeline.py` | modify — `AnalysisBundle.forecast`, `apply_forecasts` post-pass, single-ticker call, flag append. |
| `src/mbe/report/markdown.py` | modify — replace the Bull/Base/Bear block with a 3-Year Price Forecast section. |
| `src/mbe/backtest/harness.py` | modify — forecast-accuracy mode. |
| `tests/test_forecast.py` | new — anchor, paths, guards, probabilities, flags. |
| `tests/test_valuation.py` | modify — base-FCF behaviour, one existing assertion updated. |
| `tests/test_pipeline.py` | modify — forecast populated on both code paths. |

`forecast.py` holds all forecast logic including the coherence flags. They do **not** go in `risk.py`: `assess_risk` runs at `pipeline.py:76`, before the forecast exists, and receives no price history.

---

## Task 1: Honest DCF base cash flow

**Files:**
- Modify: `src/mbe/analysis/valuation.py:63-79` (`_avg_last3`, `_base_fcf`), `:115` (call site), `:190-200` (assumptions), `:1-12` (docstring)
- Test: `tests/test_valuation.py`

Background: HBL's FCF by fiscal year is 58.6 → 196.2 → 93.9 → 588.1 (Rs cr). The 3-year mean is 292.7 against a latest of 588.1, so all three scenarios compound off 54% of last year's actual cash flow. No averaging window fixes a step change; the fix is to use current earning power and move the peak risk into the bear scenario.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_valuation.py`:

```python
def test_base_fcf_uses_latest_not_trailing_mean():
    """A step change in cash flow must not be averaged away. HBL-shaped:
    revenue +68% and net margin 12.6% -> 24.7% in the latest year."""
    years = [2023, 2024, 2025, 2026]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, [1357.6, 2221.5, 1967.2, 3302.8])),
            "net_income": dict(zip(years, [98.7, 280.9, 276.9, 814.9])),
            "cfo": dict(zip(years, [122.4, 270.3, 246.7, 738.4])),
            "capex": dict(zip(years, [63.9, 74.1, 152.8, 150.3])),
            "fcf": dict(zip(years, [58.6, 196.2, 93.9, 588.1])),
            "shares_diluted": dict(zip(years, [27.7, 27.7, 27.8, 27.7])),
            "total_equity": dict(zip(years, [951.4, 1220.5, 1482.7, 2214.2])),
            "total_debt": dict(zip(years, [86.0, 67.5, 74.3, 66.9])),
            "cash": dict(zip(years, [132.0, 223.5, 117.0, 528.2])),
        }
    )
    info = CompanyInfo(ticker="STEP.NS", market_cap=20574.0, shares_outstanding=27.7)
    fund = compute_fundamentals(fin, info)
    v = compute_valuation(fin, info, fund, price=741.9)
    assert v.assumptions["base_fcf"] == pytest.approx(588.1, abs=0.01)
    # 588.1 / mean(196.2, 93.9, 588.1) = 588.1 / 292.73
    assert v.assumptions["fcf_spike_ratio"] == pytest.approx(2.009, abs=0.005)
    assert not v.fcf_proxy_used


def test_declining_fcf_uses_latest_not_flattering_mean():
    """Symmetry check: a business whose cash flow is shrinking must read as
    shrinking, not be propped up by its own better past."""
    years = [2023, 2024, 2025, 2026]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, [1000.0, 1000.0, 1000.0, 1000.0])),
            "net_income": dict(zip(years, [100.0, 90.0, 70.0, 50.0])),
            "cfo": dict(zip(years, [110.0, 95.0, 72.0, 52.0])),
            "capex": dict(zip(years, [10.0, 10.0, 10.0, 10.0])),
            "fcf": dict(zip(years, [100.0, 85.0, 62.0, 42.0])),
            "shares_diluted": dict(zip(years, [10.0, 10.0, 10.0, 10.0])),
        }
    )
    info = CompanyInfo(ticker="FADE.NS", market_cap=800.0, shares_outstanding=10.0)
    fund = compute_fundamentals(fin, info)
    v = compute_valuation(fin, info, fund, price=80.0)
    assert v.assumptions["base_fcf"] == pytest.approx(42.0, abs=0.01)
    assert v.assumptions["fcf_spike_ratio"] == pytest.approx(42.0 / 63.0, abs=0.005)


def test_spike_ratio_nan_when_trailing_mean_non_positive():
    """No spike ratio is definable against a non-positive mean; the DCF must
    still produce a value via the NI proxy."""
    years = [2022, 2023, 2024]
    fin = FinancialHistory(
        data={
            "net_income": dict(zip(years, [10.0, 12.0, 15.0])),
            "fcf": dict(zip(years, [-5.0, -3.0, -2.0])),
            "shares_diluted": dict(zip(years, [10.0, 10.0, 10.0])),
        }
    )
    info = CompanyInfo(ticker="X.NS", market_cap=300.0, shares_outstanding=10.0)
    fund = compute_fundamentals(fin, info)
    v = compute_valuation(fin, info, fund, price=30.0)
    assert v.fcf_proxy_used
    import math
    assert math.isnan(v.assumptions["fcf_spike_ratio"])
```

- [ ] **Step 2: Update the one existing assertion this intentionally changes**

`test_owner_earnings_floor_skipped_when_earnings_not_cash_backed` currently asserts the base equals the 3y FCF mean `(15+16+18)/3`. Under the new rule it is the latest, `18.0`. This is the intended behaviour change, not a regression. In `tests/test_valuation.py`, replace:

```python
    assert v.assumptions["base_fcf"] == pytest.approx((15 + 16 + 18) / 3, abs=0.01)
```

with:

```python
    # base is current earning power (latest FCF), not the 3y mean; the
    # owner-earnings floor is correctly skipped because CFO/NI is only ~0.37
    assert v.assumptions["base_fcf"] == pytest.approx(18.0, abs=0.01)
```

The other four existing base-FCF tests are unaffected: `test_owner_earnings_floor_for_capex_heavy_compounder` has a floor of 68.13 that still dominates a latest FCF of 18.0; `test_negative_fcf_uses_ni_proxy` and `test_high_leverage_floors_fair_value_at_zero_not_negative` have a non-positive latest FCF and still fall through to the proxy; `test_dcf_scenarios_ordered_and_mos_consistent` only asserts ordering and consistency.

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `.venv/bin/python -m pytest tests/test_valuation.py -v`

Expected: the three new tests FAIL with `KeyError: 'fcf_spike_ratio'`, and `test_owner_earnings_floor_skipped_when_earnings_not_cash_backed` fails on `18.0 != 16.33`.

- [ ] **Step 4: Rewrite `_base_fcf`**

In `src/mbe/analysis/valuation.py`, replace the whole `_base_fcf` function (lines 68-79):

```python
def _base_fcf(fin: FinancialHistory) -> tuple[float | None, bool, float | None]:
    """Returns (base_fcf, proxy_used, spike_ratio).

    Current earning power, deliberately NOT a smoothed average. A trailing mean
    of a level series systematically understates a business whose cash flow is
    growing, and no averaging window can absorb a step change — measured on
    HBLENGINE.NS, every smoothing variant landed within 20% of the biased
    result. The risk that the latest year was a peak belongs to the *bear
    scenario* (see analysis/forecast.py), not to a haircut applied to all three
    scenarios at once, which is what made even bull cases show downside.

    `spike_ratio` (latest / 3y mean) quantifies how far the latest year stands
    out. It is reported, never used to reduce the base.
    """
    avg_fcf = _avg_last3(fin, "fcf")
    latest_fcf = fin.latest("fcf")
    spike_ratio = (
        latest_fcf / avg_fcf
        if latest_fcf is not None and avg_fcf is not None and avg_fcf > 0
        else None
    )
    if latest_fcf is not None and latest_fcf > 0:
        return latest_fcf, False, spike_ratio
    if avg_fcf is not None and avg_fcf > 0:
        return avg_fcf, False, spike_ratio
    avg_ni = _avg_last3(fin, "net_income")
    if avg_ni is not None and avg_ni > 0:
        return 0.8 * avg_ni, True, spike_ratio
    return None, False, spike_ratio
```

- [ ] **Step 5: Update the call site and assumptions**

In `src/mbe/analysis/valuation.py`, change line 115 from:

```python
    base_fcf, proxy_used = _base_fcf(fin)
```

to:

```python
    base_fcf, proxy_used, spike_ratio = _base_fcf(fin)
```

Then in the `assumptions` dict of the returned `ValuationResult`, add one entry after `"base_fcf"`:

```python
            "fcf_spike_ratio": spike_ratio if spike_ratio is not None else float("nan"),
```

- [ ] **Step 6: Update the module docstring**

In `src/mbe/analysis/valuation.py`, replace the first two bullets of the module docstring (lines 4-6):

```
- Base FCF = 3y average FCF (smooths capex cycles); latest FCF if the average
  is non-positive; 0.8 x 3y-avg net income as a flagged proxy otherwise.
```

with:

```
- Base FCF = latest FCF (current earning power); the 3y average only when the
  latest is non-positive; 0.8 x 3y-avg net income as a flagged proxy otherwise.
  Deliberately unsmoothed: averaging a growing level series understates it, and
  conservatism belongs in the bear scenario, not in the input all three share.
```

- [ ] **Step 7: Run the full valuation suite**

Run: `.venv/bin/python -m pytest tests/test_valuation.py -v`

Expected: all PASS, including the three new tests.

- [ ] **Step 8: Run the whole suite to catch downstream breakage**

Run: `.venv/bin/python -m pytest -q`

Expected: all PASS. `tests/test_scoring.py` and `tests/test_risk.py` consume `margin_of_safety`; if either asserts a hard-coded fair value or MoS number, update it to the new value and note in the commit that the change is intended.

- [ ] **Step 9: Commit**

```bash
git add src/mbe/analysis/valuation.py tests/test_valuation.py
git commit -m "fix(valuation): base DCF on current earning power, not a trailing mean

A 3y mean of a level series understates any business whose cash flow is
growing, and no averaging window absorbs a step change. Because all three
scenarios shared that haircut input, even bull cases showed downside.

Base FCF is now latest FCF, with the peak-year risk exposed as
fcf_spike_ratio for the bear scenario to consume instead."
```

---

## Task 2: Forecast models

**Files:**
- Create: `src/mbe/models/forecast.py`
- Test: `tests/test_forecast.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_forecast.py`:

```python
import pytest

from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath


def test_models_construct_with_defaults():
    anchor = MultipleAnchor(peer_pe=22.0, peer_n=6, anchor=30.0)
    assert anchor.quality_multiplier == 1.0
    assert anchor.notes == []
    assert anchor.own_pe_median is None

    path = ScenarioPath(
        name="base", probability=0.5, growth_start=0.345, growth_end=0.10,
        terminal_net_margin=0.209, exit_multiple=30.0, revenue_fy3=6742.0,
        eps_fy3=50.8, target_price=1524.0, cagr_3y=0.275,
    )
    assert path.evidence == []

    fc = PriceForecast(
        ticker="TEST.NS", base_fiscal_year=2026, price=741.9,
        anchor=anchor, scenarios=[path],
    )
    assert fc.horizon_years == 3
    assert fc.expected_target is None
    assert fc.downside_probability == 0.0
    assert fc.completeness == 0.0


def test_probability_is_bounded():
    with pytest.raises(ValueError):
        ScenarioPath(
            name="base", probability=1.5, growth_start=0.1, growth_end=0.1,
            terminal_net_margin=0.2, exit_multiple=20.0, revenue_fy3=100.0,
            eps_fy3=2.0, target_price=40.0, cagr_3y=0.1,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.models.forecast'`

- [ ] **Step 3: Create the models**

Create `src/mbe/models/forecast.py`:

```python
"""3-year scenario forecast models.

A forecast is three explicit paths that each move growth, margin AND the exit
multiple — not one growth knob nudged three ways, which is what made every
scenario in v0.1 tell the same story. Every assumption is carried as
report-ready evidence so a reader can disagree with a specific number instead
of the whole output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MultipleAnchor(BaseModel):
    """How the base-case exit multiple was built.

    Fully auditable by construction: a 3-year forecast is only as good as its
    exit multiple, so every input and every clamp that bound is recorded.
    """

    peer_pe: float | None = None           # leave-one-out peer median P/E
    peer_n: int = 0                        # peers that passed the sanity filter
    own_pe_median: float | None = None     # median trailing P/E over price history
    own_pe_percentile_now: float | None = None  # today's P/E within own history, 0..1
    own_pe_capped: float | None = None     # own median after the peer-relative cap
    quality_multiplier: float = 1.0
    anchor: float | None = None            # final base-case exit multiple
    notes: list[str] = []


class ScenarioPath(BaseModel):
    name: str                              # "bull" | "base" | "bear"
    probability: float = Field(ge=0, le=1)
    growth_start: float
    growth_end: float                      # revenue growth after the 3y fade
    terminal_net_margin: float
    exit_multiple: float
    revenue_fy3: float
    eps_fy3: float
    target_price: float
    cagr_3y: float
    evidence: list[str] = []


class PriceForecast(BaseModel):
    ticker: str
    horizon_years: int = 3
    base_fiscal_year: int
    price: float
    anchor: MultipleAnchor
    scenarios: list[ScenarioPath] = []     # ordered bull, base, bear
    expected_target: float | None = None
    expected_cagr_3y: float | None = None
    downside_probability: float = 0.0      # total probability of targets below price
    completeness: float = Field(ge=0, le=1, default=0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/models/forecast.py tests/test_forecast.py
git commit -m "feat(models): 3-year scenario forecast models"
```

---

## Task 3: Own trailing P/E history

**Files:**
- Create: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

This is the market-awareness input: where does today's multiple sit inside the stock's own history? It must not look ahead — a fiscal year's earnings may only be used from the date they were published. `backtest/pointintime.py:24` already provides `availability_date(fy_year, fy_end_month)` with a 90-day filing lag, and `FinancialHistory.filed` carries real filing dates when known.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
import pandas as pd

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory


def _prices(dates: list[str], closes: list[float]) -> PriceHistory:
    idx = pd.to_datetime(dates)
    return PriceHistory(
        df=pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1000.0] * len(closes)},
            index=idx,
        )
    )


def test_own_pe_series_uses_only_published_earnings():
    """Indian FY2025 ends 31-Mar-2025 and becomes visible 90 days later
    (29-Jun-2025). A price on 01-Jun-2025 must still use FY2024 earnings."""
    from mbe.analysis.forecast import own_pe_series

    fin = FinancialHistory(
        data={
            "net_income": {2024: 100.0, 2025: 200.0},
            "shares_diluted": {2024: 10.0, 2025: 10.0},
        }
    )
    info = CompanyInfo(ticker="PIT.NS")
    prices = _prices(["2025-06-01", "2025-08-01"], [100.0, 100.0])

    pes = own_pe_series(prices, fin, info)
    # 01-Jun: EPS 10.0 (FY2024) -> P/E 10.0;  01-Aug: EPS 20.0 (FY2025) -> 5.0
    assert pes == pytest.approx([10.0, 5.0])


def test_own_pe_series_honours_explicit_filed_dates():
    from mbe.analysis.forecast import own_pe_series
    from datetime import date

    fin = FinancialHistory(
        data={
            "net_income": {2024: 100.0, 2025: 200.0},
            "shares_diluted": {2024: 10.0, 2025: 10.0},
        },
        filed={2025: date(2025, 5, 1)},
    )
    info = CompanyInfo(ticker="PIT.NS")
    prices = _prices(["2025-06-01"], [100.0])
    # filed 01-May beats the 90-day default, so FY2025 is already visible
    assert own_pe_series(prices, fin, info) == pytest.approx([5.0])


def test_own_pe_series_skips_loss_years_and_empty_history():
    from mbe.analysis.forecast import own_pe_series

    loss = FinancialHistory(
        data={"net_income": {2024: -50.0}, "shares_diluted": {2024: 10.0}}
    )
    info = CompanyInfo(ticker="LOSS.NS")
    assert own_pe_series(_prices(["2025-06-01"], [100.0]), loss, info) == []

    empty = FinancialHistory(data={})
    assert own_pe_series(_prices(["2025-06-01"], [100.0]), empty, info) == []


def test_percentile_of_places_value_in_distribution():
    from mbe.analysis.forecast import percentile_of

    assert percentile_of([10.0, 20.0, 30.0, 40.0], 10.0) == pytest.approx(0.25)
    assert percentile_of([10.0, 20.0, 30.0, 40.0], 40.0) == pytest.approx(1.0)
    assert percentile_of([], 10.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.analysis.forecast'`

- [ ] **Step 3: Create `forecast.py` with the P/E history helpers**

Create `src/mbe/analysis/forecast.py`:

```python
"""3-year scenario forecast: what could this stock be worth in three years?

The v0.1 valuation moved exactly one knob between bull, base and bear (growth,
by a factor of 1.2) while sharing a deliberately-haircut base cash flow, so
every scenario told the same pessimistic story. This module instead projects
revenue and net margin separately, applies an exit multiple anchored to what
peers and the stock's own history actually trade at, and guards both ends:
neither the input nor any single scenario is allowed to carry all the
conservatism or all the optimism.

Cross-sectional by nature — the peer anchor needs a screened universe — so it
runs as a post-pass over completed bundles, the same contract as
analysis/sector.py. On the single-ticker path the peer term is simply absent
and PriceForecast.completeness records it.
"""

from __future__ import annotations

from datetime import date
from statistics import median

from mbe.backtest.pointintime import availability_date
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory

HORIZON_YEARS = 3
GROWTH_CAP = 0.40             # cap on the starting revenue growth rate
TERMINAL_GROWTH_MIN = 0.04
TERMINAL_GROWTH_MAX = 0.15
TERMINAL_GROWTH_FALLBACK = 0.10
PEER_PE_MIN, PEER_PE_MAX = 5.0, 80.0   # sanity filter on peer P/E inputs
OWN_PE_CAP_VS_PEER = 1.5
ANCHOR_MIN, ANCHOR_MAX = 8.0, 45.0
MULT_BEAR, MULT_BASE, MULT_BULL = 0.6, 1.0, 1.4
BULL_CAGR_CAP = 0.45          # ~3x in 3 years; the optimism-side guard
SPIKE_THRESHOLD = 1.5
BEAR_GROWTH_MULT = 0.4
BEAR_GROWTH_MULT_SPIKED = 0.2


def own_pe_series(
    prices: PriceHistory, fin: FinancialHistory, info: CompanyInfo
) -> list[float]:
    """Trailing P/E for each trading day, using only earnings published by that
    date. Yahoo labels an Indian fiscal year by its March end-year, so the
    90-day filing lag in pointintime.availability_date is what stops this from
    looking ahead; fin.filed overrides it whenever a real date is known.
    """
    ni = dict(fin.series("net_income"))
    shares = dict(fin.series("shares_diluted"))
    if not ni or prices.df.empty:
        return []
    fy_end_month = 3 if info.ticker.endswith((".NS", ".BO")) else 12
    visible_from: list[tuple[date, int]] = sorted(
        (fin.filed.get(year) or availability_date(year, fy_end_month), year)
        for year in ni
    )
    out: list[float] = []
    for timestamp, close in prices.df["close"].items():
        as_of = timestamp.date()
        published = [year for avail, year in visible_from if avail <= as_of]
        if not published:
            continue
        year = max(published)
        earnings, count = ni[year], shares.get(year)
        if earnings <= 0 or count is None or count <= 0:
            continue
        out.append(float(close) * count / earnings)
    return out


def percentile_of(values: list[float], x: float) -> float | None:
    """Share of `values` at or below x. None when there is no distribution."""
    if not values:
        return None
    return sum(1 for v in values if v <= x) / len(values)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/analysis/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): point-in-time own trailing P/E history"
```

---

## Task 4: Exit multiple anchor

**Files:**
- Modify: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

HBL's own 3-year median P/E is 74.3x — a 2023-26 Indian smallcap bull-regime artifact that would wreck the forecast if used raw. Hence the peer-relative cap and the absolute clamp, both recorded.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
def test_anchor_blends_peer_and_own_with_quality_premium():
    from mbe.analysis.forecast import build_anchor

    a = build_anchor(
        peer_pes=[20.0, 22.0, 24.0], own_pes=[25.0, 30.0, 35.0],
        current_pe=25.0, franchise_score=50.0,
    )
    assert a.peer_pe == pytest.approx(22.0)
    assert a.peer_n == 3
    assert a.own_pe_median == pytest.approx(30.0)
    # 1.5 * 22 = 33 > 30, so the cap does not bind
    assert a.own_pe_capped == pytest.approx(30.0)
    assert a.quality_multiplier == pytest.approx(0.85 + 0.35 * 0.5)
    # (0.6 * 22 + 0.4 * 30) * 1.025 = 25.2 * 1.025
    assert a.anchor == pytest.approx(25.2 * 1.025)
    assert a.own_pe_percentile_now == pytest.approx(1 / 3)


def test_anchor_caps_regime_inflated_own_history_against_peers():
    """HBL's real shape: own 3y median 74x against a ~22x peer median."""
    from mbe.analysis.forecast import build_anchor

    a = build_anchor(
        peer_pes=[20.0, 22.0, 24.0], own_pes=[74.3], current_pe=25.2,
        franchise_score=91.7,
    )
    assert a.own_pe_capped == pytest.approx(1.5 * 22.0)
    assert any("capped" in n for n in a.notes)
    raw = 0.6 * 22.0 + 0.4 * 33.0
    assert a.anchor == pytest.approx(raw * (0.85 + 0.35 * 0.917))


def test_anchor_clamped_to_bounds_and_noted():
    from mbe.analysis.forecast import ANCHOR_MAX, build_anchor

    a = build_anchor(
        peer_pes=[70.0, 75.0, 78.0], own_pes=[80.0], current_pe=75.0,
        franchise_score=100.0,
    )
    assert a.anchor == pytest.approx(ANCHOR_MAX)
    assert any("clamped" in n for n in a.notes)


def test_anchor_filters_insane_peer_multiples():
    from mbe.analysis.forecast import build_anchor

    a = build_anchor(
        peer_pes=[2.0, 20.0, 22.0, 500.0], own_pes=[25.0],
        current_pe=20.0, franchise_score=50.0,
    )
    assert a.peer_n == 2          # 2.0 and 500.0 rejected
    assert a.peer_pe == pytest.approx(21.0)


def test_anchor_falls_back_to_single_source():
    from mbe.analysis.forecast import build_anchor

    peers_only = build_anchor([20.0, 22.0], [], None, 50.0)
    assert peers_only.anchor == pytest.approx(21.0 * 1.025)
    assert any("own-history" in n for n in peers_only.notes)

    own_only = build_anchor([], [28.0, 32.0], 30.0, 50.0)
    assert own_only.anchor == pytest.approx(30.0 * 1.025)
    assert any("peer" in n for n in own_only.notes)


def test_anchor_absent_when_no_multiple_source():
    from mbe.analysis.forecast import build_anchor

    a = build_anchor([], [], None, 50.0)
    assert a.anchor is None
    assert any("neither" in n for n in a.notes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_anchor'`

- [ ] **Step 3: Implement `build_anchor`**

Add to `src/mbe/analysis/forecast.py` (import `MultipleAnchor` from `mbe.models.forecast` at the top):

```python
def build_anchor(
    peer_pes: list[float],
    own_pes: list[float],
    current_pe: float | None,
    franchise_score: float,
) -> MultipleAnchor:
    """Base-case exit multiple, blended from what peers trade at, what this
    stock has traded at, and how good the business is.

    The own-history term is capped against the peer median because our price
    window is short and regime-bound: a name whose own median is 74x in a
    three-year bull run has not earned a 74x exit assumption.
    """
    notes: list[str] = []
    usable = [p for p in peer_pes if PEER_PE_MIN <= p <= PEER_PE_MAX]
    peer_pe = float(median(usable)) if usable else None
    own_pe = float(median(own_pes)) if own_pes else None
    pctile = percentile_of(own_pes, current_pe) if current_pe is not None else None
    quality_multiplier = 0.85 + 0.35 * (franchise_score / 100.0)

    own_capped: float | None = None
    if peer_pe is not None and own_pe is not None:
        own_capped = min(own_pe, OWN_PE_CAP_VS_PEER * peer_pe)
        if own_capped < own_pe:
            notes.append(
                f"own-history P/E median {own_pe:.1f}x capped to {own_capped:.1f}x "
                f"({OWN_PE_CAP_VS_PEER:g}x the peer median) — our price window is "
                "short and covers one regime"
            )
        raw = 0.6 * peer_pe + 0.4 * own_capped
    elif peer_pe is not None:
        raw = peer_pe
        notes.append("no own-history P/E available — anchored on peers alone")
    elif own_pe is not None:
        raw = min(own_pe, ANCHOR_MAX)
        notes.append("no peer P/E available — anchored on own history alone")
    else:
        notes.append("neither peer nor own-history P/E available — no anchor")
        return MultipleAnchor(
            own_pe_percentile_now=pctile,
            quality_multiplier=quality_multiplier,
            notes=notes,
        )

    anchor = raw * quality_multiplier
    clamped = min(max(anchor, ANCHOR_MIN), ANCHOR_MAX)
    if clamped != anchor:
        notes.append(
            f"anchor {anchor:.1f}x clamped to {clamped:.1f}x "
            f"(bounds {ANCHOR_MIN:g}x-{ANCHOR_MAX:g}x)"
        )
    return MultipleAnchor(
        peer_pe=peer_pe,
        peer_n=len(usable),
        own_pe_median=own_pe,
        own_pe_percentile_now=pctile,
        own_pe_capped=own_capped,
        quality_multiplier=quality_multiplier,
        anchor=clamped,
        notes=notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/analysis/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): exit-multiple anchor from peers, own history and quality"
```

---

## Task 5: Growth and margin paths

**Files:**
- Modify: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

The margin path is where "was the latest year a peak, or the new normal?" gets argued explicitly rather than buried in a smoothed input. Growth is driven by revenue CAGR alone — never the v0.1 median across revenue/profit/FCF CAGRs, which mixed non-comparable series (HBL: 34.5% / 102.1% / 115.8%).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
def test_fade_is_linear_and_inclusive():
    from mbe.analysis.forecast import fade

    assert fade(0.30, 0.10, 3) == pytest.approx([0.30, 0.20, 0.10])
    assert fade(0.10, 0.10, 3) == pytest.approx([0.10, 0.10, 0.10])


def test_growth_paths_ordered_and_driven_by_revenue_cagr():
    from mbe.analysis.forecast import growth_paths

    paths = growth_paths(g0=0.345, g_term=0.10, spiked=False)
    assert paths["base"] == (pytest.approx(0.345), pytest.approx(0.10))
    # bull holds growth up: it fades only to 70% of the start
    assert paths["bull"][1] == pytest.approx(0.345 * 0.7)
    # bear starts at 40% of delivered growth and ends at half the terminal rate
    assert paths["bear"] == (pytest.approx(0.345 * 0.4), pytest.approx(0.05))
    assert paths["bear"][0] < paths["base"][0] <= paths["bull"][0]


def test_spiked_earnings_produce_a_harsher_bear_start():
    from mbe.analysis.forecast import growth_paths

    normal = growth_paths(g0=0.345, g_term=0.10, spiked=False)
    spiked = growth_paths(g0=0.345, g_term=0.10, spiked=True)
    assert spiked["bear"][0] < normal["bear"][0]
    assert spiked["base"] == normal["base"]   # only the bear path tightens


def test_growth_start_capped_and_floored():
    from mbe.analysis.forecast import GROWTH_CAP, growth_paths

    assert growth_paths(g0=0.90, g_term=0.10, spiked=False)["base"][0] == pytest.approx(
        GROWTH_CAP
    )
    assert growth_paths(g0=-0.20, g_term=0.10, spiked=False)["base"][0] == pytest.approx(
        0.0
    )


def test_terminal_growth_clamped_with_fallback():
    from mbe.analysis.forecast import (
        TERMINAL_GROWTH_FALLBACK, TERMINAL_GROWTH_MAX, TERMINAL_GROWTH_MIN,
        terminal_growth,
    )

    assert terminal_growth([]) == pytest.approx(TERMINAL_GROWTH_FALLBACK)
    assert terminal_growth([0.11, 0.12, 0.13]) == pytest.approx(0.12)
    assert terminal_growth([0.40, 0.45]) == pytest.approx(TERMINAL_GROWTH_MAX)
    assert terminal_growth([-0.05, 0.0]) == pytest.approx(TERMINAL_GROWTH_MIN)


def test_margin_paths_argue_peak_versus_new_normal():
    from mbe.analysis.forecast import margin_paths

    # HBL shape: latest 24.7%, 3y mean 17.1%, best ever 24.7%
    m = margin_paths(m0=0.247, m3=0.171, m_best=0.247)
    assert m["bull"] == pytest.approx(0.247)              # capped by own best
    assert m["base"] == pytest.approx((0.247 + 0.171) / 2)
    assert m["bear"] == pytest.approx(0.171)              # full reversion
    assert m["bear"] < m["base"] < m["bull"]


def test_bull_margin_expansion_capped_by_own_best_year():
    from mbe.analysis.forecast import margin_paths

    m = margin_paths(m0=0.20, m3=0.18, m_best=0.30)
    assert m["bull"] == pytest.approx(0.21)   # 0.20 * 1.05, below the 0.30 ceiling


def test_bear_margin_takes_the_worse_of_latest_and_mean():
    """A business improving off a low base must not have its bear case set
    above where it currently is."""
    from mbe.analysis.forecast import margin_paths

    m = margin_paths(m0=0.10, m3=0.16, m_best=0.16)
    assert m["bear"] == pytest.approx(0.10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ImportError: cannot import name 'fade'`

- [ ] **Step 3: Implement the path builders**

Add to `src/mbe/analysis/forecast.py`:

```python
def fade(start: float, end: float, years: int) -> list[float]:
    """Linear fade from start to end, inclusive of both endpoints."""
    if years <= 1:
        return [end]
    return [start + (end - start) * i / (years - 1) for i in range(years)]


def terminal_growth(peer_growths: list[float]) -> float:
    """The rate growth fades toward: the peer median, clamped to a plausible
    band. Falls back to a fixed rate when there is no peer set (single-ticker
    path), which is why the fallback is stated rather than silently zero.
    """
    present = [g for g in peer_growths if g is not None]
    if not present:
        return TERMINAL_GROWTH_FALLBACK
    return min(max(float(median(present)), TERMINAL_GROWTH_MIN), TERMINAL_GROWTH_MAX)


def growth_paths(
    g0: float, g_term: float, spiked: bool
) -> dict[str, tuple[float, float]]:
    """(start, end) revenue growth per scenario.

    Driven by delivered revenue CAGR alone. v0.1 took a median across
    revenue/profit/FCF CAGRs — non-comparable series whose median then had to
    be clipped to 25%, which made the report's "delivered-growth median" label
    false and capped every bull case at 30%.
    """
    start = min(max(g0, 0.0), GROWTH_CAP)
    bear_mult = BEAR_GROWTH_MULT_SPIKED if spiked else BEAR_GROWTH_MULT
    return {
        "bull": (start, max(start * 0.7, g_term)),
        "base": (start, g_term),
        "bear": (start * bear_mult, g_term * 0.5),
    }


def margin_paths(m0: float, m3: float, m_best: float) -> dict[str, float]:
    """Terminal net margin per scenario.

    This is where "was the latest year a peak, or the new normal?" is argued
    explicitly: bull treats it as the new normal, base splits the difference
    with the 3-year mean, bear reverts fully.
    """
    return {
        "bull": min(m0 * 1.05, m_best),
        "base": (m0 + m3) / 2,
        "bear": min(m0, m3),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/analysis/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): revenue and margin scenario paths

Growth is driven by delivered revenue CAGR alone rather than a median across
non-comparable series, and the margin path carries the peak-versus-new-normal
question explicitly instead of burying it in a smoothed input."
```

---

## Task 6: Target projection and the two-sided guard

**Files:**
- Modify: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

Stacking every knob at its optimum produced a bull target of 5x in three years for HBL — the same failure as v0.1 with the sign flipped. The guard trims the bull exit multiple, but never below the base multiple, since that would invert the scenarios.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
def test_project_compounds_revenue_and_dilution():
    from mbe.analysis.forecast import project

    p = project(
        revenue_0=1000.0, growth_path=[0.20, 0.15, 0.10], margin=0.20,
        shares_0=10.0, share_cagr=0.0, exit_multiple=20.0, price=40.0,
    )
    revenue = 1000.0 * 1.20 * 1.15 * 1.10
    assert p.revenue_fy3 == pytest.approx(revenue)
    assert p.eps_fy3 == pytest.approx(revenue * 0.20 / 10.0)
    assert p.target_price == pytest.approx(revenue * 0.20 / 10.0 * 20.0)
    assert p.cagr_3y == pytest.approx((p.target_price / 40.0) ** (1 / 3) - 1)


def test_project_dilution_reduces_eps():
    from mbe.analysis.forecast import project

    clean = project(1000.0, [0.10] * 3, 0.20, 10.0, 0.00, 20.0, 40.0)
    diluting = project(1000.0, [0.10] * 3, 0.20, 10.0, 0.05, 20.0, 40.0)
    assert diluting.eps_fy3 < clean.eps_fy3


def test_bull_guard_trims_exit_multiple_and_records_it():
    from mbe.analysis.forecast import BULL_CAGR_CAP, apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=75.0, exit_multiple=49.0, base_exit_multiple=35.0, price=741.9
    )
    cagr = (75.0 * trimmed / 741.9) ** (1 / 3) - 1
    assert cagr == pytest.approx(BULL_CAGR_CAP, abs=1e-6)
    assert trimmed < 49.0
    assert any("trimmed" in e for e in evidence)


def test_bull_guard_never_inverts_scenario_ordering():
    """If the cap cannot be met even at the base multiple, the earnings path
    alone implies a tripling — surface it, do not clamp below base."""
    from mbe.analysis.forecast import apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=500.0, exit_multiple=49.0, base_exit_multiple=35.0, price=100.0
    )
    assert trimmed == pytest.approx(35.0)
    assert any("could not" in e for e in evidence)


def test_bull_guard_is_a_no_op_below_the_cap():
    from mbe.analysis.forecast import apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=10.0, exit_multiple=20.0, base_exit_multiple=15.0, price=150.0
    )
    assert trimmed == pytest.approx(20.0)
    assert evidence == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ImportError: cannot import name 'project'`

- [ ] **Step 3: Implement projection and the guard**

Add to `src/mbe/analysis/forecast.py` (add `from dataclasses import dataclass` to the imports):

```python
@dataclass(frozen=True)
class Projection:
    revenue_fy3: float
    eps_fy3: float
    target_price: float
    cagr_3y: float


def project(
    revenue_0: float,
    growth_path: list[float],
    margin: float,
    shares_0: float,
    share_cagr: float,
    exit_multiple: float,
    price: float,
) -> Projection:
    """Compound revenue along the growth path, apply the terminal margin and
    projected share count, then the exit multiple."""
    revenue = revenue_0
    for g in growth_path:
        revenue *= 1 + g
    shares = shares_0 * (1 + max(share_cagr, 0.0)) ** HORIZON_YEARS
    eps = revenue * margin / shares
    target = eps * exit_multiple
    return Projection(
        revenue_fy3=revenue,
        eps_fy3=eps,
        target_price=target,
        cagr_3y=(target / price) ** (1 / HORIZON_YEARS) - 1 if price > 0 else 0.0,
    )


def apply_bull_guard(
    eps_fy3: float, exit_multiple: float, base_exit_multiple: float, price: float
) -> tuple[float, list[str]]:
    """Keep the bull case from stacking every knob at its optimum.

    Sustained growth AND expanded margins AND a full re-rating compound into
    fantasy (5x in three years, measured on HBLENGINE.NS) — the mirror image of
    the v0.1 failure. One knob is trimmed, the exit multiple, and the trim is
    reported. It never goes below the base case's multiple: that would invert
    the scenario ordering, and a bull case still above the cap at the base
    multiple is a finding about the earnings path, not something to hide.
    """
    if price <= 0 or eps_fy3 <= 0:
        return exit_multiple, []
    cagr = (eps_fy3 * exit_multiple / price) ** (1 / HORIZON_YEARS) - 1
    if cagr <= BULL_CAGR_CAP:
        return exit_multiple, []
    needed = price * (1 + BULL_CAGR_CAP) ** HORIZON_YEARS / eps_fy3
    if needed < base_exit_multiple:
        return base_exit_multiple, [
            f"bull {cagr:.0%}/yr exceeds the {BULL_CAGR_CAP:.0%}/yr sanity bound and "
            f"could not be trimmed to it without dropping the bull exit multiple "
            f"below the base case's {base_exit_multiple:.1f}x — the earnings path "
            f"alone implies this move"
        ]
    return needed, [
        f"bull exit multiple trimmed {exit_multiple:.1f}x -> {needed:.1f}x to respect "
        f"the {BULL_CAGR_CAP:.0%}/yr sanity bound"
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/analysis/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): target projection with a two-sided sanity guard"
```

---

## Task 7: Probabilities and expected value

**Files:**
- Modify: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

Weights come from evidence the engine already computes, not from thin air: mean assumption support (the same quantity `build_thesis` uses for `thesis_confidence`) and franchise score.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
def test_probabilities_sum_to_one_and_track_quality():
    from mbe.analysis.forecast import scenario_probabilities

    strong = scenario_probabilities(0.87, 91.7, veto=False)   # HBL's real inputs
    weak = scenario_probabilities(0.35, 20.0, veto=False)
    for p in (strong, weak):
        assert sum(p.values()) == pytest.approx(1.0)
        assert all(v >= 0 for v in p.values())
    assert strong["bull"] > weak["bull"]
    assert strong["bear"] < weak["bear"]
    assert strong["bull"] == pytest.approx(0.368, abs=0.002)
    assert strong["bear"] == pytest.approx(0.177, abs=0.002)


def test_veto_shifts_weight_from_bull_to_bear():
    from mbe.analysis.forecast import scenario_probabilities

    clean = scenario_probabilities(0.80, 80.0, veto=False)
    vetoed = scenario_probabilities(0.80, 80.0, veto=True)
    assert vetoed["bull"] == pytest.approx(clean["bull"] - 0.15)
    assert vetoed["bear"] == pytest.approx(clean["bear"] + 0.15)
    assert sum(vetoed.values()) == pytest.approx(1.0)


def test_veto_cannot_drive_bull_probability_negative():
    from mbe.analysis.forecast import scenario_probabilities

    p = scenario_probabilities(0.0, 0.0, veto=True)
    assert p["bull"] >= 0.0
    assert sum(p.values()) == pytest.approx(1.0)


def test_expected_value_is_computed_on_prices_not_by_averaging_cagrs():
    """CAGR is non-linear in price, so averaging CAGRs is not the same thing.
    A wide spread makes the two answers differ measurably."""
    from mbe.analysis.forecast import expected_outcome

    targets = {"bull": 4000.0, "base": 1000.0, "bear": 250.0}
    probs = {"bull": 0.3, "base": 0.5, "bear": 0.2}
    exp_target, exp_cagr, downside = expected_outcome(targets, probs, price=1000.0)

    assert exp_target == pytest.approx(0.3 * 4000 + 0.5 * 1000 + 0.2 * 250)
    assert exp_cagr == pytest.approx((exp_target / 1000.0) ** (1 / 3) - 1)
    naive = sum(
        probs[k] * ((targets[k] / 1000.0) ** (1 / 3) - 1) for k in targets
    )
    assert exp_cagr != pytest.approx(naive, abs=1e-4)
    assert downside == pytest.approx(0.2)


def test_downside_probability_counts_every_scenario_below_price():
    from mbe.analysis.forecast import expected_outcome

    targets = {"bull": 1200.0, "base": 900.0, "bear": 500.0}
    probs = {"bull": 0.3, "base": 0.5, "bear": 0.2}
    _, _, downside = expected_outcome(targets, probs, price=1000.0)
    assert downside == pytest.approx(0.7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ImportError: cannot import name 'scenario_probabilities'`

- [ ] **Step 3: Implement probabilities and expected value**

Add to `src/mbe/analysis/forecast.py`:

```python
VETO_SHIFT = 0.15


def scenario_probabilities(
    mean_assumption_support: float, franchise_score: float, veto: bool
) -> dict[str, float]:
    """Weights drawn from evidence the engine already computes: how often this
    company's own assumptions have held, and how durable the franchise looks.
    A vetoed thesis moves weight from bull to bear.
    """
    quality = 0.5 * mean_assumption_support + 0.5 * (franchise_score / 100.0)
    p_bull = 0.10 + 0.30 * quality
    p_bear = 0.40 - 0.25 * quality
    if veto:
        shift = min(VETO_SHIFT, p_bull)
        p_bull -= shift
        p_bear += shift
    return {"bull": p_bull, "base": 1.0 - p_bull - p_bear, "bear": p_bear}


def expected_outcome(
    targets: dict[str, float], probs: dict[str, float], price: float
) -> tuple[float | None, float | None, float]:
    """Returns (expected_target, expected_cagr_3y, downside_probability).

    The expectation is taken over *prices* and only then annualised. Averaging
    the scenario CAGRs directly would be a different — and wrong — number,
    because CAGR is non-linear in price.
    """
    expected_target = sum(probs[name] * targets[name] for name in targets)
    downside = sum(probs[name] for name in targets if targets[name] < price)
    if price <= 0 or expected_target <= 0:
        return expected_target or None, None, downside
    return (
        expected_target,
        (expected_target / price) ** (1 / HORIZON_YEARS) - 1,
        downside,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/analysis/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): evidence-derived scenario probabilities and expected value"
```

---

## Task 8: Assemble the forecast

**Files:**
- Modify: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

`build_forecast` takes a completed `AnalysisBundle` because it needs `business.franchise_score`, `thesis.assumptions` and `critique.veto` — all of which exist only after `analyze_ticker` finishes. Import `AnalysisBundle` under `TYPE_CHECKING` to avoid the runtime cycle, exactly as `analysis/sector.py:24` does.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
@pytest.fixture
def hbl_bundle():
    """HBL Engineering's real shape: revenue +68% and net margin 12.6% -> 24.7%
    in FY26, debt-free, no dilution."""
    from mbe.analysis.business import assess_business
    from mbe.analysis.risk import assess_risk
    from mbe.analysis.technicals import compute_technicals
    from mbe.pipeline import AnalysisBundle
    from mbe.scoring.engine import build_scorecard
    from mbe.thesis.engine import build_thesis, critique_thesis

    years = [2023, 2024, 2025, 2026]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, [1357.6, 2221.5, 1967.2, 3302.8])),
            "gross_profit": dict(zip(years, [376.1, 736.8, 996.3, 1921.1])),
            "operating_income": dict(zip(years, [116.6, 383.9, 347.9, 1062.4])),
            "ebitda": dict(zip(years, [171.0, 427.3, 417.2, 1140.7])),
            "net_income": dict(zip(years, [98.7, 280.9, 276.9, 814.9])),
            "interest_expense": dict(zip(years, [5.7, 9.3, 13.0, 14.7])),
            "cfo": dict(zip(years, [122.4, 270.3, 246.7, 738.4])),
            "capex": dict(zip(years, [63.9, 74.1, 152.8, 150.3])),
            "fcf": dict(zip(years, [58.6, 196.2, 93.9, 588.1])),
            "shares_diluted": dict(zip(years, [27.7, 27.7, 27.8, 27.7])),
            "total_assets": dict(zip(years, [1294.2, 1654.1, 1979.5, 2941.7])),
            "total_equity": dict(zip(years, [951.4, 1220.5, 1482.7, 2214.2])),
            "total_debt": dict(zip(years, [86.0, 67.5, 74.3, 66.9])),
            "cash": dict(zip(years, [132.0, 223.5, 117.0, 528.2])),
            "current_assets": dict(zip(years, [800.0, 1000.0, 1200.0, 2025.0])),
            "current_liabilities": dict(zip(years, [300.0, 350.0, 400.0, 567.0])),
        }
    )
    info = CompanyInfo(
        ticker="HBLTEST.NS", name="HBL Test", sector="Industrials",
        industry="Electrical Equipment & Parts",
        market_cap=20574.0, shares_outstanding=27.7, price=741.9,
    )
    dates = pd.date_range("2023-08-01", periods=740, freq="B")
    closes = [400.0 + i * 0.6 for i in range(740)]
    prices = PriceHistory(
        df=pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1e6] * 740},
            index=dates,
        )
    )
    fund = compute_fundamentals(fin, info)
    tech = compute_technicals(prices, None)
    val = compute_valuation(fin, info, fund, price=741.9)
    risk = assess_risk(fin, fund, tech, val, info)
    card = build_scorecard(info, fund, tech, val, risk, fin, price_days=len(prices.df))
    business = assess_business(fin, info, fund)
    thesis = build_thesis(info, fund, business, val, risk)
    critique = critique_thesis(thesis, fund, business, val, risk)
    return AnalysisBundle(
        info=info, fin=fin, fund=fund, tech=tech, val=val, risk=risk, card=card,
        as_of=date(2026, 7, 20), business=business, thesis=thesis, critique=critique,
        prices=prices,
    )


def test_build_forecast_produces_ordered_positive_scenarios(hbl_bundle):
    from mbe.analysis.forecast import build_forecast

    fc = build_forecast(hbl_bundle, peer_pes=[20.0, 22.0, 24.0, 26.0],
                        peer_growths=[0.12, 0.14, 0.10, 0.16])
    assert fc is not None
    assert fc.base_fiscal_year == 2026
    assert [s.name for s in fc.scenarios] == ["bull", "base", "bear"]
    bull, base, bear = fc.scenarios
    assert bear.target_price < base.target_price < bull.target_price
    assert fc.expected_cagr_3y is not None
    assert sum(s.probability for s in fc.scenarios) == pytest.approx(1.0)
    # the whole point: a debt-free 33% ROCE compounder at its cheapest multiple
    # in three years must not show downside in its base case
    assert base.cagr_3y > 0
    assert all(s.evidence for s in fc.scenarios)


def test_build_forecast_degrades_without_peers(hbl_bundle):
    from mbe.analysis.forecast import build_forecast

    with_peers = build_forecast(hbl_bundle, [20.0, 22.0, 24.0], [0.12, 0.14])
    without = build_forecast(hbl_bundle, [], [])
    assert without is not None
    assert without.completeness < with_peers.completeness
    assert without.anchor.peer_pe is None
    assert any("peer" in n for n in without.anchor.notes)


def test_build_forecast_returns_none_without_any_multiple_source(hbl_bundle):
    """No peers and no usable own P/E history means no anchor, and a forecast
    with no anchor is not a forecast."""
    from mbe.analysis.forecast import build_forecast

    hbl_bundle.prices = PriceHistory(
        df=pd.DataFrame(
            {"open": [], "high": [], "low": [], "close": [], "volume": []},
            index=pd.to_datetime([]),
        )
    )
    assert build_forecast(hbl_bundle, [], []) is None


def test_build_forecast_bear_is_harsher_for_a_spiked_earner(hbl_bundle):
    from mbe.analysis.forecast import build_forecast

    spiked = build_forecast(hbl_bundle, [20.0, 22.0, 24.0], [0.12])
    # flatten the step change: same latest year, no spike
    steady = hbl_bundle.model_copy(deep=True)
    steady.fin.data["net_income"] = {2023: 600.0, 2024: 680.0, 2025: 740.0, 2026: 814.9}
    steady.fin.data["fcf"] = {2023: 430.0, 2024: 490.0, 2025: 530.0, 2026: 588.1}
    steady.fund = compute_fundamentals(steady.fin, steady.info)
    steady.val = compute_valuation(steady.fin, steady.info, steady.fund, price=741.9)
    steady_fc = build_forecast(steady, [20.0, 22.0, 24.0], [0.12])
    spiked_bear = next(s for s in spiked.scenarios if s.name == "bear")
    steady_bear = next(s for s in steady_fc.scenarios if s.name == "bear")
    assert spiked_bear.growth_start < steady_bear.growth_start
```

By this task `tests/test_forecast.py` needs these at module level. Consolidate the imports at the top of the file to exactly:

```python
from datetime import date

import pandas as pd
import pytest

from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.valuation import compute_valuation
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath
```

Then delete the now-redundant inline `import pandas as pd` and `from datetime import date` statements added inside earlier tasks' tests. The per-test `from mbe.analysis.forecast import ...` lines stay as they are — each task's tests import only the function they are driving out, which keeps the tasks independently runnable.

- [ ] **Step 2: Add `prices` to `AnalysisBundle`**

`build_forecast` needs the price history for the own-P/E series, and `AnalysisBundle` does not currently carry it. In `src/mbe/pipeline.py`, add to the `AnalysisBundle` class body (alongside `fin`, after the `tech` field):

```python
    prices: PriceHistory | None = None
```

and add `PriceHistory` to the existing `from mbe.models.company import CompanyInfo, FinancialHistory` import. Then in `analyze_ticker`'s return statement, pass it:

```python
        info=info, fin=fin, fund=fund, tech=tech, val=val, risk=risk, prices=prices,
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_forecast'`

- [ ] **Step 4: Implement `build_forecast`**

Add to `src/mbe/analysis/forecast.py`. Extend the imports at the top with:

```python
from typing import TYPE_CHECKING

from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath

if TYPE_CHECKING:  # avoid a runtime cycle: pipeline imports this module
    from mbe.pipeline import AnalysisBundle
```

Then:

```python
def _mean_assumption_support(bundle: "AnalysisBundle") -> float:
    """Mean historical support across the thesis assumptions — the same
    quantity build_thesis uses for thesis_confidence. 0.5 when unknown, so an
    unmeasurable company sits at the midpoint rather than at either extreme."""
    if bundle.thesis is None or not bundle.thesis.assumptions:
        return 0.5
    supports = [a.historical_support for a in bundle.thesis.assumptions]
    return sum(supports) / len(supports)


def _net_margins(fin: FinancialHistory) -> list[tuple[int, float]]:
    revenue = dict(fin.series("revenue"))
    return [
        (year, ni / revenue[year])
        for year, ni in fin.series("net_income")
        if revenue.get(year) not in (None, 0)
    ]


def build_forecast(
    bundle: "AnalysisBundle", peer_pes: list[float], peer_growths: list[float]
) -> PriceForecast | None:
    """Three-year bull/base/bear target prices for one company.

    Returns None when no exit multiple can be anchored — neither peers nor a
    usable own-P/E history. A forecast without an anchor would be arithmetic
    dressed up as a view.
    """
    fin, info, fund, val = bundle.fin, bundle.info, bundle.fund, bundle.val
    price = val.price
    margins = _net_margins(fin)
    revenue_0 = fin.latest("revenue")
    shares_0 = fin.latest("shares_diluted") or info.shares_outstanding
    if not margins or not revenue_0 or not shares_0 or price <= 0:
        return None

    base_year, m0 = margins[-1]
    recent = [m for _, m in margins[-3:]]
    m3 = sum(recent) / len(recent)
    m_best = max(m for _, m in margins)

    own_pes = (
        own_pe_series(bundle.prices, fin, info) if bundle.prices is not None else []
    )
    franchise = bundle.business.franchise_score if bundle.business else 0.0
    anchor = build_anchor(peer_pes, own_pes, val.pe, franchise)
    if anchor.anchor is None:
        return None

    spike = val.assumptions.get("fcf_spike_ratio")
    ni_recent = [ni for _, ni in fin.series("net_income")[-3:]]
    ni_mean = sum(ni_recent) / len(ni_recent) if ni_recent else 0.0
    ni_latest = fin.latest("net_income") or 0.0
    spiked = (ni_mean > 0 and ni_latest / ni_mean >= SPIKE_THRESHOLD) or (
        spike is not None and spike == spike and spike >= SPIKE_THRESHOLD
    )

    g_term = terminal_growth(peer_growths)
    growth = growth_paths(fund.revenue_cagr_3y or 0.0, g_term, spiked)
    margin = margin_paths(m0, m3, m_best)
    probs = scenario_probabilities(
        _mean_assumption_support(bundle),
        franchise,
        veto=bool(bundle.critique and bundle.critique.veto),
    )
    multiples = {
        "bull": anchor.anchor * MULT_BULL,
        "base": anchor.anchor * MULT_BASE,
        "bear": anchor.anchor * MULT_BEAR,
    }
    share_cagr = fund.share_count_cagr_3y or 0.0

    scenarios: list[ScenarioPath] = []
    targets: dict[str, float] = {}
    for name in ("bull", "base", "bear"):
        start, end = growth[name]
        path = fade(start, end, HORIZON_YEARS)
        exit_multiple = multiples[name]
        p = project(revenue_0, path, margin[name], shares_0, share_cagr,
                    exit_multiple, price)
        evidence = [
            f"revenue grows {start:.0%} fading to {end:.0%} over {HORIZON_YEARS} years",
            f"net margin ends at {margin[name]:.1%} (latest {m0:.1%}, "
            f"3y mean {m3:.1%})",
            f"exits at {exit_multiple:.1f}x earnings "
            f"({exit_multiple / anchor.anchor:.1f}x the {anchor.anchor:.1f}x anchor)",
        ]
        if name == "bull":
            exit_multiple, guard_notes = apply_bull_guard(
                p.eps_fy3, exit_multiple, multiples["base"], price
            )
            if guard_notes:
                p = project(revenue_0, path, margin[name], shares_0, share_cagr,
                            exit_multiple, price)
                evidence[-1] = f"exits at {exit_multiple:.1f}x earnings"
                evidence.extend(guard_notes)
        if spiked and name == "bear":
            evidence.append(
                f"latest earnings are {ni_latest / ni_mean:.1f}x their 3y mean, so "
                "this bear path assumes the step change does not repeat"
            )
        scenarios.append(ScenarioPath(
            name=name, probability=probs[name], growth_start=start, growth_end=end,
            terminal_net_margin=margin[name], exit_multiple=exit_multiple,
            revenue_fy3=p.revenue_fy3, eps_fy3=p.eps_fy3,
            target_price=p.target_price, cagr_3y=p.cagr_3y, evidence=evidence,
        ))
        targets[name] = p.target_price

    expected_target, expected_cagr, downside = expected_outcome(targets, probs, price)
    present = [
        anchor.peer_pe is not None,
        bool(own_pes),
        fund.revenue_cagr_3y is not None,
        True,                                   # net margin, guaranteed above
        fin.latest("shares_diluted") is not None,
        bundle.business is not None,
        bundle.thesis is not None and bool(bundle.thesis.assumptions),
    ]
    return PriceForecast(
        ticker=info.ticker, base_fiscal_year=base_year, price=price, anchor=anchor,
        scenarios=scenarios, expected_target=expected_target,
        expected_cagr_3y=expected_cagr, downside_probability=downside,
        completeness=sum(present) / len(present),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS. If `test_build_forecast_produces_ordered_positive_scenarios` fails on `base.cagr_3y > 0`, do **not** relax the assertion — print the scenario evidence and check whether the anchor is being clamped by `ANCHOR_MAX`, which is the parameter the spec flags as the least certain.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/analysis/forecast.py src/mbe/pipeline.py tests/test_forecast.py
git commit -m "feat(forecast): assemble 3-year bull/base/bear target prices"
```

---

## Task 9: Coherence flags

**Files:**
- Modify: `src/mbe/analysis/forecast.py`
- Test: `tests/test_forecast.py`

These are the sanity checks that make the original failure impossible to repeat silently. They live here, not in `risk.py`, because `assess_risk` runs before the forecast exists and receives no price history.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_forecast.py`:

```python
def test_multiple_at_low_fires_at_the_bottom_of_own_history(hbl_bundle):
    """HBL today: trailing P/E 25.2x against a 3y median of 74.3x — the
    cheapest it has been in the whole window."""
    from mbe.analysis.forecast import build_forecast, forecast_flags

    fc = build_forecast(hbl_bundle, [20.0, 22.0, 24.0], [0.12])
    fc.anchor.own_pe_percentile_now = 0.02
    codes = [f.code for f in forecast_flags(hbl_bundle, fc)]
    assert "MULTIPLE_AT_LOW" in codes

    fc.anchor.own_pe_percentile_now = 0.60
    assert "MULTIPLE_AT_LOW" not in [f.code for f in forecast_flags(hbl_bundle, fc)]


def test_earnings_spike_flag_fires_and_is_informational(hbl_bundle):
    from mbe.analysis.forecast import build_forecast, forecast_flags

    fc = build_forecast(hbl_bundle, [20.0, 22.0, 24.0], [0.12])
    spike = [f for f in forecast_flags(hbl_bundle, fc) if f.code == "EARNINGS_SPIKE"]
    assert len(spike) == 1
    assert spike[0].severity == 1


def test_forecast_incoherent_fires_when_bull_is_below_the_market(hbl_bundle):
    """The exact v0.1 failure: the model's most optimistic case sits below what
    the market already pays for. That is a model error, not a finding."""
    from mbe.analysis.forecast import build_forecast, forecast_flags

    fc = build_forecast(hbl_bundle, [20.0, 22.0, 24.0], [0.12])
    hbl_bundle.val.implied_growth = 0.90     # market prices 90% growth
    bull = next(s for s in fc.scenarios if s.name == "bull")
    assert bull.growth_start < 0.90
    codes = [f.code for f in forecast_flags(hbl_bundle, fc)]
    assert "FORECAST_INCOHERENT" in codes

    hbl_bundle.val.implied_growth = 0.05
    assert "FORECAST_INCOHERENT" not in [
        f.code for f in forecast_flags(hbl_bundle, fc)
    ]


def test_coherence_flags_do_not_change_risk_score(hbl_bundle):
    from mbe.analysis.forecast import build_forecast, forecast_flags

    before = hbl_bundle.risk.risk_score
    fc = build_forecast(hbl_bundle, [20.0, 22.0, 24.0], [0.12])
    hbl_bundle.risk.flags.extend(forecast_flags(hbl_bundle, fc))
    assert hbl_bundle.risk.risk_score == pytest.approx(before)


def test_no_flags_without_a_forecast(hbl_bundle):
    from mbe.analysis.forecast import forecast_flags

    assert forecast_flags(hbl_bundle, None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: FAIL with `ImportError: cannot import name 'forecast_flags'`

- [ ] **Step 3: Implement `forecast_flags`**

Add to `src/mbe/analysis/forecast.py` (add `from mbe.models.analysis import RiskFlag` to the imports):

```python
MULTIPLE_LOW_PERCENTILE = 0.10


def forecast_flags(
    bundle: "AnalysisBundle", forecast: PriceForecast | None
) -> list[RiskFlag]:
    """Coherence checks on the forecast against observable market facts.

    Reported, never scored: risk_score is already computed by the time these
    are known, and the spec keeps the only scoring change confined to
    margin_of_safety. FORECAST_INCOHERENT exists so the v0.1 failure — the
    model's bull case sitting below the growth the market already pays for —
    cannot recur without saying so out loud.
    """
    if forecast is None:
        return []
    flags: list[RiskFlag] = []

    pctile = forecast.anchor.own_pe_percentile_now
    if pctile is not None and pctile <= MULTIPLE_LOW_PERCENTILE:
        flags.append(RiskFlag(
            code="MULTIPLE_AT_LOW", severity=1,
            detail=(
                f"Trades at the {pctile:.0%} percentile of its own multiple history "
                f"(median {forecast.anchor.own_pe_median:.1f}x) — cheap relative to "
                "its own past, not just to peers"
            ),
        ))

    ni_recent = [ni for _, ni in bundle.fin.series("net_income")[-3:]]
    ni_mean = sum(ni_recent) / len(ni_recent) if ni_recent else 0.0
    ni_latest = bundle.fin.latest("net_income") or 0.0
    if ni_mean > 0 and ni_latest / ni_mean >= SPIKE_THRESHOLD:
        flags.append(RiskFlag(
            code="EARNINGS_SPIKE", severity=1,
            detail=(
                f"Latest earnings are {ni_latest / ni_mean:.1f}x their 3y mean — the "
                "bear scenario is load-bearing here"
            ),
        ))

    bull = next((s for s in forecast.scenarios if s.name == "bull"), None)
    implied = bundle.val.implied_growth
    if bull is not None and implied is not None and bull.growth_start < implied:
        flags.append(RiskFlag(
            code="FORECAST_INCOHERENT", severity=2,
            detail=(
                f"Bull case assumes {bull.growth_start:.0%} growth but the market "
                f"already prices {implied:.0%} — the model's most optimistic case is "
                "below consensus, so treat the forecast as understated"
            ),
        ))
    return flags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/mbe/analysis/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): coherence flags so a broken forecast cannot stay silent"
```

---

## Task 10: Pipeline wiring

**Files:**
- Modify: `src/mbe/pipeline.py:36-52` (bundle), `:61-88` (`analyze_ticker`), `:90-109` (`screen`)
- Modify: `src/mbe/analysis/forecast.py` (add `apply_forecasts`)
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py`:

The file already has a `StubProvider` class at `tests/test_pipeline.py:54` that serves every ticker the same statements and prices, and `analyze_ticker` / `screen` are already imported at the top. Use it — do not introduce a second provider style:

```python
def test_screen_populates_forecasts_with_peer_anchors():
    """Four names share StubProvider's industry, so the group clears MIN_GROUP
    and every member gets a leave-one-out peer anchor."""
    result = screen(["A.NS", "B.NS", "C.NS", "D.NS"], StubProvider())
    assert len(result.ranked) == 4
    for bundle in result.ranked:
        assert bundle.forecast is not None
        assert bundle.forecast.anchor.peer_n >= 1
        assert [s.name for s in bundle.forecast.scenarios] == ["bull", "base", "bear"]


def test_analyze_ticker_populates_a_lower_completeness_forecast():
    solo = analyze_ticker("GOOD.NS", StubProvider())
    assert solo.forecast is not None
    assert solo.forecast.anchor.peer_pe is None
    assert solo.forecast.completeness < 1.0
```

If `StubProvider.get_info` does not set an `industry`, the four tickers will not form a group and `peer_n` will be 0. Check `tests/test_pipeline.py:58-65` and, if `industry` is missing, add `industry="Test Industry"` to the `CompanyInfo` it returns — a one-word change that makes the group form.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `AnalysisBundle` has no attribute `forecast`

- [ ] **Step 3: Add the bundle field**

In `src/mbe/pipeline.py`, add to `AnalysisBundle` after `critique`:

```python
    forecast: PriceForecast | None = None
```

and add the import:

```python
from mbe.models.forecast import PriceForecast
```

- [ ] **Step 4: Implement `apply_forecasts`**

Add to `src/mbe/analysis/forecast.py`:

```python
def apply_forecasts(
    bundles: list["AnalysisBundle"], context: "SectorContext"
) -> None:
    """Post-pass: give every bundle a forecast with a leave-one-out peer anchor.

    Cross-sectional by nature, the same contract as analysis/sector.py — the
    same stock legitimately gets a different peer anchor in a different
    universe. Mutates bundles in place and appends coherence flags.
    """
    by_group: dict[str, list["AnalysisBundle"]] = {}
    for bundle in bundles:
        group = context.membership.get(bundle.info.ticker)
        if group is not None:
            by_group.setdefault(group, []).append(bundle)

    for bundle in bundles:
        group = context.membership.get(bundle.info.ticker)
        peers = [
            b for b in by_group.get(group, [])
            if b.info.ticker != bundle.info.ticker
        ] if group is not None else []
        peer_pes = [b.val.pe for b in peers if b.val.pe is not None]
        peer_growths = [
            b.fund.revenue_cagr_3y for b in peers
            if b.fund.revenue_cagr_3y is not None
        ]
        bundle.forecast = build_forecast(bundle, peer_pes, peer_growths)
        bundle.risk.flags.extend(forecast_flags(bundle, bundle.forecast))
```

Add `SectorContext` to the `TYPE_CHECKING` imports:

```python
if TYPE_CHECKING:  # avoid a runtime cycle: pipeline imports this module
    from mbe.models.sector import SectorContext
    from mbe.pipeline import AnalysisBundle
```

- [ ] **Step 5: Wire both pipeline paths**

In `src/mbe/pipeline.py`, add the import:

```python
from mbe.analysis.forecast import apply_forecasts, build_forecast, forecast_flags
```

In `analyze_ticker`, build the bundle first, then attach the forecast before returning. Replace the return statement with:

```python
    bundle = AnalysisBundle(
        info=info, fin=fin, fund=fund, tech=tech, val=val, risk=risk,
        card=card, as_of=date.today(), prices=prices,
        business=business, stewardship=stewardship, thesis=thesis, critique=critique,
    )
    # no universe on this path: the peer term is absent and completeness says so
    bundle.forecast = build_forecast(bundle, peer_pes=[], peer_growths=[])
    bundle.risk.flags.extend(forecast_flags(bundle, bundle.forecast))
    return bundle
```

In `screen`, add the post-pass immediately after `apply_sector_pillar(bundles, context)`:

```python
        apply_forecasts(bundles, context)  # peer-anchored, overrides the solo pass
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py tests/test_forecast.py -v`
Expected: all PASS

- [ ] **Step 7: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS. `tests/test_web.py` and `tests/test_publish.py` serialize bundles; if either asserts an exact JSON shape, update the expectation to include `forecast` and `prices`.

- [ ] **Step 8: Commit**

```bash
git add src/mbe/pipeline.py src/mbe/analysis/forecast.py tests/test_pipeline.py
git commit -m "feat(pipeline): forecast post-pass with leave-one-out peer anchors"
```

---

## Task 11: Report section

**Files:**
- Modify: `src/mbe/report/markdown.py:195-199` (the Bull/Base/Bear block) and the Valuation section
- Test: manual render plus `tests/test_web.py` regression

- [ ] **Step 1: Replace the Bull/Base/Bear block**

In `src/mbe/report/markdown.py`, replace lines 195-199 entirely:

```jinja
## Bull / Base / Bear

- **Bull:** growth sustains at {{ val.assumptions.get("g_bull") | pct }}, fair value {{ val.fair_value_bull | num }} ({{ pct_vs(val.fair_value_bull, val.price) }}).
- **Base:** delivered-growth median of {{ val.assumptions.get("g_base") | pct }} continues 5 years then fades, fair value {{ val.fair_value_base | num }} ({{ pct_vs(val.fair_value_base, val.price) }}).
- **Bear:** growth decays to {{ val.assumptions.get("g_bear") | pct }}, fair value {{ val.fair_value_bear | num }} ({{ pct_vs(val.fair_value_bear, val.price) }}).
```

with:

```jinja
## 3-Year Price Forecast

{% if forecast %}
Where the price could be in {{ forecast.horizon_years }} years, projected from FY{{ forecast.base_fiscal_year }} revenue and net margin against an exit multiple. Each scenario moves growth, margin **and** the multiple — not one knob three ways.

| Scenario | Prob. | Revenue growth | Net margin | Exit multiple | FY+3 EPS | Target | 3y CAGR |
|---|---|---|---|---|---|---|---|
{% for s in forecast.scenarios %}
| **{{ s.name | capitalize }}** | {{ s.probability | pct }} | {{ s.growth_start | pct }} → {{ s.growth_end | pct }} | {{ s.terminal_net_margin | pct }} | {{ "%.1f" | format(s.exit_multiple) }}x | {{ s.eps_fy3 | num }} | {{ s.target_price | num }} | {{ s.cagr_3y | pct }} |
{% endfor %}

**Probability-weighted:** target {{ forecast.expected_target | num }}, expected 3y CAGR {{ forecast.expected_cagr_3y | pct }}. Probability of a target below today's price: {{ forecast.downside_probability | pct }}.

**Exit multiple anchor — {{ "%.1f" | format(forecast.anchor.anchor) }}x**

| Input | Value |
|---|---|
| Peer median P/E ({{ forecast.anchor.peer_n }} peers, leave-one-out) | {% if forecast.anchor.peer_pe %}{{ "%.1f" | format(forecast.anchor.peer_pe) }}x{% else %}not available{% endif %} |
| Own history median P/E | {% if forecast.anchor.own_pe_median %}{{ "%.1f" | format(forecast.anchor.own_pe_median) }}x{% else %}not available{% endif %} |
| Today's P/E within own history | {% if forecast.anchor.own_pe_percentile_now is not none %}{{ forecast.anchor.own_pe_percentile_now | pct }} percentile{% else %}not available{% endif %} |
| Quality multiplier (franchise score) | {{ "%.2f" | format(forecast.anchor.quality_multiplier) }}x |

{% for note in forecast.anchor.notes %}
- {{ note }}
{% endfor %}

**Scenario assumptions**

{% for s in forecast.scenarios %}
*{{ s.name | capitalize }}:*
{% for e in s.evidence %}
- {{ e }}
{% endfor %}
{% endfor %}

*Forecast completeness {{ forecast.completeness | pct }}. A scenario model with
stated assumptions, not a prediction — see Model validation status.*
{% else %}
No forecast: no exit multiple could be anchored to either peer or own-history
multiples, and a forecast without an anchor would be arithmetic dressed up as a
view.
{% endif %}
```

- [ ] **Step 2: Pass `forecast` into the template context**

In `src/mbe/report/markdown.py`, inside the `_TEMPLATE.render(...)` call that starts at line 299, add one line after `critique=bundle.critique,` (line 309):

```python
        forecast=bundle.forecast,
```

- [ ] **Step 3: Disclose the spike ratio in the Valuation section**

In the Valuation section of the same template, after the existing `Assumptions:` line, add:

```jinja
{% if val.assumptions.get("fcf_spike_ratio") == val.assumptions.get("fcf_spike_ratio") %}
Base FCF is the latest year's, not a trailing average — it stands at {{ "%.1f" | format(val.assumptions.get("fcf_spike_ratio")) }}x the 3-year mean. The risk that it does not repeat is carried by the bear scenario above, not by a haircut to all three.
{% endif %}
```

The `x == x` comparison is a NaN check: the ratio is NaN when no 3-year mean is definable.

- [ ] **Step 4: Render a real report and read it**

Run:

```bash
.venv/bin/python -m mbe.cli analyze HBLENGINE.NS --out /tmp/fc-check
```

Then read the generated markdown and verify by eye: the forecast table has three rows in bull/base/bear order, targets descend bull → bear, the anchor audit table is populated, and the scenario assumptions read as sentences a human would argue with. Note that `mbe analyze` has no peer set, so "Peer median P/E" will read *not available* — that is correct on this path.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS. `tests/test_web.py` renders reports; if it asserts on the old "Bull / Base / Bear" heading, update it to the new heading.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/report/markdown.py tests/
git commit -m "feat(report): 3-Year Price Forecast section with a full audit trail

Replaces the Bull/Base/Bear block, whose 'delivered-growth median' label
described a 25% cap rather than the median it claimed."
```

---

## Task 12: Forecast accuracy backtest

**Files:**
- Modify: `src/mbe/backtest/harness.py`
- Test: `tests/test_harness.py`

The spec is explicit that this will show weak results at first: the Indian sample spans 2021-2025 and holds barely one non-overlapping 3-year window, so the US 2012-2025 sample carries nearly all the evidence. Build the measurement anyway — an unvalidated forecast is exactly what the existing findings doc warns against.

- [ ] **Step 1: Read the harness first**

Run: `.venv/bin/python -m pytest tests/test_harness.py -v` and read `src/mbe/backtest/harness.py:70-130` (`evaluate_cutoff`, `forward_return`, `analyze_as_of`). Match the existing point-in-time pattern — `truncate_financials` and `truncate_prices` already do the hard part.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_harness.py`:

```python
def test_forecast_accuracy_scores_predicted_against_realized():
    """A forecast whose base target is hit exactly should score ~0 error."""
    from mbe.backtest.harness import forecast_error

    # predicted base target 1500 from a price of 1000 over 3 years; realized 1500
    assert forecast_error(predicted=1500.0, realized=1500.0) == pytest.approx(0.0)
    assert forecast_error(predicted=1500.0, realized=750.0) == pytest.approx(-0.5)
    assert forecast_error(predicted=1000.0, realized=2000.0) == pytest.approx(1.0)


def test_forecast_error_none_on_missing_inputs():
    from mbe.backtest.harness import forecast_error

    assert forecast_error(predicted=None, realized=1500.0) is None
    assert forecast_error(predicted=1500.0, realized=None) is None
    assert forecast_error(predicted=0.0, realized=1500.0) is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_harness.py -v`
Expected: FAIL with `ImportError: cannot import name 'forecast_error'`

- [ ] **Step 4: Implement `forecast_error`**

Add to `src/mbe/backtest/harness.py`:

```python
def forecast_error(predicted: float | None, realized: float | None) -> float | None:
    """Relative error of a forecast target against the realized price.

    Signed on purpose: the failure this whole change addresses was systematic
    *understatement*, so a mean error near zero matters more than a small
    absolute error, and averaging absolute values would have hidden the bias.
    """
    if predicted is None or realized is None or predicted <= 0:
        return None
    return realized / predicted - 1
```

- [ ] **Step 5: Record the mean error per cutoff in `run_backtest_multi`**

`evaluate_cutoff` takes plain score/return dicts and never sees a bundle, so the accuracy pass cannot live there. It belongs in `run_backtest_multi`, which has the bundles.

Two things to get right. `forward_return` returns a *return*, not a price, so the realized price is `bundle.val.price * (1 + ret)`. And forecasts need the peer post-pass, which the backtest currently only runs when a sector score is requested.

In `src/mbe/backtest/harness.py`, add a field to `CutoffResult` (line 49-57):

```python
    forecast_mean_error: float | None = None  # signed; positive = forecast too low
```

Then in `run_backtest_multi`, replace the sector post-pass block:

```python
        if at_cutoff and any(s in _SECTOR_SCORES for s in score_names):
            context = compute_sector_scores([b for _, b in at_cutoff])
            # descriptive attach only: base multibagger stays comparable
            apply_sector_pillar([b for _, b in at_cutoff], context, adjust_score=False)
```

with:

```python
        forecast_errors: list[float] = []
        if at_cutoff:
            context = compute_sector_scores([b for _, b in at_cutoff])
            if any(s in _SECTOR_SCORES for s in score_names):
                # descriptive attach only: base multibagger stays comparable
                apply_sector_pillar(
                    [b for _, b in at_cutoff], context, adjust_score=False
                )
            apply_forecasts([b for _, b in at_cutoff], context)
            for ticker, bundle in at_cutoff:
                if bundle.forecast is None or len(bundle.forecast.scenarios) != 3:
                    continue
                base = bundle.forecast.scenarios[1]  # ordered bull, base, bear
                realized = bundle.val.price * (1 + fwd[ticker])
                err = forecast_error(base.target_price, realized)
                if err is not None:
                    forecast_errors.append(err)
        mean_error = (
            sum(forecast_errors) / len(forecast_errors) if forecast_errors else None
        )
```

Add the import at the top of the file:

```python
from mbe.analysis.forecast import apply_forecasts
```

Then set the field on each `CutoffResult` — the error is score-independent, so the same value goes on every score's result. Replace:

```python
            per_score_results[name].append(
                CutoffResult(cutoff=cutoff, **evaluate_cutoff(scores[name], fwd))
            )
```

with:

```python
            per_score_results[name].append(CutoffResult(
                cutoff=cutoff,
                forecast_mean_error=mean_error,
                **evaluate_cutoff(scores[name], fwd),
            ))
```

Finally, in `render_backtest_md`, add a column for it labelled *"mean signed forecast error (positive = forecast was too low)"*.

**Note on horizon:** this measurement is only meaningful when `horizon_days` is around 1095. Running it at the default shorter horizon compares a 3-year target against a 1-year move and will look terrible for reasons that have nothing to do with the model.

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS

- [ ] **Step 7: Run a real backtest and record the finding**

Run: `.venv/bin/python -m mbe.cli backtest --help` to get the exact invocation, then run it on the US sample. Append the mean signed forecast error to `docs/backtest-findings-2026-07.md` under a new heading, stating the sample, the window count, and — if the error is large or the sample too thin to conclude anything — say so plainly. Do not report a favourable number without its sample size.

- [ ] **Step 8: Commit**

```bash
git add src/mbe/backtest/harness.py tests/test_harness.py docs/backtest-findings-2026-07.md
git commit -m "feat(backtest): signed forecast-accuracy measurement

Signed rather than absolute: the failure being fixed was systematic
understatement, which a mean absolute error would have concealed."
```

---

## Task 13: Rebuild the site and review the ranking shift

**Files:**
- Modify: `site/` (generated), `CHANGELOG.md`

- [ ] **Step 1: Capture the current top 25 before rebuilding**

```bash
cp site/data.json /tmp/data-before.json
```

- [ ] **Step 2: Rebuild**

There is no `publish` CLI command — the site is built by `scripts/build_site.py`, which screens `nifty-smallcap250` and writes `site/`:

```bash
.venv/bin/python scripts/build_site.py
```

This hits Yahoo for ~250 tickers and takes a while. It refuses to publish if fewer than 100 names analyze (`MIN_ANALYZED` at `scripts/build_site.py:31`), so a rate-limited run fails loudly rather than shipping a half-ranking.

- [ ] **Step 3: Diff the ranking and sanity check it**

`site/data.json` holds the ranking under the `top` key, with `mb` (multibagger score) and `inv` (investment score) per row:

```bash
.venv/bin/python - <<'PY'
import json
before = {r["ticker"]: r for r in json.load(open("/tmp/data-before.json"))["top"]}
after = {r["ticker"]: r for r in json.load(open("site/data.json"))["top"]}
for t in sorted(set(before) | set(after)):
    b, a = before.get(t), after.get(t)
    if b and a:
        print(f'{t:18s} mb {b["mb"]:5.1f} -> {a["mb"]:5.1f}   inv {b["inv"]:5.1f} -> {a["inv"]:5.1f}')
    else:
        print(f'{t:18s} {"dropped out of top" if b else "new in top"}')
PY
```

Read the output. Expected direction: high-growth, cash-generative names rise as the Valuation pillar stops penalising them for the arithmetic of their own growth. If a name with weak fundamentals jumps to the top, that is a signal the base-FCF change is being read as quality — investigate before accepting, and report it rather than shipping it.

- [ ] **Step 4: Update the changelog**

Add a `CHANGELOG.md` entry following the existing format, covering: the base-FCF fix and that it changes rankings, the new 3-year forecast section, the three coherence flags, and that the forecast is descriptive-only pending validation.

- [ ] **Step 5: Commit**

```bash
git add site/ CHANGELOG.md
git commit -m "chore(publish): site rebuild with 3-year scenario forecasts"
```

---

## Notes for the implementer

**The two least certain numbers in this whole change** are `ANCHOR_MAX = 45.0` and the `0.6 / 1.0 / 1.4` multiple spread. They are judgment calls, not derived. HBL lands near the 45x ceiling, so the clamp does real work rather than sitting idle. If Task 8's `base.cagr_3y > 0` assertion fails, these are the first things to examine — but raise it with the user rather than quietly retuning a constant to make a test pass.

**`BULL_CAGR_CAP = 0.45`** is a hard ceiling: the engine will never forecast better than roughly 3x in three years. That is deliberate.

**Do not weaken a failing assertion to get green.** Every test in this plan encodes a specific failure that was diagnosed in the spec. A test that fails is either a real bug or a parameter worth a conversation.
