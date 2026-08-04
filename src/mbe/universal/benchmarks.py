"""Additive benchmark table(s) for metrics the Universal Research Score
scores that mbe.scoring.benchmarks does not define a threshold for.
Kept in a separate module — never edits mbe.scoring.benchmarks — so the
existing Multibagger/Investment score stays byte-identical (a hard
compatibility requirement of this feature)."""

from __future__ import annotations

NET_MARGIN_THRESHOLDS: list[tuple[float, int]] = [
    (0.15, 90), (0.10, 75), (0.05, 60), (0.0, 40),
]


def score_net_margin(value: float) -> tuple[int, str]:
    for threshold, points in NET_MARGIN_THRESHOLDS:
        if value >= threshold:
            return points, f">= {threshold:.2f} earns {points}"
    return 10, "negative net margin, floor 10"
