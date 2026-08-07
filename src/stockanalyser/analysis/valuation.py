"""Valuation lens: relative multiples + a transparent two-stage DCF.

Assumptions are always exposed in res.data so the dashboard can show *why* a
fair value came out where it did — never a black-box number.
"""
from __future__ import annotations

import numpy as np

from ..config import ValuationConfig
from ..models import CompanyData, LensResult, Signal


def _safe(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def relative_multiples(data: CompanyData) -> dict[str, float | None]:
    f = data.fundamentals
    s = f.latest
    price = f.price
    shares = f.shares_outstanding or (s.shares_outstanding if s else None)
    out: dict[str, float | None] = {"price": price, "shares": shares}
    if not (s and price and shares):
        return out
    eps = _safe(s.net_income, shares)
    bvps = _safe(s.equity, shares)
    out["eps"] = round(eps, 2) if eps else None
    out["pe"] = round(price / eps, 1) if eps and eps > 0 else None
    out["pb"] = round(price / bvps, 2) if bvps and bvps > 0 else None
    mcap = price * shares
    ev = mcap + (s.total_debt or 0) - (s.cash or 0)
    out["ev_ebitda"] = round(ev / s.ebitda, 1) if s.ebitda and s.ebitda > 0 else None
    out["div_yield"] = round((s.dividend_per_share or 0) / price * 100, 2) if s.dividend_per_share else 0.0
    out["market_cap"] = round(mcap, 1)
    return out


def two_stage_dcf(data: CompanyData, cfg: ValuationConfig) -> dict[str, float | None]:
    """FCF-based two-stage DCF. Stage-1 growth from historical FCF/PAT trend,
    fading to terminal growth; discounted at cfg.discount_rate."""
    f = data.fundamentals
    stmts = f.ordered()
    if len(stmts) < 2:
        return {"fair_value": None}
    fcfs = [s.fcf for s in stmts if s.fcf is not None]
    base_fcf = fcfs[-1] if fcfs else None
    if base_fcf is None or base_fcf <= 0:
        # fall back to PAT if FCF is negative/missing
        base_fcf = stmts[-1].net_income
    if base_fcf is None or base_fcf <= 0:
        return {"fair_value": None, "note": "No positive FCF/PAT base for DCF"}

    # historical growth of the base metric
    series = fcfs if len(fcfs) >= 2 else [s.net_income for s in stmts if s.net_income]
    g0 = 0.10
    if len(series) >= 2 and series[0] and series[0] > 0:
        g0 = (series[-1] / series[0]) ** (1 / (len(series) - 1)) - 1
    g0 = float(np.clip(g0, -0.05, 0.25))

    r = cfg.discount_rate
    gt = cfg.terminal_growth
    pv = 0.0
    fcf = base_fcf
    for yr in range(1, cfg.dcf_years + 1):
        g = g0 + (gt - g0) * (yr / cfg.dcf_years) if cfg.fade_to_terminal else g0
        fcf *= (1 + g)
        pv += fcf / (1 + r) ** yr
    terminal = fcf * (1 + gt) / (r - gt)
    pv += terminal / (1 + r) ** cfg.dcf_years

    shares = f.shares_outstanding or (stmts[-1].shares_outstanding)
    net_debt = (stmts[-1].total_debt or 0) - (stmts[-1].cash or 0)
    equity_value = pv - net_debt
    fair = equity_value / shares if shares else None
    return {
        "fair_value": round(fair, 1) if fair else None,
        "enterprise_value": round(pv, 1),
        "stage1_growth": round(g0 * 100, 1),
        "terminal_growth": round(gt * 100, 1),
        "discount_rate": round(r * 100, 1),
        "base_fcf": round(base_fcf, 1),
    }


def analyse(data: CompanyData, cfg: ValuationConfig | None = None) -> LensResult:
    cfg = cfg or ValuationConfig()
    res = LensResult(lens="Valuation")
    f = data.fundamentals
    if not f or not f.latest or not f.price:
        res.summary = "No price/fundamentals for valuation."
        return res

    mult = relative_multiples(data)
    dcf = two_stage_dcf(data, cfg)
    res.data["multiples"] = mult
    res.data["dcf"] = dcf

    signals: list[Signal] = []
    sub: list[float] = []

    pe = mult.get("pe")
    if pe:
        # cheaper = better; anchor: PE 15 = fair, 40+ = expensive, <10 = cheap
        score = float(np.clip((40 - pe) / 30, 0, 1))
        stance = "bullish" if pe < 18 else "bearish" if pe > 35 else "neutral"
        signals.append(Signal("P/E", pe, f"{'Cheap' if pe<18 else 'Expensive' if pe>35 else 'Fair'} on earnings", stance, 0.6))
        sub.append(score)
    pb = mult.get("pb")
    if pb:
        signals.append(Signal("P/B", pb, f"{'Below' if pb<3 else 'Above'} 3x book", "bullish" if pb < 3 else "neutral", 0.4))
        sub.append(float(np.clip((6 - pb) / 5, 0, 1)))
    eve = mult.get("ev_ebitda")
    if eve:
        signals.append(Signal("EV/EBITDA", eve, f"{'Reasonable' if eve<15 else 'Rich'}", "bullish" if eve < 15 else "bearish" if eve > 25 else "neutral", 0.5))
        sub.append(float(np.clip((25 - eve) / 20, 0, 1)))
    dy = mult.get("div_yield")
    if dy is not None:
        signals.append(Signal("Dividend yield", f"{dy}%", "Income support" if dy > 1 else "Minimal yield", "neutral", 0.3))

    # DCF vs price
    fair = dcf.get("fair_value")
    price = mult.get("price")
    if fair and price:
        upside = (fair / price - 1) * 100
        res.data["dcf_upside_pct"] = round(upside, 1)
        stance = "bullish" if upside > 15 else "bearish" if upside < -15 else "neutral"
        signals.append(Signal("DCF fair value", fair,
                              f"{upside:+.0f}% vs price {price:.0f} "
                              f"(stage-1 growth {dcf.get('stage1_growth')}%, disc {dcf.get('discount_rate')}%)",
                              stance, 0.5))
        sub.append(float(np.clip((upside + 30) / 60, 0, 1)))

    res.signals = signals
    res.score = round(float(np.mean(sub) * 100), 1) if sub else None

    verdict = "cheap" if (res.score or 0) >= 60 else "expensive" if (res.score or 0) <= 35 else "fairly valued"
    res.summary = (
        f"Valuation looks {verdict} (score {res.score}/100). "
        f"P/E {pe}, P/B {pb}, EV/EBITDA {eve}. "
        + (f"DCF fair value ~{fair} vs price {price:.0f} "
           f"({res.data.get('dcf_upside_pct'):+.0f}%)." if fair and price else "DCF not computable.")
    )
    return res
