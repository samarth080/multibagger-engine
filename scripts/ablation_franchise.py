"""Ablation: does the franchise-durability score earn its place?

Runs the multi-score harness (base multibagger vs franchise vs Quality vs
investment) point-in-time on the cached US small-cap samples and the Indian
smallcap sample, 2y horizon. Decision rule (from the P2.1 spec): franchise
stays a first-class *score* only if its IC >= base multibagger IC on the
majority of samples; otherwise it is demoted to a descriptive business profile.
Either way the result is recorded honestly.
"""

from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.universe import get_universe

SCORES = ["multibagger", "franchise", "Quality", "investment"]
HORIZON = 730
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

SAMPLES = [
    ("us-smallcap-sample", edgar, [date(y, 7, 15) for y in range(2012, 2024)]),
    ("us-smallcap-sample2", edgar, [date(y, 7, 15) for y in range(2012, 2024)]),
    ("nifty-smallcap250", nse, [date(y, 7, 15) for y in (2021, 2022, 2023)]),
]

wins = {s: 0 for s in SCORES}
totals = 0
for universe, provider, cutoffs in SAMPLES:
    tickers = get_universe(universe, cache=YCACHE, pinned=True)
    limit = 50 if universe.startswith("nifty") else None
    reports = run_backtest_multi(
        (tickers[:limit] if limit else tickers), provider, cutoffs, HORIZON,
        score_names=SCORES, universe_name=universe,
    )
    print(f"\n=== {universe} ({len(cutoffs)} cutoffs, 2y) ===")
    base = reports["multibagger"].mean_ic or float("-inf")
    for s in SCORES:
        ic = reports[s].mean_ic
        tag = ""
        if s != "multibagger" and ic is not None and ic >= (reports["multibagger"].mean_ic or -9):
            tag = "  >= base"
        print(f"  {s:12s} mean IC {('n/a' if ic is None else f'{ic:+.3f}')}{tag}")
    totals += 1
    for s in SCORES:
        ic = reports[s].mean_ic
        if ic is not None and ic >= base:
            wins[s] += 1

print(f"\n=== VERDICT ({totals} samples) ===")
for s in SCORES:
    print(f"  {s:12s} >= base multibagger in {wins[s]}/{totals} samples")
print(f"\nfranchise stays a first-class score iff franchise wins majority: "
      f"{wins['franchise']}/{totals}")
