"""Sector / top-down lens: relative strength vs index & sector, peer context,
and a top-down↔bottom-up reconciliation."""
from __future__ import annotations

import numpy as np

from ..models import CompanyData, LensResult, Signal


def _return_over(frame, days: int) -> float | None:
    if frame is None or len(frame) < days + 1:
        return None
    c = frame["close"]
    return round((c.iloc[-1] / c.iloc[-days - 1] - 1) * 100, 1)


def analyse(data: CompanyData) -> LensResult:
    res = LensResult(lens="Sector")
    if data.prices is None:
        res.summary = "No price data for sector/relative-strength analysis."
        return res

    stock = data.prices.frame
    signals: list[Signal] = []
    sub: list[float] = []
    res.data["sector"] = data.company.sector
    res.data["peers"] = data.peers

    windows = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    rs_table = {}
    bench = data.benchmarks.get("NIFTY") or data.benchmarks.get("SPX")
    sect = data.benchmarks.get("SECTOR")
    for label, d in windows.items():
        sr = _return_over(stock, d)
        br = _return_over(bench.frame, d) if bench else None
        cr = _return_over(sect.frame, d) if sect else None
        rs_table[label] = {"stock": sr, "index": br, "sector": cr,
                           "rs_vs_index": round(sr - br, 1) if (sr is not None and br is not None) else None,
                           "rs_vs_sector": round(sr - cr, 1) if (sr is not None and cr is not None) else None}
    res.data["relative_strength"] = rs_table

    # score on 6M/1Y relative strength vs index
    rs_vals = [rs_table[w]["rs_vs_index"] for w in ("3M", "6M", "1Y") if rs_table[w]["rs_vs_index"] is not None]
    if rs_vals:
        avg_rs = float(np.mean(rs_vals))
        stance = "bullish" if avg_rs > 5 else "bearish" if avg_rs < -5 else "neutral"
        signals.append(Signal("Relative strength vs index", f"{avg_rs:+.1f}%",
                              "Outperforming the market" if avg_rs > 0 else "Lagging the market", stance, 0.6))
        sub.append(float(np.clip((avg_rs + 25) / 50, 0, 1)))

    rs_sec = [rs_table[w]["rs_vs_sector"] for w in ("3M", "6M", "1Y") if rs_table[w]["rs_vs_sector"] is not None]
    if rs_sec:
        avg = float(np.mean(rs_sec))
        signals.append(Signal("Relative strength vs sector", f"{avg:+.1f}%",
                              "Leader within its sector" if avg > 0 else "Laggard within its sector",
                              "bullish" if avg > 0 else "bearish", 0.5))
        sub.append(float(np.clip((avg + 20) / 40, 0, 1)))

    # top-down vs bottom-up reconciliation note
    sector_1y = rs_table["1Y"]["sector"]
    stock_1y = rs_table["1Y"]["stock"]
    if sector_1y is not None and stock_1y is not None:
        if sector_1y > 10 and stock_1y > sector_1y:
            note = "Rising sector AND leading it — top-down and bottom-up agree (tailwind)."
        elif sector_1y < 0 and stock_1y > 0:
            note = "Swimming against a weak sector — bottom-up strength despite top-down drag."
        elif sector_1y > 10 and stock_1y < sector_1y:
            note = "In a hot sector but lagging peers — a laggard, not a leader."
        else:
            note = "Sector and stock broadly in line."
        signals.append(Signal("Top-down / bottom-up", "", note, "neutral", 0.4))
        res.data["reconciliation"] = note

    if data.peers:
        signals.append(Signal("Peer set", ", ".join(data.peers),
                              "Compare valuation & quality against these names", "neutral", 0.3))

    res.signals = signals
    res.score = round(float(np.mean(sub) * 100), 1) if sub else None
    res.summary = (
        f"Sector: {data.company.sector or 'n/a'}. "
        + (f"6M relative strength vs index {rs_table['6M']['rs_vs_index']:+}% ." if rs_table['6M']['rs_vs_index'] is not None else "")
        + (f" {res.data.get('reconciliation','')}" if res.data.get("reconciliation") else "")
    )
    return res
