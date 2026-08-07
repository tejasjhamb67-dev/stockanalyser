"""Quality & forensics lens — 'are the numbers real?'

Piotroski F-score (health), Altman Z-score (distress), Beneish M-score
(earnings-manipulation probability), plus a cash-vs-profit accruals check.
Each is computed defensively: if the inputs aren't present it is skipped, not faked.
"""
from __future__ import annotations

from ..models import CompanyData, FinancialStatement, LensResult, Signal


def _safe(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def piotroski(prev: FinancialStatement, cur: FinancialStatement) -> tuple[int, list[str]]:
    """9 binary tests. Returns (score 0-9, list of passed-test labels)."""
    passed: list[str] = []

    def add(cond, label):
        if cond:
            passed.append(label)

    # profitability (4)
    add((cur.net_income or 0) > 0, "Positive net income")
    add((cur.cfo or 0) > 0, "Positive operating cash flow")
    roa_c = _safe(cur.net_income, cur.total_assets)
    roa_p = _safe(prev.net_income, prev.total_assets)
    add(roa_c is not None and roa_p is not None and roa_c > roa_p, "Rising ROA")
    add(cur.cfo is not None and cur.net_income is not None and cur.cfo > cur.net_income, "CFO > net income (quality of earnings)")
    # leverage/liquidity (3)
    de_c = _safe(cur.total_debt, cur.total_assets)
    de_p = _safe(prev.total_debt, prev.total_assets)
    add(de_c is not None and de_p is not None and de_c < de_p, "Falling leverage")
    cr_c = _safe(cur.current_assets, cur.current_liabilities)
    cr_p = _safe(prev.current_assets, prev.current_liabilities)
    add(cr_c is not None and cr_p is not None and cr_c > cr_p, "Rising current ratio")
    add(cur.shares_outstanding is not None and prev.shares_outstanding is not None
        and cur.shares_outstanding <= prev.shares_outstanding, "No share dilution")
    # efficiency (2)
    gm_c = _safe(cur.ebitda, cur.revenue)
    gm_p = _safe(prev.ebitda, prev.revenue)
    add(gm_c is not None and gm_p is not None and gm_c > gm_p, "Rising margin")
    at_c = _safe(cur.revenue, cur.total_assets)
    at_p = _safe(prev.revenue, prev.total_assets)
    add(at_c is not None and at_p is not None and at_c > at_p, "Rising asset turnover")
    return len(passed), passed


def altman_z(s: FinancialStatement, market_cap: float | None) -> float | None:
    """Altman Z for manufacturers. Uses market cap for equity value if available."""
    if not all(v is not None for v in (s.total_assets, s.current_assets, s.current_liabilities,
                                       s.revenue, s.ebit, s.equity, s.total_debt)):
        return None
    ta = s.total_assets
    wc = s.current_assets - s.current_liabilities
    re = s.equity  # proxy: retained earnings ≈ book equity
    ebit = s.ebit
    mve = market_cap if market_cap else s.equity
    tl = s.total_debt + s.current_liabilities
    sales = s.revenue
    z = (1.2 * wc / ta + 1.4 * re / ta + 3.3 * ebit / ta
         + 0.6 * mve / max(tl, 1e-9) + 1.0 * sales / ta)
    return round(z, 2)


def beneish_m(prev: FinancialStatement, cur: FinancialStatement) -> float | None:
    """Beneish M-score (5-variable simplified). M > -1.78 ⇒ likely manipulator."""
    try:
        dsri = (_safe(cur.receivables, cur.revenue)) / (_safe(prev.receivables, prev.revenue))
        # gross margin index (using EBITDA margin as proxy)
        gmi = (_safe(prev.ebitda, prev.revenue)) / (_safe(cur.ebitda, cur.revenue))
        # asset quality index — non-current, non-PPE proxy via (1 - CA/TA)
        aqi = (1 - _safe(cur.current_assets, cur.total_assets)) / (1 - _safe(prev.current_assets, prev.total_assets))
        sgi = cur.revenue / prev.revenue
        # total accruals to total assets
        tata = ((cur.net_income - (cur.cfo or 0)) / cur.total_assets)
    except (TypeError, ZeroDivisionError):
        return None
    m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 4.679 * tata)
    return round(m, 2)


def analyse(data: CompanyData) -> LensResult:
    res = LensResult(lens="Quality")
    f = data.fundamentals
    if not f or len(f.statements) < 2:
        res.summary = "Need at least two periods for forensic analysis."
        return res

    stmts = f.ordered()
    prev, cur = stmts[-2], stmts[-1]
    signals: list[Signal] = []
    sub: list[float] = []

    # Piotroski
    fscore, passed = piotroski(prev, cur)
    res.data["piotroski"] = {"score": fscore, "passed": passed}
    fstance = "bullish" if fscore >= 7 else "bearish" if fscore <= 3 else "neutral"
    signals.append(Signal("Piotroski F-score", f"{fscore}/9",
                          "Financially strong" if fscore >= 7 else "Financially weak" if fscore <= 3 else "Middling",
                          fstance, 0.7))
    sub.append(fscore / 9)

    # Altman Z
    z = altman_z(cur, data.company.market_cap)
    if z is not None:
        res.data["altman_z"] = z
        zstance = "bullish" if z > 3 else "bearish" if z < 1.8 else "warning"
        zinterp = ("Safe zone" if z > 3 else "Distress zone — bankruptcy risk" if z < 1.8 else "Grey zone")
        signals.append(Signal("Altman Z-score", z, zinterp, zstance, 0.7))
        sub.append(min(1.0, max(0.0, (z - 1.0) / 3.0)))

    # Beneish M
    m = beneish_m(prev, cur)
    if m is not None:
        res.data["beneish_m"] = m
        manip = m > -1.78
        signals.append(Signal("Beneish M-score", m,
                              "⚠ Likely earnings manipulation" if manip else "No manipulation flag",
                              "warning" if manip else "bullish", 0.7))
        sub.append(0.15 if manip else 0.9)

    # accruals / cash backing over the full window
    cfo_sum = sum((s.cfo or 0) for s in stmts)
    pat_sum = sum((s.net_income or 0) for s in stmts)
    cfo_pat = round(_safe(cfo_sum, pat_sum), 2) if _safe(cfo_sum, pat_sum) is not None else None
    if cfo_pat is not None:
        res.data["cfo_to_pat_cumulative"] = cfo_pat
        good = cfo_pat >= 0.8
        signals.append(Signal("Cumulative CFO/PAT", cfo_pat,
                              "Profits backed by cash" if good else "Profits NOT converting to cash — accrual red flag",
                              "bullish" if good else "warning", 0.7))
        sub.append(min(1.0, max(0.0, cfo_pat)))

    res.signals = signals
    res.score = round(sum(sub) / len(sub) * 100, 1) if sub else None

    flags = [s.name for s in signals if s.stance == "warning"]
    res.summary = (
        f"Forensic score {res.score}/100. Piotroski {fscore}/9"
        + (f", Altman Z {z}" if z is not None else "")
        + (f", Beneish M {m}" if m is not None else "")
        + (f", cumulative CFO/PAT {cfo_pat}." if cfo_pat is not None else ".")
        + (f" ⚠ Red flags: {', '.join(flags)}." if flags else " No forensic red flags.")
    )
    return res
