"""Ablation: does the stewardship score earn first-class status?

Same pre-registered rule as the franchise ablation (Addendum 9): stewardship
stays a ranking score only if its IC >= base multibagger IC on the majority of
samples; otherwise it is demoted to a descriptive profile. Either way recorded.
"""

from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.universe import get_universe

SCORES = ["multibagger", "stewardship"]
HORIZON = 730
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

SAMPLES = [
    ("us-smallcap-sample", edgar, [date(y, 7, 15) for y in range(2012, 2024)], None),
    ("us-smallcap-sample2", edgar, [date(y, 7, 15) for y in range(2012, 2024)], None),
    ("nifty-smallcap250", nse, [date(y, 7, 15) for y in (2021, 2022, 2023)], 50),
]

wins = 0
for universe, provider, cutoffs, limit in SAMPLES:
    tickers = get_universe(universe, cache=YCACHE, pinned=True)
    reports = run_backtest_multi(
        (tickers[:limit] if limit else tickers), provider, cutoffs, HORIZON,
        score_names=SCORES, universe_name=universe,
    )
    base = reports["multibagger"].mean_ic
    stew = reports["stewardship"].mean_ic
    beat = stew is not None and base is not None and stew >= base
    wins += int(beat)
    print(f"{universe:24s} multibagger {base:+.3f} | stewardship "
          f"{('n/a' if stew is None else f'{stew:+.3f}')}"
          f"{'  >= base' if beat else ''}")

print(f"\nVERDICT: stewardship >= base in {wins}/{len(SAMPLES)} samples -> "
      f"{'first-class score' if wins * 2 > len(SAMPLES) else 'DEMOTED to descriptive-only'}")
