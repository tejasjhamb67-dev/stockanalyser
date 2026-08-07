"""Fundamental lens: statements → ratios → DuPont → growth → 0–100 score.

Follows the Zerodha Varsity FA checklist: profitability, leverage & liquidity,
efficiency, growth, and the DuPont decomposition of ROE.
"""
from __future__ import annotations

import numpy as np

from ..models import CompanyData, FinancialStatement, LensResult, Signal


def _safe(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct(x):
    return None if x is None else round(x * 100, 2)


def compute_ratios(s: FinancialStatement) -> dict[str, float | None]:
    """Point-in-time ratios for one statement."""
    r: dict[str, float | None] = {}
    r["gross_margin"] = None  # gross not modelled in condensed statements
    r["ebitda_margin"] = _pct(_safe(s.ebitda, s.revenue))
    r["operating_margin"] = _pct(_safe(s.ebit, s.revenue))
    r["net_margin"] = _pct(_safe(s.net_income, s.revenue))
    r["roe"] = _pct(_safe(s.net_income, s.equity))
    r["roa"] = _pct(_safe(s.net_income, s.total_assets))
    capital_employed = None
    if s.equity is not None and s.total_debt is not None:
        capital_employed = s.equity + s.total_debt
    r["roce"] = _pct(_safe(s.ebit, capital_employed))
    r["debt_equity"] = round(_safe(s.total_debt, s.equity), 2) if _safe(s.total_debt, s.equity) is not None else None
    r["interest_coverage"] = round(_safe(s.ebit, s.interest), 2) if _safe(s.ebit, s.interest) is not None else None
    r["current_ratio"] = round(_safe(s.current_assets, s.current_liabilities), 2) if _safe(s.current_assets, s.current_liabilities) is not None else None
    quick_assets = None
    if s.current_assets is not None and s.inventory is not None:
        quick_assets = s.current_assets - s.inventory
    r["quick_ratio"] = round(_safe(quick_assets, s.current_liabilities), 2) if _safe(quick_assets, s.current_liabilities) is not None else None
    r["asset_turnover"] = round(_safe(s.revenue, s.total_assets), 2) if _safe(s.revenue, s.total_assets) is not None else None
    # working-capital days
    r["receivable_days"] = round(_safe(s.receivables, s.revenue) * 365, 0) if _safe(s.receivables, s.revenue) is not None else None
    r["inventory_days"] = round(_safe(s.inventory, s.revenue) * 365, 0) if _safe(s.inventory, s.revenue) is not None else None
    r["payable_days"] = round(_safe(s.payables, s.revenue) * 365, 0) if _safe(s.payables, s.revenue) is not None else None
    if all(r[k] is not None for k in ("receivable_days", "inventory_days", "payable_days")):
        r["cash_conversion_days"] = r["receivable_days"] + r["inventory_days"] - r["payable_days"]
    else:
        r["cash_conversion_days"] = None
    # cash backing of profit (accruals)
    r["cfo_to_pat"] = round(_safe(s.cfo, s.net_income), 2) if _safe(s.cfo, s.net_income) is not None else None
    r["fcf"] = s.fcf
    return r


def dupont(s: FinancialStatement) -> dict[str, float | None]:
    """ROE = net margin × asset turnover × equity multiplier."""
    nm = _safe(s.net_income, s.revenue)
    at = _safe(s.revenue, s.total_assets)
    em = _safe(s.total_assets, s.equity)
    roe = None if None in (nm, at, em) else nm * at * em
    return {
        "net_margin": _pct(nm), "asset_turnover": round(at, 2) if at else None,
        "equity_multiplier": round(em, 2) if em else None, "roe": _pct(roe),
    }


def cagr(series: list[float], years: int) -> float | None:
    series = [x for x in series if x is not None and x > 0]
    if len(series) < 2 or years <= 0:
        return None
    return round(((series[-1] / series[0]) ** (1 / years) - 1) * 100, 1)


def analyse(data: CompanyData) -> LensResult:
    res = LensResult(lens="Fundamental")
    f = data.fundamentals
    if not f or not f.statements:
        res.summary = "No fundamental statements available."
        return res

    stmts = f.ordered()
    latest = stmts[-1]
    ratios = compute_ratios(latest)
    du = dupont(latest)
    res.data["ratios"] = ratios
    res.data["dupont"] = du
    res.data["periods"] = [s.period for s in stmts]

    # growth
    n = len(stmts) - 1
    rev_cagr = cagr([s.revenue for s in stmts], n)
    pat_cagr = cagr([s.net_income for s in stmts], n)
    ebitda_cagr = cagr([s.ebitda for s in stmts], n)
    res.data["growth"] = {"revenue_cagr": rev_cagr, "pat_cagr": pat_cagr, "ebitda_cagr": ebitda_cagr}
    res.data["series"] = {
        "revenue": [s.revenue for s in stmts],
        "net_income": [s.net_income for s in stmts],
        "ebitda_margin": [_pct(_safe(s.ebitda, s.revenue)) for s in stmts],
        "roe": [_pct(_safe(s.net_income, s.equity)) for s in stmts],
        "debt_equity": [round(_safe(s.total_debt, s.equity), 2) if _safe(s.total_debt, s.equity) else None for s in stmts],
    }

    signals: list[Signal] = []
    sub: list[float] = []   # 0..1 sub-scores

    def rate(name, value, good, bad, higher_better=True, unit=""):
        if value is None:
            return
        if higher_better:
            score = np.clip((value - bad) / (good - bad), 0, 1)
            stance = "bullish" if value >= good else "bearish" if value <= bad else "neutral"
        else:
            score = np.clip((bad - value) / (bad - good), 0, 1)
            stance = "bullish" if value <= good else "bearish" if value >= bad else "neutral"
        sub.append(float(score))
        signals.append(Signal(name, f"{value}{unit}", _interp(name, value, stance), stance, 0.6))

    rate("ROE", ratios["roe"], good=18, bad=8, unit="%")
    rate("ROCE", ratios["roce"], good=20, bad=10, unit="%")
    rate("Net margin", ratios["net_margin"], good=15, bad=3, unit="%")
    rate("EBITDA margin", ratios["ebitda_margin"], good=20, bad=8, unit="%")
    rate("Debt/Equity", ratios["debt_equity"], good=0.3, bad=1.5, higher_better=False)
    rate("Interest coverage", ratios["interest_coverage"], good=6, bad=2, unit="x")
    rate("Current ratio", ratios["current_ratio"], good=1.8, bad=1.0)
    rate("Revenue CAGR", rev_cagr, good=15, bad=3, unit="%")
    rate("PAT CAGR", pat_cagr, good=18, bad=3, unit="%")
    rate("CFO/PAT", ratios["cfo_to_pat"], good=1.0, bad=0.4)

    # DuPont narrative signal
    if du["roe"] is not None:
        driver = "operating quality"
        if du["equity_multiplier"] and du["equity_multiplier"] > 2.5:
            driver = "balance-sheet leverage (watch this)"
        elif du["asset_turnover"] and du["asset_turnover"] > 1.2:
            driver = "asset efficiency"
        signals.append(Signal(
            "DuPont ROE", f"{du['roe']}%",
            f"ROE = {du['net_margin']}% margin × {du['asset_turnover']} turnover × {du['equity_multiplier']} leverage → driven by {driver}",
            "neutral", 0.5))

    res.signals = signals
    res.score = round(float(np.mean(sub) * 100), 1) if sub else None

    tone = "strong" if (res.score or 0) >= 65 else "weak" if (res.score or 0) <= 40 else "average"
    res.summary = (
        f"Business quality looks {tone} (score {res.score}/100). "
        f"ROE {ratios['roe']}%, ROCE {ratios['roce']}%, net margin {ratios['net_margin']}%, "
        f"D/E {ratios['debt_equity']}. Revenue CAGR {rev_cagr}%, PAT CAGR {pat_cagr}% over {n}y. "
        f"Profit is {'well' if (ratios['cfo_to_pat'] or 0) >= 0.8 else 'poorly'} backed by "
        f"operating cash (CFO/PAT {ratios['cfo_to_pat']})."
    )
    return res


def _interp(name: str, value, stance: str) -> str:
    good = stance == "bullish"
    table = {
        "ROE": "Strong return on equity" if good else "Weak return on equity",
        "ROCE": "Efficient use of capital" if good else "Poor capital efficiency",
        "Net margin": "Healthy profitability" if good else "Thin margins",
        "EBITDA margin": "Healthy operating margin" if good else "Weak operating margin",
        "Debt/Equity": "Conservatively financed" if good else "Leveraged balance sheet",
        "Interest coverage": "Comfortably services debt" if good else "Debt-servicing stress",
        "Current ratio": "Sound liquidity" if good else "Tight liquidity",
        "Revenue CAGR": "Growing top line" if good else "Stagnant/declining revenue",
        "PAT CAGR": "Compounding profits" if good else "Flat/declining profits",
        "CFO/PAT": "Profit backed by real cash" if good else "Profit not converting to cash (accrual risk)",
    }
    return table.get(name, name)
