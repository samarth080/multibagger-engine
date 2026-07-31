"""Pillar-attribution backtest: which score components carry signal?

Runs every pillar + composite through the PIT harness in one pass per sample
and prints a mean-IC matrix. Research artifact — results land in
docs/backtest-findings-2026-07.md.
"""

from datetime import date

from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.storage import RunStore
from mbe.universe import get_universe

SCORES = [
    "multibagger", "investment", "Quality", "Growth",
    "Financial Strength", "Valuation", "Momentum", "Size Runway", "Reinvestment",
]
CUTOFFS = [date(y, 7, 15) for y in range(2012, 2024)]
HORIZON = 730

provider = CompositeProvider(
    fundamentals=EdgarFundamentals(DiskCache("data/cache")),
    market=YahooProvider(DiskCache("data/cache")),
)
store = RunStore("data/mbe.duckdb")

for universe in ("us-smallcap-sample", "us-smallcap-sample2"):
    tickers = get_universe(universe, cache=DiskCache("data/cache", ttl_hours=168), pinned=True)
    reports = run_backtest_multi(
        tickers, provider, CUTOFFS, HORIZON,
        score_names=SCORES, universe_name=universe,
    )
    print(f"\n=== {universe} (2y, {len(CUTOFFS)} cutoffs) ===")
    for name in SCORES:
        r = reports[name]
        mean_ic = "n/a" if r.mean_ic is None else f"{r.mean_ic:+.3f}"
        n_pos = sum(1 for c in r.cutoffs if c.ic is not None and c.ic > 0)
        print(f"{name:20s} mean IC {mean_ic}  positive {n_pos}/{len(CUTOFFS)}")
        store.save_backtest(
            universe=universe, score_name=name, horizon_days=HORIZON,
            mean_ic=r.mean_ic if r.mean_ic is not None else float("nan"),
            details={"cutoffs": len(CUTOFFS), "attribution_run": True},
        )
