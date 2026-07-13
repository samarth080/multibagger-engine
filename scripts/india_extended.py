"""Extended India backtest: cutoffs 2016-2023 (including NON-bull windows),
both disjoint samples, 2y horizon — enabled by the legacy parser deepening
statements to FY2013+. This is the properly-windowed test of the home market.
"""

from datetime import date

from mbe.backtest.harness import run_backtest
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.storage import RunStore
from mbe.universe import get_universe

CACHE = DiskCache("data/cache")
provider = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))
CUTOFFS = [date(y, 7, 15) for y in range(2016, 2024)]

all_tickers = get_universe("nifty-smallcap250", cache=DiskCache("data/cache", ttl_hours=168))
store = RunStore("data/mbe.duckdb")

for name, tickers in [("india-primary", all_tickers[:50]), ("india-replication", all_tickers[50:100])]:
    report = run_backtest(
        tickers, provider, CUTOFFS, 730,
        score_name="multibagger", universe_name=name,
    )
    print(f"\n=== {name} (8 cutoffs 2016-2023, 2y) ===")
    for c in report.cutoffs:
        ic = "n/a" if c.ic is None else f"{c.ic:+.3f}"
        print(f"  {c.cutoff}: IC {ic} | n={c.n}")
    mean = "n/a" if report.mean_ic is None else f"{report.mean_ic:+.3f}"
    print(f"Mean IC: {mean} | skipped {len(report.skipped)}")
    store.save_backtest(
        universe=name, score_name="multibagger", horizon_days=730,
        mean_ic=report.mean_ic if report.mean_ic is not None else float("nan"),
        details={"cutoffs": "2016-2023", "legacy_depth": True},
    )
