"""P2.4 sector rotation tests: multi-horizon returns, grouping, aggregation,
leave-one-out pillar, augmented score, themes table, screen/harness wiring.
All offline; stub providers follow the tests/test_pipeline.py pattern."""

import numpy as np
import pandas as pd
import pytest

from mbe.analysis.technicals import compute_technicals
from mbe.models.company import PriceHistory


def _price_history(closes) -> PriceHistory:
    closes = pd.Series(closes, dtype=float)
    idx = pd.bdate_range("2022-01-03", periods=len(closes))
    return PriceHistory(
        df=pd.DataFrame(
            {
                "open": closes.values,
                "high": closes.values * 1.01,
                "low": closes.values * 0.99,
                "close": closes.values,
                "volume": 1_000_000.0,
            },
            index=idx,
        )
    )


def test_multi_horizon_returns():
    closes = list(np.linspace(100, 200, 300))
    state = compute_technicals(_price_history(closes), None)
    assert state.return_126d == pytest.approx(closes[-1] / closes[-127] - 1)
    assert state.return_252d == pytest.approx(closes[-1] / closes[-253] - 1)


def test_multi_horizon_returns_none_on_short_history():
    closes = list(np.linspace(100, 120, 130))
    state = compute_technicals(_price_history(closes), None)
    assert state.return_126d is not None
    assert state.return_252d is None


from mbe.scoring.benchmarks import score_metric


def test_sector_benchmark_tables():
    assert score_metric("sector_rel_strength_6m", 0.06)[0] == 75
    assert score_metric("sector_rel_strength_6m", -0.20)[0] == 5  # floor
    assert score_metric("sector_rel_strength_12m", 0.30)[0] == 90
    assert score_metric("sector_rev_accel", 0.03)[0] == 75
    assert score_metric("sector_margin_delta", 0.015)[0] == 75
