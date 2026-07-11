import numpy as np
import pandas as pd
import pytest

from mbe.analysis.technicals import compute_technicals
from mbe.models.company import PriceHistory


def _prices(closes, volume=1000.0) -> PriceHistory:
    closes = pd.Series(closes, dtype=float)
    idx = pd.bdate_range("2023-01-02", periods=len(closes))
    df = pd.DataFrame(
        {
            "open": closes.values,
            "high": closes.values * 1.01,
            "low": closes.values * 0.99,
            "close": closes.values,
            "volume": volume,
        },
        index=idx,
    )
    return PriceHistory(df=df)


def test_sma_on_linear_series():
    t = compute_technicals(_prices(np.arange(1, 301)))
    assert t.sma200 == pytest.approx(np.mean(np.arange(101, 301)))  # 200.5
    assert t.sma50 == pytest.approx(np.mean(np.arange(251, 301)))  # 275.5
    assert t.price == pytest.approx(300.0)
    assert t.price_vs_200sma == pytest.approx(300 / 200.5 - 1)


def test_rsi_all_gains_is_100():
    t = compute_technicals(_prices(np.arange(1, 101)))
    assert t.rsi14 == pytest.approx(100.0, abs=0.01)


def test_constant_series_has_zero_atr_and_flat_macd():
    t = compute_technicals(_prices(np.full(300, 50.0)))
    # high/low fixture spread is 2% of price, so ATR% reflects only that band
    assert t.macd_hist == pytest.approx(0.0, abs=1e-9)
    assert t.trend_state == "sideways"
    assert t.rsi14 is None or 40 <= t.rsi14 <= 60  # no gains, no losses


def test_uptrend_classified_strong_up():
    t = compute_technicals(_prices(np.arange(1, 301)))
    assert t.trend_state == "strong_up"
    assert t.dist_52w_high == pytest.approx(0.0, abs=0.02)
    assert t.dist_52w_low > 0.3


def test_downtrend_classified_down():
    t = compute_technicals(_prices(np.linspace(300, 30, 300)))
    assert t.trend_state in ("down", "strong_down")
    assert t.rsi14 < 35


def test_relative_strength_vs_benchmark():
    stock = _prices(np.linspace(100, 110, 300))  # +10% overall, ~+2.3% per 63d
    bench = _prices(np.full(300, 100.0))
    t = compute_technicals(stock, bench)
    expected = 110 / stock.df["close"].iloc[-64] - 1
    assert t.relative_strength_63d == pytest.approx(expected, abs=1e-6)


def test_short_history_degrades_to_none_not_error():
    t = compute_technicals(_prices(np.arange(1, 51)))
    assert t.sma200 is None
    assert t.trend_state == "unknown"
    assert t.completeness < 1.0


def test_traded_value():
    t = compute_technicals(_prices(np.full(300, 50.0), volume=2000.0))
    assert t.avg_traded_value_20d == pytest.approx(50.0 * 2000.0)
