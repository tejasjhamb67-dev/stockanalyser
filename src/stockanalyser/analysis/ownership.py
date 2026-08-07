"""Ownership & flows lens: shareholding trend (promoter/FII/DII), pledging,
and bulk/block deal activity as an independent read on the price move."""
from __future__ import annotations

import numpy as np

from ..models import CompanyData, LensResult, Signal


def _trend(vals: list[float | None]) -> float | None:
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return None
    return round(v[-1] - v[0], 2)


def analyse(data: CompanyData) -> LensResult:
    res = LensResult(lens="Ownership")
    o = data.ownership
    if not o or not o.history:
        res.summary = "No shareholding data available."
        return res

    hist = o.history
    latest = hist[-1]
    signals: list[Signal] = []
    sub: list[float] = []

    res.data["latest"] = {
        "promoter": latest.promoter, "pledged": latest.promoter_pledged,
        "fii": latest.fii, "dii": latest.dii, "public": latest.public,
    }
    res.data["series"] = {
        "periods": [h.period for h in hist],
        "promoter": [h.promoter for h in hist],
        "pledged": [h.promoter_pledged for h in hist],
        "fii": [h.fii for h in hist],
        "dii": [h.dii for h in hist],
    }

    # promoter holding & trend
    prom_trend = _trend([h.promoter for h in hist])
    if latest.promoter is not None:
        stance = "bullish" if latest.promoter >= 50 else "neutral"
        note = f"Promoter holds {latest.promoter}%"
        if prom_trend is not None and prom_trend < -1:
            note += f" but has been trimming ({prom_trend:+.1f}pp) — watch"
            stance = "warning"
        elif prom_trend is not None and prom_trend > 0.5:
            note += f" and rising ({prom_trend:+.1f}pp) — confidence"
        signals.append(Signal("Promoter holding", f"{latest.promoter}%", note, stance, 0.6))
        sub.append(float(np.clip(latest.promoter / 75, 0, 1)))

    # pledging — the single biggest governance red flag here
    if latest.promoter_pledged is not None:
        pl = latest.promoter_pledged
        pl_trend = _trend([h.promoter_pledged for h in hist])
        if pl <= 0:
            signals.append(Signal("Promoter pledge", "0%", "No pledged shares — clean", "bullish", 0.7))
            sub.append(1.0)
        else:
            rising = pl_trend is not None and pl_trend > 2
            signals.append(Signal("Promoter pledge", f"{pl}%",
                                  f"⚠ {pl}% of promoter stake pledged"
                                  + (f" and RISING ({pl_trend:+.1f}pp) — distress risk" if rising else ""),
                                  "warning", 0.8))
            sub.append(float(np.clip(1 - pl / 50, 0, 1)))

    # institutional flows
    fii_trend = _trend([h.fii for h in hist])
    dii_trend = _trend([h.dii for h in hist])
    if fii_trend is not None or dii_trend is not None:
        inst = (fii_trend or 0) + (dii_trend or 0)
        stance = "bullish" if inst > 0 else "bearish" if inst < -0.5 else "neutral"
        signals.append(Signal("Institutional flows", f"{inst:+.1f}pp",
                              f"FII {fii_trend:+.1f}pp, DII {dii_trend:+.1f}pp over the window"
                              if fii_trend is not None and dii_trend is not None else "partial data",
                              stance, 0.5))
        sub.append(float(np.clip((inst + 3) / 6, 0, 1)))

    # bulk / block deals
    if o.bulk_block_deals:
        for d in o.bulk_block_deals:
            signals.append(Signal("Bulk/Block deal", d.get("action", "?"),
                                  f"{d.get('party','?')} {d.get('action','?')} ~{d.get('qty_pct','?')}% "
                                  f"(~{d.get('days_ago','?')}d ago)",
                                  "warning" if d.get("action") == "SELL" else "bullish", 0.4))

    res.signals = signals
    res.score = round(float(np.mean(sub) * 100), 1) if sub else None
    res.summary = (
        f"Ownership: promoter {latest.promoter}% "
        f"(pledge {latest.promoter_pledged}%), FII {latest.fii}%, DII {latest.dii}%. "
        + ("⚠ Pledging present — governance risk. " if (latest.promoter_pledged or 0) > 0 else "")
        + (f"FII {'accumulating' if (fii_trend or 0) > 0 else 'reducing'}." if fii_trend is not None else "")
    )
    return res
