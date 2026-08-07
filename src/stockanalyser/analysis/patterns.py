"""Candlestick pattern recognition, Zerodha-style.

Each detector returns a list of (date, pattern, stance, note). Patterns are gated
by prior trend and confirmation where the Varsity module requires it — a hammer is
only a hammer at the bottom of a downtrend, an engulfing needs a real prior body.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Stance = Literal["bullish", "bearish", "neutral"]


@dataclass
class PatternHit:
    date: pd.Timestamp
    pattern: str
    stance: Stance
    note: str


def _body(o, c):
    return abs(c - o)


def _range(h, l):
    return max(h - l, 1e-9)


def _trend(closes: pd.Series, idx: int, window: int = 7) -> str:
    """Cheap prior-trend read using the slope of the preceding window."""
    if idx < window:
        return "none"
    seg = closes.iloc[idx - window:idx]
    change = (seg.iloc[-1] - seg.iloc[0]) / seg.iloc[0]
    if change > 0.03:
        return "up"
    if change < -0.03:
        return "down"
    return "sideways"


def detect(df: pd.DataFrame, lookback: int = 40) -> list[PatternHit]:
    """Scan the last `lookback` bars for the classic single & multi-bar patterns."""
    hits: list[PatternHit] = []
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    closes = c
    start = max(2, len(df) - lookback)

    for i in range(start, len(df)):
        date = df.index[i]
        oi, hi, li, ci = o.iloc[i], h.iloc[i], l.iloc[i], c.iloc[i]
        body = _body(oi, ci)
        rng = _range(hi, li)
        upper = hi - max(oi, ci)
        lower = min(oi, ci) - li
        trend = _trend(closes, i)
        bull = ci > oi

        # ── single-bar ─────────────────────────────────────────────
        if body / rng > 0.9:
            hits.append(PatternHit(date, "Marubozu",
                                   "bullish" if bull else "bearish",
                                   "Full-body candle — strong one-side conviction"))
        elif body / rng < 0.1:
            hits.append(PatternHit(date, "Doji", "neutral",
                                   "Indecision — open ≈ close"))
        elif lower > 2 * body and upper < body and trend == "down":
            hits.append(PatternHit(date, "Hammer", "bullish",
                                   "Long lower wick after a downtrend — buyers stepped in"))
        elif upper > 2 * body and lower < body and trend == "up":
            hits.append(PatternHit(date, "Shooting Star", "bearish",
                                   "Long upper wick after an uptrend — sellers rejected highs"))
        elif lower > 2 * body and upper < body and trend == "up":
            hits.append(PatternHit(date, "Hanging Man", "bearish",
                                   "Long lower wick after an uptrend — warning of a top"))

        # ── two-bar ────────────────────────────────────────────────
        if i >= 1:
            op, cp = o.iloc[i - 1], c.iloc[i - 1]
            prev_bull = cp > op
            prev_body = _body(op, cp)
            # engulfing: current body engulfs previous, opposite colour
            if (bull and not prev_bull and ci >= op and oi <= cp
                    and body > prev_body and trend == "down"):
                hits.append(PatternHit(date, "Bullish Engulfing", "bullish",
                                       "Big up-candle swallows the prior down-candle"))
            elif (not bull and prev_bull and oi >= cp and ci <= op
                  and body > prev_body and trend == "up"):
                hits.append(PatternHit(date, "Bearish Engulfing", "bearish",
                                       "Big down-candle swallows the prior up-candle"))
            # harami: small body inside previous large body
            elif prev_body > body * 2 and max(oi, ci) < max(op, cp) and min(oi, ci) > min(op, cp):
                hits.append(PatternHit(date, "Harami", "neutral",
                                       "Small candle inside prior body — momentum stalling"))

        # ── three-bar star ─────────────────────────────────────────
        if i >= 2:
            o1, c1 = o.iloc[i - 2], c.iloc[i - 2]
            o2, c2 = o.iloc[i - 1], c.iloc[i - 1]
            b1, b2 = _body(o1, c1), _body(o2, c2)
            mid1 = (o1 + c1) / 2
            # morning star: big down, small body, big up closing above mid of first
            if (c1 < o1 and b2 < b1 * 0.5 and bull and ci > mid1 and trend == "down"):
                hits.append(PatternHit(date, "Morning Star", "bullish",
                                       "Three-bar bottom reversal"))
            elif (c1 > o1 and b2 < b1 * 0.5 and not bull and ci < mid1 and trend == "up"):
                hits.append(PatternHit(date, "Evening Star", "bearish",
                                       "Three-bar top reversal"))

    return hits
