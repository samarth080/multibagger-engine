"""Is Valuation underweighted relative to Growth in the multibagger blend?

Hypothesis from a specific, visible failure in the live top 25: NIVABUPA earns
5.6% on capital and trades at 122x, its own 3-year forecast says -4.1%/yr, and
it still ranks #22 of 250. The composite rewards its 36.4% revenue growth
(Growth weight 0.26) and small size (0.16) while under-penalising the multiple
(Valuation weight 0.14). CARTRADE is the same shape: 5.0% ROCE at 59.5x, #24.

**This is a post-hoc hypothesis tested on the same data that generated it.**
That is weaker evidence than a pre-registered test on fresh data, and no
outcome here should be treated as confirmatory. It is recorded that way
deliberately.

Two step sizes only, to limit fishing:
  valuation-swap : Growth 0.26 <-> Valuation 0.14  (the direct hypothesis)
  valuation-mid  : Growth 0.20,   Valuation 0.20   (half the step)

Pre-registered margin (>= 0.05, 2026-07-31) applies. Run in-process so hard
gates fire exactly as in production.
"""

from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.scoring import engine
from mbe.universe import get_universe

MARGIN = 0.05
HORIZON = 730
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

US_CUTOFFS = [date(y, 7, 15) for y in range(2012, 2024)]
IN_CUTOFFS = [date(y, 7, 15) for y in range(2016, 2024)]
_india = get_universe("nifty-smallcap250", cache=YCACHE, pinned=True)

SAMPLES = [
    ("us-smallcap-sample", edgar, US_CUTOFFS,
     get_universe("us-smallcap-sample", cache=YCACHE, pinned=True)),
    ("us-smallcap-sample2", edgar, US_CUTOFFS,
     get_universe("us-smallcap-sample2", cache=YCACHE, pinned=True)),
    ("india-primary", nse, IN_CUTOFFS, _india[:50]),
    ("india-replication", nse, IN_CUTOFFS, _india[50:100]),
]

BASELINE = dict(engine.MULTIBAGGER_WEIGHTS)
VARIANTS = {
    "baseline": BASELINE,
    "valuation-swap": {**BASELINE, "Growth": 0.14, "Valuation": 0.26},
    "valuation-mid": {**BASELINE, "Growth": 0.20, "Valuation": 0.20},
}
for label, w in VARIANTS.items():
    assert abs(sum(w.values()) - 1.0) < 1e-9, (label, sum(w.values()))

results: dict[str, dict[str, float | None]] = {}
for label, weights in VARIANTS.items():
    engine.MULTIBAGGER_WEIGHTS.clear()
    engine.MULTIBAGGER_WEIGHTS.update(weights)
    results[label] = {}
    for universe, provider, cutoffs, tickers in SAMPLES:
        rep = run_backtest_multi(
            tickers, provider, cutoffs, HORIZON,
            score_names=["multibagger"], universe_name=universe,
        )["multibagger"]
        results[label][universe] = rep.mean_ic
    print(f"{label:16s} " + " ".join(
        f"{results[label][u]:+.3f}" for u, *_ in SAMPLES), flush=True)

engine.MULTIBAGGER_WEIGHTS.clear()
engine.MULTIBAGGER_WEIGHTS.update(BASELINE)

print(f"\n{'variant':16s}" + "".join(f"{u[:12]:>14s}" for u, *_ in SAMPLES) + "   better")
print("-" * 78)
for label in VARIANTS:
    if label == "baseline":
        print(f"{label:16s}" + "".join(
            f"{results[label][u]:+14.3f}" for u, *_ in SAMPLES))
        continue
    cells, better, counted = [], 0, 0
    for universe, *_ in SAMPLES:
        a, b = results[label][universe], results["baseline"][universe]
        if a is None or b is None:
            cells.append("n/a")
            continue
        counted += 1
        won = a >= b + MARGIN
        better += int(won)
        cells.append(f"{a - b:+.3f}{'*' if won else ' '}")
    print(f"{label:16s}" + "".join(f"{c:>14s}" for c in cells) + f"   {better}/{counted}")

print(f"\n* = beat baseline by >= {MARGIN}. Post-hoc hypothesis: treat any win as")
print("a lead to test on fresh data, not as a result.")
