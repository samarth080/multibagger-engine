"""Disjoint India replication: names 51-100 of nifty-smallcap250.

The decisive test of the +0.232 home-market IC (Addendum 8). The US precedent
(Addendum 4) says exciting first-sample results regress on replication —
this settles whether India's number was signal or sample luck.
"""

from datetime import date

from mbe.backtest.harness import render_backtest_md, run_backtest
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.storage import RunStore
from mbe.universe import get_universe

CACHE = DiskCache("data/cache")
provider = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

tickers = get_universe("nifty-smallcap250", cache=DiskCache("data/cache", ttl_hours=168), pinned=True)[50:100]
report = run_backtest(
    tickers, provider,
    cutoffs=[date(2021, 7, 15), date(2022, 7, 15), date(2023, 7, 15)],
    horizon_days=730, score_name="multibagger",
    universe_name="nifty-smallcap250-replication",
)
for c in report.cutoffs:
    ic = "n/a" if c.ic is None else f"{c.ic:+.3f}"
    print(f"  {c.cutoff}: IC {ic} | n={c.n}")
mean = "n/a" if report.mean_ic is None else f"{report.mean_ic:+.3f}"
print(f"Mean IC: {mean} | skipped {len(report.skipped)}")

with open("reports/backtest_india_replication.md", "w") as f:
    f.write(render_backtest_md(report))
RunStore("data/mbe.duckdb").save_backtest(
    universe="nifty-smallcap250-replication", score_name="multibagger",
    horizon_days=730,
    mean_ic=report.mean_ic if report.mean_ic is not None else float("nan"),
    details={"replication_of": "Addendum 8", "n_tickers": len(tickers)},
)
