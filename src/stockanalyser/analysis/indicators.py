"""Pure technical-indicator functions on an OHLCV DataFrame.

Kept free of any 'lens' logic so they're independently testable and reusable.
Everything operates on a pandas DataFrame with open/high/low/close/volume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=max(2, window // 2)).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100.0).where(avg_loss != 0, 100.0)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def bollinger(close: pd.Series, window: int = 20, sigma: float = 2.0):
    mid = sma(close, window)
    sd = close.rolling(window, min_periods=max(2, window // 2)).std()
    return mid - sigma * sd, mid, mid + sigma * sd


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0.0))
    return (direction * df["volume"]).cumsum()


def vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).rolling(window, min_periods=1).sum()
    vv = df["volume"].rolling(window, min_periods=1).sum().replace(0, np.nan)
    return pv / vv


def volume_zscore(df: pd.DataFrame, window: int = 20) -> pd.Series:
    v = df["volume"].astype(float)
    mean = v.rolling(window, min_periods=5).mean()
    std = v.rolling(window, min_periods=5).std().replace(0, np.nan)
    return (v - mean) / std


def support_resistance(df: pd.DataFrame, window: int = 20, lookback: int = 120):
    """Swing-based S/R: recent pivot lows/highs. Returns (supports, resistances)
    as sorted lists of price levels near the current price."""
    recent = df.tail(lookback)
    highs, lows = recent["high"], recent["low"]
    piv_hi, piv_lo = [], []
    k = max(2, window // 4)
    for i in range(k, len(recent) - k):
        seg_hi = highs.iloc[i - k:i + k + 1]
        seg_lo = lows.iloc[i - k:i + k + 1]
        if highs.iloc[i] == seg_hi.max():
            piv_hi.append(float(highs.iloc[i]))
        if lows.iloc[i] == seg_lo.min():
            piv_lo.append(float(lows.iloc[i]))
    price = float(df["close"].iloc[-1])
    supports = sorted({round(p, 2) for p in piv_lo if p < price}, reverse=True)[:3]
    resistances = sorted({round(p, 2) for p in piv_hi if p > price})[:3]
    return supports, resistances


def fib_retracements(df: pd.DataFrame, lookback: int = 180) -> dict[str, float]:
    seg = df.tail(lookback)
    hi, lo = float(seg["high"].max()), float(seg["low"].min())
    diff = hi - lo
    return {f"{int(r*100)}%": round(hi - diff * r, 2)
            for r in (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)}


def realised_vol(close: pd.Series, window: int = 20) -> float:
    rets = np.log(close / close.shift(1)).dropna()
    if len(rets) < window:
        return float("nan")
    return float(rets.tail(window).std() * np.sqrt(252) * 100)
