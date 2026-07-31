"""Does dropping a component improve the blend?

Addendum 19 found two components failing the blend in different ways:

- **Momentum** was worse than the blend in 4/4 samples, with absolute ICs of
  -0.049 / -0.004 / -0.110 / +0.037. Unlike the size result, survivorship bias
  has no obvious mechanism to manufacture a *negative* reading, which makes this
  the more trustworthy of the two findings — and it suggests the blend is being
  dragged by a component, not merely diluted.
- **Size Runway** beat the blend 4/4, but Addendum 20 withdrew its backtest
  performance as evidence after it failed its survivorship bound.

So: does removing either actually help? `combine` renormalizes over the pillars
present, so deleting a key redistributes its weight proportionally across the
rest. Run in-process rather than recombining offline, so hard gates apply
exactly as they do in production.

Pre-registered margin: a variant is an improvement only at >= 0.05 (2026-07-31).
Descriptive only — nothing here changes a weight without a separate decision.
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
    "no-Momentum": {k: v for k, v in BASELINE.items() if k != "Momentum"},
    "no-Size": {k: v for k, v in BASELINE.items() if k != "Size Runway"},
    "no-Momentum-no-Size": {
        k: v for k, v in BASELINE.items() if k not in ("Momentum", "Size Runway")
    },
}

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
    print(f"{label:22s} " + " ".join(
        f"{results[label][u]:+.3f}" for u, *_ in SAMPLES), flush=True)

engine.MULTIBAGGER_WEIGHTS.clear()
engine.MULTIBAGGER_WEIGHTS.update(BASELINE)

print(f"\n{'variant':22s}" + "".join(f"{u[:12]:>14s}" for u, *_ in SAMPLES) + "   better")
print("-" * 84)
for label in VARIANTS:
    if label == "baseline":
        cells = [f"{results[label][u]:+.3f}" for u, *_ in SAMPLES]
        print(f"{label:22s}" + "".join(f"{c:>14s}" for c in cells))
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
    print(f"{label:22s}" + "".join(f"{c:>14s}" for c in cells) + f"   {better}/{counted}")

print(f"\n* = improved on baseline by >= {MARGIN} (pre-registered margin)")
print("Deltas are variant IC minus baseline IC; positive means dropping helped.")
