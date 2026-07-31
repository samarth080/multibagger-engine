"""Does the dilution signal earn its place, now that US data finally has it?

Addendum 16 open thread: base multibagger IC on us-smallcap-sample fell
+0.098 -> -0.012 once the EDGAR share-count fix restored share_count_cagr_3y.
That was either universe drift or a real anti-signal, inseparable while the
sample redrew weekly. Pinned universes make it separable.

The metric reaches the two scores by *different* routes, so both are tested:

- `multibagger` sees it ONLY through the hard gate (engine._hard_gates), which
  caps the score at HARD_GATE_CAP for >8%/yr dilution. Financial Strength is
  not in MULTIBAGGER_WEIGHTS at all, so the pillar cannot move this ranking.
- `investment` sees it ONLY through the Financial Strength pillar (weight 0.18
  of the composite, 0.10 within the pillar). No gate applies to it.

A first pass toggled only the pillar and returned deltas of exactly 0.000 on
multibagger across 27 cutoffs — correct, and the tell that it was measuring the
wrong path. Both arms are toggled here.

True A/B: identical companies, cutoffs, data and code; only the signal moves.
"""

from datetime import date

import mbe.scoring.engine as engine
from mbe.backtest.harness import run_backtest_multi
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.yahoo import YahooProvider
from mbe.scoring import pillars
from mbe.universe import get_universe

HORIZON = 730
METRIC = "share_count_cagr_3y"
GATE_MARKER = "shareholder erosion gate"
SCORES = ["multibagger", "investment"]
CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)

edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

SAMPLES = [
    ("us-smallcap-sample", edgar, [date(y, 7, 15) for y in range(2012, 2024)], None),
    ("us-smallcap-sample2", edgar, [date(y, 7, 15) for y in range(2012, 2024)], None),
    ("nifty-smallcap250", nse, [date(y, 7, 15) for y in (2021, 2022, 2023)], 50),
]

STRENGTH_WITH = list(pillars._STRENGTH)
STRENGTH_WITHOUT = [i for i in STRENGTH_WITH if i[0] != METRIC]
assert len(STRENGTH_WITHOUT) == len(STRENGTH_WITH) - 1, f"{METRIC} not in _STRENGTH"

_orig_gates = engine._hard_gates


def _gates_without_dilution(fund, fin):
    return [f for f in _orig_gates(fund, fin) if GATE_MARKER not in f]


def run(label: str, *, dilution_on: bool) -> dict[tuple[str, str], float | None]:
    pillars._STRENGTH[:] = STRENGTH_WITH if dilution_on else STRENGTH_WITHOUT
    engine._hard_gates = _orig_gates if dilution_on else _gates_without_dilution
    out: dict[tuple[str, str], float | None] = {}
    for universe, provider, cutoffs, limit in SAMPLES:
        tickers = get_universe(universe, cache=YCACHE, pinned=True)
        reports = run_backtest_multi(
            (tickers[:limit] if limit else tickers), provider, cutoffs, HORIZON,
            score_names=SCORES, universe_name=universe,
        )
        for s in SCORES:
            out[(universe, s)] = reports[s].mean_ic
        print(f"  [{label}] {universe:22s} "
              + " ".join(f"{s} {out[(universe, s)]:+.4f}" for s in SCORES), flush=True)
    return out


print("A/B on pinned universes: same companies, same data, dilution signal toggled\n")
on = run("with", dilution_on=True)
off = run("without", dilution_on=False)
pillars._STRENGTH[:] = STRENGTH_WITH
engine._hard_gates = _orig_gates

for s in SCORES:
    route = "hard gate" if s == "multibagger" else "Financial Strength pillar"
    print(f"\n=== {s} (route: {route}) ===")
    print(f"{'sample':24s} {'with':>9s} {'without':>9s} {'delta':>9s}")
    helps = 0
    counted = 0
    for universe, *_ in SAMPLES:
        a, b = on[(universe, s)], off[(universe, s)]
        if a is None or b is None:
            print(f"{universe:24s} {'n/a':>9s} {'n/a':>9s} {'n/a':>9s}")
            continue
        counted += 1
        helps += int(a >= b)
        print(f"{universe:24s} {a:+9.3f} {b:+9.3f} {a - b:+9.3f}")
    if counted:
        verdict = "keep" if helps * 2 > counted else "ANTI-SIGNAL, candidate for removal"
        print(f"VERDICT ({s}): dilution helped in {helps}/{counted} -> {verdict}")
