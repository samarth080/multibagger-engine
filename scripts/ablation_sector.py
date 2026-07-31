"""Ablation: does the Sector Momentum pillar earn its 0.12 weight?

Pre-registered rule (P2.4 spec, fixed BEFORE results were seen): the pillar
goes live in the multibagger score only if augmented mean IC >= base mean IC
in the majority of samples. Weight fixed at 0.12; no sweeping. Fail ->
descriptive-only (sector table, tags, report line stay). Either way recorded.
"""

from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.universe import get_universe

SCORES = ["multibagger", "multibagger_sector", "sector"]
HORIZON = 730
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

US_CUTOFFS = [date(y, 7, 15) for y in range(2012, 2024)]
IN_CUTOFFS = [date(y, 7, 15) for y in range(2016, 2024)]

india = get_universe("nifty-smallcap250", cache=YCACHE, pinned=True)
SAMPLES = [
    ("us-smallcap-sample", edgar, US_CUTOFFS,
     get_universe("us-smallcap-sample", cache=YCACHE, pinned=True)),
    ("us-smallcap-sample2", edgar, US_CUTOFFS,
     get_universe("us-smallcap-sample2", cache=YCACHE, pinned=True)),
    ("india-primary", nse, IN_CUTOFFS, india[:50]),
    ("india-replication", nse, IN_CUTOFFS, india[50:100]),
]


def fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.3f}"


wins = 0
for name, provider, cutoffs, tickers in SAMPLES:
    reports = run_backtest_multi(
        tickers, provider, cutoffs, HORIZON, score_names=SCORES, universe_name=name
    )
    base = reports["multibagger"].mean_ic
    aug = reports["multibagger_sector"].mean_ic
    solo = reports["sector"].mean_ic
    beat = aug is not None and base is not None and aug >= base
    wins += int(beat)
    print(f"{name:22s} base {fmt(base)} | +sector {fmt(aug)} | "
          f"sector-alone {fmt(solo)}{'  >= base' if beat else ''}")

print(f"\nVERDICT: +sector >= base in {wins}/{len(SAMPLES)} samples -> "
      f"{'LIVE: set SECTOR_PILLAR_LIVE = True' if wins * 2 > len(SAMPLES) else 'DEMOTED to descriptive-only'}")
