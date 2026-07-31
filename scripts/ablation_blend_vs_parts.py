"""Does the multibagger blend beat its own components?

Two separate readings have now hinted that a single pillar may outperform the
composite it sits inside: sector-alone in Addendum 14 (since retracted as drift)
and Quality-alone on India in Addendum 18 (+0.280 vs a +0.221 composite, a
margin that clears the pre-registered threshold).

A blend that cannot beat its own best part is not earning its complexity — it is
diluting a signal with noise. This tests every component of MULTIBAGGER_WEIGHTS
against the blend, on pinned universes, under the amended rule (a win requires
IC_component >= IC_blend + 0.05).

Descriptive only. Nothing here changes a weight; the point is to know.
"""

from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.scoring.engine import MULTIBAGGER_WEIGHTS
from mbe.universe import get_universe

MARGIN = 0.05  # pre-registered 2026-07-31
HORIZON = 730
COMPONENTS = list(MULTIBAGGER_WEIGHTS)
SCORES = ["multibagger"] + COMPONENTS
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

results: dict[str, dict[str, float | None]] = {}
for universe, provider, cutoffs, tickers in SAMPLES:
    reports = run_backtest_multi(
        tickers, provider, cutoffs, HORIZON,
        score_names=SCORES, universe_name=universe,
    )
    results[universe] = {s: reports[s].mean_ic for s in SCORES}
    row = results[universe]
    print(f"{universe:22s} blend {row['multibagger']:+.3f} | "
          + " ".join(f"{c[:4]} {row[c]:+.3f}" for c in COMPONENTS), flush=True)

print(f"\n{'component':16s} " + " ".join(f"{u[:12]:>13s}" for u, *_ in SAMPLES) + "   wins")
print("-" * 78)
for comp in COMPONENTS:
    cells, wins, counted = [], 0, 0
    for universe, *_ in SAMPLES:
        blend, part = results[universe]["multibagger"], results[universe][comp]
        if blend is None or part is None:
            cells.append("n/a")
            continue
        counted += 1
        beat = part >= blend + MARGIN
        wins += int(beat)
        cells.append(f"{part - blend:+.3f}{'*' if beat else ' '}")
    print(f"{comp:16s} " + " ".join(f"{c:>13s}" for c in cells) + f"   {wins}/{counted}")

print(f"\n* = component beat the blend by >= {MARGIN} (pre-registered margin)")
print("A component winning a majority would mean the blend dilutes it.")
