"""Survivorship sensitivity for the Size Runway signal.

The only replicating component (Addendum 6) is also the one most inflated by
current-constituent survivorship. Free delisting-inclusive data doesn't exist,
so we bound the bias instead: inject synthetic "ghost" delisted names into
each cutoff — small (top size score), with grid-varied forward returns — and
measure how the observed IC degrades under plausible assumptions.

Grid: delisted share of the true universe (S&P600 turnover ~5-8%/yr => over a
2y window ~10-16%, skewed small) x ghost forward return (index removals mix
bankruptcies with premium buyouts, so we sweep -60%..+20%).
"""

from datetime import date

from scipy import stats

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.universe import get_universe

US_CUTOFFS = [date(y, 7, 15) for y in range(2012, 2024)]
IN_CUTOFFS = [date(y, 7, 15) for y in range(2016, 2024)]
HORIZON = 730
GHOST_SIZE_SCORE = 95.0  # delisted names skew small -> top size-runway tier
DELIST_FRACTIONS = [0.05, 0.10, 0.15, 0.20]
GHOST_RETURNS = [-0.60, -0.40, -0.20, 0.0, 0.20]

CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)
provider = CompositeProvider(
    fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE)
)
nse_provider = CompositeProvider(
    fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE)
)

# India carries the strongest Size Runway readings (+0.368 / +0.440, Addendum 19)
# and so is the most important place to bound the bias, not the least. The same
# grid is swept: NIFTY Smallcap 250 turnover is not identical to the S&P 600's,
# but 5-20% spans both plausibly.
_india = get_universe("nifty-smallcap250", cache=YCACHE, pinned=True)
SAMPLES = [
    ("us-smallcap-sample", provider, US_CUTOFFS,
     get_universe("us-smallcap-sample", cache=YCACHE, pinned=True)),
    ("us-smallcap-sample2", provider, US_CUTOFFS,
     get_universe("us-smallcap-sample2", cache=YCACHE, pinned=True)),
    ("india-primary", nse_provider, IN_CUTOFFS, _india[:50]),
    ("india-replication", nse_provider, IN_CUTOFFS, _india[50:100]),
]


def adjusted_mean_ic(panel, delist_frac, ghost_return):
    ics = []
    for day in panel.values():
        scores = [s for s, _ in day.values()]
        rets = [r for _, r in day.values()]
        n_ghosts = max(1, round(delist_frac * len(scores)))
        # ghosts are the SMALLEST names: they must rank at/above the top
        # size tier (95 + eps), not below it; return jitter decorrelated
        scores += [GHOST_SIZE_SCORE + 0.001 * (i + 1) for i in range(n_ghosts)]
        rets += [ghost_return + 0.0001 * ((i * 7) % n_ghosts) for i in range(n_ghosts)]
        if len(set(scores)) > 1 and len(set(rets)) > 1:
            ics.append(float(stats.spearmanr(scores, rets).statistic))
    return sum(ics) / len(ics) if ics else float("nan")


for universe, prov, cutoffs, tickers in SAMPLES:
    report = run_backtest_multi(
        tickers, prov, cutoffs, HORIZON,
        score_names=["Size Runway"], universe_name=universe, collect_raw=True,
    )["Size Runway"]
    panel = report.raw_panel
    print(f"\n=== {universe}: observed mean IC {report.mean_ic:+.3f} ===")
    print("delist\\ghost_ret " + "".join(f"{g:>8.0%}" for g in GHOST_RETURNS))
    for frac in DELIST_FRACTIONS:
        row = f"{frac:>15.0%} "
        for g in GHOST_RETURNS:
            row += f"{adjusted_mean_ic(panel, frac, g):>+8.3f}"
        print(row, flush=True)
