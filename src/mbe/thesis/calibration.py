"""Calibration scoring: are the platform's stated confidences honest?

Brier score (lower is better; 0.25 = coin-flip forecasting at 0.5) and a
reliability table comparing stated confidence to observed frequency per bucket.
"""

from __future__ import annotations


def brier_score(pairs: list[tuple[float, bool]]) -> float | None:
    """pairs = (stated confidence, outcome). Mean squared forecast error."""
    if not pairs:
        return None
    return sum((c - (1.0 if o else 0.0)) ** 2 for c, o in pairs) / len(pairs)


def reliability_table(
    pairs: list[tuple[float, bool]], bucket_size: float = 0.2
) -> list[dict]:
    """Bucket by stated confidence; report stated mean vs observed frequency."""
    buckets: dict[int, list[tuple[float, bool]]] = {}
    n_buckets = round(1 / bucket_size)
    for conf, outcome in pairs:
        idx = min(int(conf / bucket_size), n_buckets - 1)
        buckets.setdefault(idx, []).append((conf, outcome))
    table = []
    for idx in sorted(buckets):
        items = buckets[idx]
        lo, hi = idx * bucket_size, (idx + 1) * bucket_size
        stated = sum(c for c, _ in items) / len(items)
        observed = sum(1 for _, o in items if o) / len(items)
        table.append(
            {
                "bucket": f"{lo:.1f}-{hi:.1f}",
                "n": len(items),
                "stated": round(stated, 4),
                "observed": round(observed, 4),
                "gap": round(observed - stated, 4),
            }
        )
    return table


def learn_calibration_map(
    pairs: list[tuple[float, bool]], bucket_size: float = 0.1, min_n: int = 50
) -> list[tuple[float, float, float]]:
    """Bucketwise mapping stated -> observed, learned from resolved predictions.
    Only well-populated buckets (n >= min_n) earn a correction; sparse ranges
    fall back to identity. Returns [(lo, hi, observed), ...]."""
    out = []
    for row in reliability_table(pairs, bucket_size=bucket_size):
        if row["n"] < min_n:
            continue
        lo, hi = (float(x) for x in row["bucket"].split("-"))
        out.append((lo, hi, row["observed"]))
    return out


def apply_calibration(
    confidence: float, calibration_map: list[tuple[float, float, float]]
) -> float:
    """Replace a stated confidence with the observed frequency of its bucket.
    Identity where no correction was learned."""
    for lo, hi, observed in calibration_map:
        if lo <= confidence < hi or (hi >= 1.0 and confidence == 1.0):
            return round(observed, 4)
    return confidence
