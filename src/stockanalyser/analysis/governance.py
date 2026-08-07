"""Management & governance lens — 'can you trust them?'

Combines promoter pledging (from ownership), earnings-quality flags (from the
forensic layer, recomputed lightly here) and a capital-allocation read
(ROCE level & trend, dividend discipline)."""
from __future__ import annotations

import numpy as np

from ..models import CompanyData, LensResult, Signal


def _safe(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def analyse(data: CompanyData) -> LensResult:
    res = LensResult(lens="Governance")
    signals: list[Signal] = []
    sub: list[float] = []
    f = data.fundamentals
    o = data.ownership

    # 1. pledging
    if o and o.history and o.history[-1].promoter_pledged is not None:
        pl = o.history[-1].promoter_pledged
        if pl <= 0:
            signals.append(Signal("Promoter pledge", "0%", "Clean — no pledged shares", "bullish", 0.7))
            sub.append(1.0)
        else:
            signals.append(Signal("Promoter pledge", f"{pl}%",
                                  f"⚠ {pl}% pledged — misalignment / distress risk", "warning", 0.8))
            sub.append(float(np.clip(1 - pl / 50, 0, 1)))

    # 2. capital allocation: ROCE level and trend
    if f and len(f.statements) >= 2:
        stmts = f.ordered()
        def roce(s):
            ce = None if s.equity is None or s.total_debt is None else s.equity + s.total_debt
            return _safe(s.ebit, ce)
        r_now = roce(stmts[-1])
        r_then = roce(stmts[0])
        if r_now is not None:
            level_ok = r_now > 0.15
            trend_ok = r_then is not None and r_now >= r_then
            signals.append(Signal("Capital allocation (ROCE)", f"{r_now*100:.1f}%",
                                  ("Earns well above cost of capital" if level_ok else "ROCE below ~15% hurdle")
                                  + (", improving" if trend_ok else ", flat/declining"),
                                  "bullish" if level_ok and trend_ok else "bearish" if not level_ok else "neutral",
                                  0.6))
            sub.append(float(np.clip(r_now / 0.25, 0, 1)))

        # 3. dividend discipline vs profitability
        dps = [s.dividend_per_share for s in stmts if s.dividend_per_share is not None]
        if dps and any(d > 0 for d in dps):
            paying = dps[-1] and dps[-1] > 0
            growing = len(dps) >= 2 and dps[-1] >= dps[0]
            signals.append(Signal("Dividend track record",
                                  f"{dps[-1]}/sh" if paying else "0",
                                  "Consistent, growing payout" if (paying and growing) else "Pays a dividend" if paying else "No dividend",
                                  "bullish" if (paying and growing) else "neutral", 0.4))
            sub.append(0.85 if (paying and growing) else 0.6 if paying else 0.4)

        # 4. earnings honesty: CFO vs PAT (accrual check)
        cfo_sum = sum((s.cfo or 0) for s in stmts)
        pat_sum = sum((s.net_income or 0) for s in stmts)
        ratio = _safe(cfo_sum, pat_sum)
        if ratio is not None:
            signals.append(Signal("Earnings honesty (CFO/PAT)", round(ratio, 2),
                                  "Reported profit backed by cash" if ratio >= 0.8 else "⚠ Profit not converting to cash",
                                  "bullish" if ratio >= 0.8 else "warning", 0.6))
            sub.append(float(np.clip(ratio, 0, 1)))

    if not sub:
        res.summary = "Insufficient data for governance assessment."
        return res

    res.signals = signals
    res.score = round(float(np.mean(sub) * 100), 1)
    warnings = [s.name for s in signals if s.stance == "warning"]
    res.summary = (
        f"Governance score {res.score}/100. "
        + ("⚠ Concerns: " + ", ".join(warnings) + "." if warnings
           else "No major governance concerns detected.")
    )
    return res
