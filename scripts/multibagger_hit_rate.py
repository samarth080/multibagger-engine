"""Does the multibagger score actually find multibaggers?

Every backtest in docs/backtest-findings-2026-07.md measures 2-year rank
correlation. Rank correlation and "did this 5x" are different questions: a score
can rank tolerably and never surface a single 10-bagger, or rank poorly overall
while catching the few that matter — which is the outcome a multibagger hunter
is paid for, since the payoff lives in the right tail, not the mean.

This measures the tail directly. For each cutoff: take the top quintile by
multibagger score, hold 5 years, and count what fraction cleared 2x / 3x / 5x.
Compare against the base rate over the whole scored universe at that cutoff.

**Read the lift, not the hit rate.** Absolute hit rates are inflated by
survivorship — these are today's constituents, so the dead are missing. But the
top quintile and the universe are drawn from the *same* biased pool, so the
ratio between them largely cancels the bias. A lift near 1.0 means the ranking
adds nothing over picking at random from the same list.
"""

import sys
from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.universe import get_universe

HORIZON = 1825  # 5 years — the horizon the word "multibagger" implies
QUINTILE = 0.20
THRESHOLDS = [(1.0, "2x"), (2.0, "3x"), (4.0, "5x")]  # forward return, label
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

_india = get_universe("nifty-smallcap250", cache=YCACHE, pinned=True)
SAMPLES = [
    ("us-smallcap-sample", edgar, [date(y, 7, 15) for y in range(2012, 2022)],
     get_universe("us-smallcap-sample", cache=YCACHE, pinned=True)),
    ("us-smallcap-sample2", edgar, [date(y, 7, 15) for y in range(2012, 2022)],
     get_universe("us-smallcap-sample2", cache=YCACHE, pinned=True)),
    ("india-primary", nse, [date(y, 7, 15) for y in range(2016, 2022)], _india[:50]),
    ("india-replication", nse, [date(y, 7, 15) for y in range(2016, 2022)], _india[50:100]),
]

only = sys.argv[1] if len(sys.argv) > 1 else None

for universe, provider, cutoffs, tickers in SAMPLES:
    if only and only != universe:
        continue
    report = run_backtest_multi(
        tickers, provider, cutoffs, HORIZON,
        score_names=["multibagger"], universe_name=universe, collect_raw=True,
    )["multibagger"]
    panel = report.raw_panel or {}

    pooled_top: list[float] = []
    pooled_all: list[float] = []
    print(f"\n=== {universe}: 5y holds, {len(panel)} usable cutoffs ===")
    print(f"{'cutoff':12s} {'n':>4s} {'top':>4s} " + "".join(
        f"{lab:>18s}" for _, lab in THRESHOLDS))
    for cut in sorted(panel):
        rows = panel[cut]
        if len(rows) < 5:
            continue
        ranked = sorted(rows.values(), key=lambda sr: sr[0], reverse=True)
        k = max(1, round(QUINTILE * len(ranked)))
        top = [r for _, r in ranked[:k]]
        allr = [r for _, r in ranked]
        pooled_top += top
        pooled_all += allr
        cells = []
        for thr, _ in THRESHOLDS:
            t = sum(1 for r in top if r >= thr) / len(top)
            b = sum(1 for r in allr if r >= thr) / len(allr)
            lift = f"{t / b:.2f}x" if b > 0 else "  -"
            cells.append(f"{t:>5.0%}/{b:<5.0%}{lift:>7s}")
        print(f"{cut:12s} {len(allr):4d} {len(top):4d} " + "".join(f"{c:>18s}" for c in cells))

    if not pooled_all:
        print("  no usable cutoffs")
        continue
    print(f"\n  POOLED  n={len(pooled_all)}  top-quintile n={len(pooled_top)}")
    for thr, lab in THRESHOLDS:
        t = sum(1 for r in pooled_top if r >= thr) / len(pooled_top)
        b = sum(1 for r in pooled_all if r >= thr) / len(pooled_all)
        lift = t / b if b > 0 else float("nan")
        print(f"    {lab:>3s}  top-quintile {t:6.1%}   universe {b:6.1%}   lift {lift:5.2f}x")
    med_t = sorted(pooled_top)[len(pooled_top) // 2]
    med_a = sorted(pooled_all)[len(pooled_all) // 2]
    print(f"    median 5y return  top-quintile {med_t:+.1%}   universe {med_a:+.1%}")

print("\nLift 1.00x = the ranking adds nothing over picking at random from the "
      "same (survivorship-biased) list.")
