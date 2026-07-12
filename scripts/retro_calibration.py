"""Retro-calibration: the first real test of the platform's stated confidences.

For each historical cutoff, build the point-in-time thesis and emit its
predictions; resolve each against the thesis built one year later (also
point-in-time). Both sides use only data visible at their respective dates —
no lookahead on either end. Results land in the real ledger
(source='thesis-retro') and `mbe calibration` reports the verdict.
"""

from datetime import date, timedelta

from mbe.backtest.harness import analyze_as_of
from mbe.data.cache import DiskCache
from mbe.data.composite import CompositeProvider
from mbe.data.edgar import EdgarFundamentals
from mbe.data.nse_xbrl import NseFundamentals
from mbe.data.provider import ProviderError
from mbe.data.yahoo import YahooProvider
from mbe.storage import RunStore
from mbe.thesis.calibration import brier_score, reliability_table
from mbe.thesis.predictions import emit_predictions, resolve_prediction
from mbe.universe import get_universe

CACHE = DiskCache("data/cache")
YCACHE = DiskCache("data/cache", ttl_hours=168)
edgar = CompositeProvider(fundamentals=EdgarFundamentals(CACHE), market=YahooProvider(CACHE))
nse = CompositeProvider(fundamentals=NseFundamentals(CACHE), market=YahooProvider(CACHE))

SAMPLES = [
    ("us-smallcap-sample", edgar, [date(y, 7, 15) for y in range(2016, 2025)], 60),
    ("nifty-smallcap250", nse, [date(y, 7, 15) for y in (2021, 2022, 2023, 2024)], 50),
]

store = RunStore("data/mbe.duckdb")
pairs: list[tuple[float, bool]] = []
saved = resolved_n = 0

for universe, provider, cutoffs, limit in SAMPLES:
    tickers = get_universe(universe, cache=YCACHE)[:limit]
    for cutoff in cutoffs:
        later = cutoff + timedelta(days=365)
        if later > date.today():
            continue
        for t in tickers:
            try:
                bundle_then, _ = analyze_as_of(t, provider, cutoff)
                bundle_later, _ = analyze_as_of(t, provider, later)
            except (ProviderError, Exception):
                continue
            if bundle_then.thesis is None or bundle_later.thesis is None:
                continue
            preds = emit_predictions(bundle_then.thesis, as_of=cutoff)
            for p in preds:
                p = p.model_copy(update={"source": "thesis-retro"})
                outcome = resolve_prediction(p, bundle_later.thesis, resolved_on=later)
                store.save_predictions([p])
                store.record_outcome(p, outcome)
                pairs.append((p.confidence, outcome.correct))
                resolved_n += 1
            saved += len(preds)
    print(f"{universe}: ledger now {resolved_n} resolved predictions")

print(f"\n=== RETRO-CALIBRATION ({resolved_n} resolved predictions) ===")
print(f"Brier score: {brier_score(pairs):.3f}  (0 perfect, 0.25 coin-flip)")
print(f"{'bucket':>10s} {'n':>6s} {'stated':>8s} {'observed':>9s} {'gap':>7s}")
for row in reliability_table(pairs):
    print(f"{row['bucket']:>10s} {row['n']:>6d} {row['stated']:>8.0%} "
          f"{row['observed']:>9.0%} {row['gap']:>+7.0%}")

by_kind: dict[str, list[tuple[float, bool]]] = {}
for r in store.resolved_predictions():
    by_kind.setdefault(r["kind"], []).append((r["confidence"], bool(r["correct"])))
print("\nPer kind:")
for kind, kp in by_kind.items():
    print(f"  {kind:24s} n={len(kp):4d}  brier={brier_score(kp):.3f}  "
          f"base-rate-correct={sum(1 for _, o in kp if o)/len(kp):.0%}")
