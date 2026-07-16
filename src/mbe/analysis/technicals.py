"""Technical state computation. Pure pandas, no TA-lib dependency.

All indicators follow standard definitions (Wilder smoothing for RSI/ATR/ADX).
Insufficient history yields None fields and an 'unknown' trend, never errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mbe.models.analysis import TechnicalState
from mbe.models.company import PriceHistory


def _last(series: pd.Series) -> float | None:
    if series.empty:
        return None
    v = series.iloc[-1]
    return None if pd.isna(v) else float(v)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    # no losses at all -> RSI is 100 by definition
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    return out


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = atr(df, n)
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / tr
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _obv_slope(df: pd.DataFrame, lookback: int = 20) -> float | None:
    if len(df) < lookback + 2:
        return None
    direction = np.sign(df["close"].diff().fillna(0))
    obv = (direction * df["volume"]).cumsum()
    vol_sum = df["volume"].iloc[-lookback:].sum()
    if vol_sum == 0:
        return None
    return float((obv.iloc[-1] - obv.iloc[-lookback - 1]) / vol_sum)


def _cmf(df: pd.DataFrame, n: int = 20) -> float | None:
    if len(df) < n:
        return None
    window = df.iloc[-n:]
    hl_range = window["high"] - window["low"]
    mfm = ((window["close"] - window["low"]) - (window["high"] - window["close"])).where(
        hl_range > 0, 0.0
    ) / hl_range.replace(0, np.nan)
    mfv = (mfm.fillna(0) * window["volume"]).sum()
    vol = window["volume"].sum()
    return float(mfv / vol) if vol > 0 else None


def _return(close: pd.Series, days: int) -> float | None:
    if len(close) < days + 1:
        return None
    past = close.iloc[-days - 1]
    return float(close.iloc[-1] / past - 1) if past > 0 else None


def _trend_state(
    price: float | None,
    sma50: float | None,
    sma150: float | None,
    sma200: float | None,
    sma200_slope: float | None,
    dist_low: float | None,
    dist_high: float | None,
) -> str:
    required = [price, sma50, sma150, sma200, sma200_slope, dist_low, dist_high]
    if any(v is None for v in required):
        return "unknown"
    # Minervini-style stage-2 template
    if (
        price > sma50 > sma150 > sma200
        and sma200_slope > 0
        and dist_low >= 0.30
        and dist_high >= -0.25
    ):
        return "strong_up"
    if price > sma200 and sma200_slope > 0:
        return "up"
    if price < sma50 and price < sma150 < sma200 and sma200_slope < 0:
        return "strong_down"
    if price < sma200 and sma200_slope < 0:
        return "down"
    return "sideways"


def compute_technicals(
    prices: PriceHistory, benchmark: PriceHistory | None = None
) -> TechnicalState:
    df = prices.df
    close = df["close"]
    price = _last(close)

    sma50 = _last(close.rolling(50).mean())
    sma150 = _last(close.rolling(150).mean())
    sma200_series = close.rolling(200).mean()
    sma200 = _last(sma200_series)
    sma200_slope = None
    if len(sma200_series.dropna()) >= 21:
        past = sma200_series.iloc[-21]
        if not pd.isna(past) and past != 0:
            sma200_slope = float((sma200_series.iloc[-1] - past) / past)

    atr_series = atr(df)
    atr_last = _last(atr_series)
    atr_pct = (atr_last / price * 100) if (atr_last is not None and price) else None

    # Bollinger %B over 20 days
    pct_b = None
    if len(close) >= 20:
        mid = close.rolling(20).mean().iloc[-1]
        std = close.rolling(20).std().iloc[-1]
        if not pd.isna(std) and std > 0:
            pct_b = float((close.iloc[-1] - (mid - 2 * std)) / (4 * std))

    stoch = None
    if len(df) >= 14:
        low14 = df["low"].iloc[-14:].min()
        high14 = df["high"].iloc[-14:].max()
        if high14 > low14:
            stoch = float((close.iloc[-1] - low14) / (high14 - low14) * 100)

    macd_hist = None
    if len(close) >= 35:
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = float((macd - signal).iloc[-1])

    dist_high = dist_low = None
    if len(df) >= 30 and price:
        window = df.iloc[-252:]
        high52 = window["high"].max()
        low52 = window["low"].min()
        if high52 > 0:
            dist_high = float(price / high52 - 1)
        if low52 > 0:
            dist_low = float(price / low52 - 1)

    ret63 = _return(close, 63)
    ret126 = _return(close, 126)
    ret252 = _return(close, 252)
    rel_strength = None
    if benchmark is not None and ret63 is not None:
        bench_ret = _return(benchmark.df["close"], 63)
        if bench_ret is not None:
            rel_strength = ret63 - bench_ret

    traded_value = None
    if len(df) >= 20:
        traded_value = float((df["close"] * df["volume"]).iloc[-20:].mean())

    if atr_pct is None:
        vol_regime = "unknown"
    elif atr_pct < 2:
        vol_regime = "low"
    elif atr_pct <= 4:
        vol_regime = "medium"
    else:
        vol_regime = "high"

    state = TechnicalState(
        price=price,
        sma50=sma50,
        sma150=sma150,
        sma200=sma200,
        price_vs_200sma=(price / sma200 - 1) if (price and sma200) else None,
        sma200_slope_20d=sma200_slope,
        rsi14=_last(rsi(close)),
        macd_hist=macd_hist,
        atr_pct=atr_pct,
        bollinger_pct_b=pct_b,
        stochastic14=stoch,
        adx14=_last(adx(df)),
        obv_slope_20d=_obv_slope(df),
        cmf20=_cmf(df),
        dist_52w_high=dist_high,
        dist_52w_low=dist_low,
        return_63d=ret63,
        return_126d=ret126,
        return_252d=ret252,
        relative_strength_63d=rel_strength,
        trend_state=_trend_state(
            price, sma50, sma150, sma200, sma200_slope, dist_low, dist_high
        ),
        volatility_regime=vol_regime,
        avg_traded_value_20d=traded_value,
    )

    numeric_fields = [
        state.price, state.sma50, state.sma150, state.sma200, state.price_vs_200sma,
        state.sma200_slope_20d, state.rsi14, state.macd_hist, state.atr_pct,
        state.bollinger_pct_b, state.stochastic14, state.adx14, state.obv_slope_20d,
        state.cmf20, state.dist_52w_high, state.dist_52w_low, state.return_63d,
        state.avg_traded_value_20d,
    ]
    state.completeness = sum(1 for v in numeric_fields if v is not None) / len(numeric_fields)
    return state
