"""Technical lens: turn indicators + patterns into signals and a 0–100 score."""
from __future__ import annotations

import numpy as np

from ..config import TechnicalConfig
from ..models import CompanyData, LensResult, Signal
from . import indicators as ind
from . import patterns as pat


def analyse(data: CompanyData, cfg: TechnicalConfig | None = None) -> LensResult:
    cfg = cfg or TechnicalConfig()
    res = LensResult(lens="Technical")
    if data.prices is None or len(data.prices.frame) < 30:
        res.summary = "Insufficient price history for technical analysis."
        return res

    df = data.prices.frame
    close = df["close"]
    price = float(close.iloc[-1])
    signals: list[Signal] = []
    contributions: list[float] = []   # each in [-1, 1], averaged into the score

    # ── trend: SMA cross ──────────────────────────────────────────────
    sma_s = ind.sma(close, cfg.sma_short)
    sma_l = ind.sma(close, cfg.sma_long)
    if not np.isnan(sma_s.iloc[-1]) and not np.isnan(sma_l.iloc[-1]):
        above = sma_s.iloc[-1] > sma_l.iloc[-1]
        # detect a recent cross
        crossed = (sma_s.iloc[-2] <= sma_l.iloc[-2]) if len(sma_s) > 2 else False
        stance = "bullish" if above else "bearish"
        note = f"{cfg.sma_short}DMA {'above' if above else 'below'} {cfg.sma_long}DMA"
        if above and crossed:
            note += " (fresh golden cross)"
        signals.append(Signal("Trend (SMA)", round(float(sma_s.iloc[-1]), 1), note, stance, 0.7))
        contributions.append(0.6 if above else -0.6)

    # price vs long MA
    if not np.isnan(sma_l.iloc[-1]):
        pct = (price / sma_l.iloc[-1] - 1) * 100
        contributions.append(float(np.clip(pct / 20, -1, 1)))

    # ── ADX trend strength ────────────────────────────────────────────
    adx = ind.adx(df)
    if not np.isnan(adx.iloc[-1]):
        a = float(adx.iloc[-1])
        strong = a > 25
        signals.append(Signal("ADX", round(a, 1),
                              "Trending" if strong else "Choppy / no clear trend",
                              "neutral", 0.5))

    # ── RSI ───────────────────────────────────────────────────────────
    rsi = ind.rsi(close, cfg.rsi_period)
    r = float(rsi.iloc[-1])
    if r > 70:
        signals.append(Signal("RSI", round(r, 1), "Overbought", "bearish", 0.6))
        contributions.append(-0.3)
    elif r < 30:
        signals.append(Signal("RSI", round(r, 1), "Oversold", "bullish", 0.6))
        contributions.append(0.3)
    else:
        signals.append(Signal("RSI", round(r, 1), "Neutral momentum", "neutral", 0.4))
        contributions.append((r - 50) / 100)

    # ── MACD ──────────────────────────────────────────────────────────
    macd_line, signal_line, hist = ind.macd(close, cfg.ema_short, cfg.ema_long, cfg.macd_signal)
    macd_bull = macd_line.iloc[-1] > signal_line.iloc[-1]
    signals.append(Signal("MACD", round(float(hist.iloc[-1]), 2),
                          "Above signal (bullish)" if macd_bull else "Below signal (bearish)",
                          "bullish" if macd_bull else "bearish", 0.6))
    contributions.append(0.4 if macd_bull else -0.4)

    # ── Bollinger ─────────────────────────────────────────────────────
    lb, mb, ub = ind.bollinger(close, cfg.bollinger_period, cfg.bollinger_sigma)
    if not np.isnan(ub.iloc[-1]):
        if price > ub.iloc[-1]:
            signals.append(Signal("Bollinger", round(price, 1), "Above upper band — stretched", "bearish", 0.5))
        elif price < lb.iloc[-1]:
            signals.append(Signal("Bollinger", round(price, 1), "Below lower band — stretched down", "bullish", 0.5))

    # ── Volume / OBV ──────────────────────────────────────────────────
    obv = ind.obv(df)
    obv_slope = obv.tail(20).diff().mean()
    vz = ind.volume_zscore(df).iloc[-1]
    signals.append(Signal("OBV trend", "rising" if obv_slope > 0 else "falling",
                          "Volume confirms price" if (obv_slope > 0) == macd_bull else "Volume diverges from price",
                          "bullish" if obv_slope > 0 else "bearish", 0.5))
    contributions.append(0.2 if obv_slope > 0 else -0.2)
    if not np.isnan(vz) and abs(vz) > 2:
        signals.append(Signal("Volume", round(float(vz), 1),
                              "Unusual volume today (z-score)", "warning", 0.5))

    # ── volatility ────────────────────────────────────────────────────
    rv = ind.realised_vol(close)
    if not np.isnan(rv):
        signals.append(Signal("Realised vol", f"{rv:.0f}%", "Annualised 20-day volatility", "neutral", 0.3))

    # store a compact price series so the dashboard/report is self-contained
    tail = df.tail(260)
    res.data["series_dates"] = [str(d.date()) for d in tail.index]
    res.data["series_close"] = [round(float(v), 2) for v in tail["close"]]
    res.data["series_volume"] = [int(v) for v in tail["volume"]]
    res.data["last_price"] = round(price, 2)
    res.data["change_1d_pct"] = round(float(close.pct_change().iloc[-1] * 100), 2)

    # ── structure: S/R + Fib ──────────────────────────────────────────
    supports, resistances = ind.support_resistance(df)
    fib = ind.fib_retracements(df)
    res.data["support"] = supports
    res.data["resistance"] = resistances
    res.data["fibonacci"] = fib

    # ── candlestick patterns ──────────────────────────────────────────
    hits = pat.detect(df, lookback=40)
    recent = hits[-5:]
    for hpat in recent:
        signals.append(Signal(f"Candle: {hpat.pattern}", str(hpat.date.date()),
                              hpat.note, hpat.stance, 0.4))
    if recent:
        last = recent[-1]
        contributions.append(0.25 if last.stance == "bullish"
                             else -0.25 if last.stance == "bearish" else 0.0)
    res.data["patterns"] = [
        {"date": str(h.date.date()), "pattern": h.pattern, "stance": h.stance, "note": h.note}
        for h in recent
    ]

    # ── score ─────────────────────────────────────────────────────────
    raw = float(np.mean(contributions)) if contributions else 0.0
    res.score = round(float(np.clip((raw + 1) / 2 * 100, 0, 100)), 1)
    res.signals = signals

    n_bull = sum(1 for s in signals if s.stance == "bullish")
    n_bear = sum(1 for s in signals if s.stance == "bearish")
    tone = "constructive" if res.score >= 60 else "weak" if res.score <= 40 else "mixed"
    res.summary = (
        f"Technical picture is {tone} (score {res.score}/100): "
        f"{n_bull} bullish vs {n_bear} bearish signals. "
        f"Price {price:.1f}; "
        f"RSI {r:.0f}; MACD {'bullish' if macd_bull else 'bearish'}. "
        + (f"Nearest support ~{supports[0]}, resistance ~{resistances[0]}."
           if supports and resistances else "")
    )
    return res
