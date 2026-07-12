"""Veto-avoidance study: does the self-critique veto steer away from worse
outcomes? The thesis/critique layer makes no alpha claim — its justification is
risk avoidance. This tests it directly, point-in-time.

For each cutoff we analyze every name as-of, record whether the critique vetoed
it, and compare forward-return distributions of vetoed vs non-vetoed names —
mean return and, crucially, the permanent-loss rate (fraction with a >30% 2y
loss). A useful veto should show lower mean AND a higher loss rate among vetoed.
"""

from datetime import date

from mbe.backtest.harness import analyze_as_of, forward_return
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.provider import ProviderError
from mbe.data.yahoo import YahooProvider
from mbe.universe import get_universe

HORIZON = 730
LOSS_THRESHOLD = -0.30
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

SAMPLES = [
    ("us-smallcap-sample", edgar, [date(y, 7, 15) for y in range(2012, 2024)], None),
    ("us-smallcap-sample2", edgar, [date(y, 7, 15) for y in range(2012, 2024)], None),
    ("nifty-smallcap250", nse, [date(y, 7, 15) for y in (2021, 2022, 2023)], 50),
]


def _stats(returns):
    if not returns:
        return None
    n = len(returns)
    mean = sum(returns) / n
    loss_rate = sum(1 for r in returns if r < LOSS_THRESHOLD) / n
    return mean, loss_rate, n


all_vetoed, all_ok = [], []
for universe, provider, cutoffs, limit in SAMPLES:
    tickers = get_universe(universe, cache=YCACHE)
    tickers = tickers[:limit] if limit else tickers
    vetoed, ok = [], []
    for cutoff in cutoffs:
        for t in tickers:
            try:
                bundle, full_prices = analyze_as_of(t, provider, cutoff)
            except (ProviderError, Exception):
                continue
            ret = forward_return(full_prices, cutoff, HORIZON)
            if ret is None or bundle.critique is None:
                continue
            (vetoed if bundle.critique.veto else ok).append(ret)
    all_vetoed += vetoed
    all_ok += ok
    v, o = _stats(vetoed), _stats(ok)
    print(f"\n=== {universe} ===")
    if v:
        print(f"  VETOED     mean {v[0]:+.1%}  loss-rate(>30%) {v[1]:.0%}  n={v[2]}")
    if o:
        print(f"  not vetoed mean {o[0]:+.1%}  loss-rate(>30%) {o[1]:.0%}  n={o[2]}")

print("\n=== POOLED ===")
v, o = _stats(all_vetoed), _stats(all_ok)
if v and o:
    print(f"  VETOED     mean {v[0]:+.1%}  loss-rate {v[1]:.0%}  n={v[2]}")
    print(f"  not vetoed mean {o[0]:+.1%}  loss-rate {o[1]:.0%}  n={o[2]}")
    print(f"\n  veto avoids worse outcomes? "
          f"mean {'YES' if v[0] < o[0] else 'no'}, "
          f"loss-rate {'YES' if v[1] > o[1] else 'no'}")
