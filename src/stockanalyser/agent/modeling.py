"""The driver-based forecast model — the engine under an L3 deep dive.

Rather than guess a single growth rate, this builds a forecast the way an analyst
does: revenue compounds off a driver (growth fading toward a terminal rate), margins
map revenue to EBIT, tax gives NOPAT, and reinvestment (D&A, capex, working-capital)
turns that into **unlevered free cash flow (FCFF)** — the cash the whole firm throws
off, which the valuation engine then discounts.

Assumptions are *derived from the company's own history* (CAGR, realised margins,
capex and working-capital intensity), then flexed into bull / base / bear scenarios.
Everything is exposed on the dataclasses so the deep-dive note can show the working.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..models import Fundamentals

# clamps that keep a derived forecast sane even on noisy history
_G0_MIN, _G0_MAX = -0.05, 0.30
_MARGIN_MIN, _MARGIN_MAX = 0.02, 0.60
_TAX_MIN, _TAX_MAX = 0.10, 0.35


@dataclass
class Assumptions:
    """The knobs of one forecast case."""
    label: str
    horizon: int
    g0: float               # year-1 revenue growth
    g_terminal: float       # growth the forecast fades to (and TV grows at)
    ebitda_margin: float
    tax_rate: float
    dep_pct_rev: float
    capex_pct_rev: float
    nwc_pct_rev: float      # net working capital as a % of revenue


@dataclass
class ProjYear:
    year: int
    revenue: float
    ebitda: float
    dep: float
    ebit: float
    nopat: float
    capex: float
    delta_nwc: float
    fcff: float


@dataclass
class Projection:
    assumptions: Assumptions
    base_revenue: float
    years: list[ProjYear]

    @property
    def terminal_fcff(self) -> float:
        return self.years[-1].fcff


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def derive_assumptions(
    f: Fundamentals, *, horizon: int = 8, terminal_growth: float = 0.04,
) -> Assumptions | None:
    """Read a base-case forecast straight out of the reported history."""
    stmts = f.ordered()
    if len(stmts) < 2:
        return None
    latest = stmts[-1]
    if not latest.revenue or latest.revenue <= 0:
        return None

    # revenue growth: historical CAGR of revenue
    first = stmts[0]
    n = len(stmts) - 1
    if first.revenue and first.revenue > 0:
        g0 = (latest.revenue / first.revenue) ** (1 / n) - 1
    else:
        g0 = 0.10
    g0 = _clip(g0, _G0_MIN, _G0_MAX)

    # margins & rates from the most recent year, lightly smoothed with the prior
    recent = stmts[-2:]
    ebitda_margin = _avg([s.ebitda / s.revenue for s in recent
                          if s.ebitda is not None and s.revenue]) or 0.15
    ebitda_margin = _clip(ebitda_margin, _MARGIN_MIN, _MARGIN_MAX)

    tax_rate = 0.25
    if latest.pbt and latest.pbt > 0 and latest.tax is not None:
        tax_rate = _clip(latest.tax / latest.pbt, _TAX_MIN, _TAX_MAX)

    dep_pct = _avg([abs(s.depreciation) / s.revenue for s in recent
                    if s.depreciation is not None and s.revenue]) or 0.03
    capex_pct = _avg([abs(s.capex) / s.revenue for s in stmts[-3:]
                      if s.capex is not None and s.revenue]) or 0.04

    nwc = _net_working_capital(latest)
    nwc_pct = _clip(nwc / latest.revenue, -0.30, 0.60) if nwc is not None else 0.10

    return Assumptions(
        label="base", horizon=horizon,
        g0=round(g0, 4), g_terminal=terminal_growth,
        ebitda_margin=round(ebitda_margin, 4), tax_rate=round(tax_rate, 4),
        dep_pct_rev=round(dep_pct, 4), capex_pct_rev=round(capex_pct, 4),
        nwc_pct_rev=round(nwc_pct, 4),
    )


def _net_working_capital(s) -> float | None:
    parts = [s.receivables, s.inventory, s.payables]
    if any(p is None for p in parts):
        return None
    return (s.receivables or 0) + (s.inventory or 0) - (s.payables or 0)


def _avg(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def scenario(base: Assumptions, name: str) -> Assumptions:
    """Flex the base case into bull / bear. Growth and margin are the swing factors —
    the two things a thesis actually argues about."""
    if name == "base":
        return base
    if name == "bull":
        return replace(
            base, label="bull",
            g0=_clip(base.g0 + 0.03, _G0_MIN, 0.35),
            g_terminal=base.g_terminal + 0.005,
            ebitda_margin=_clip(base.ebitda_margin + 0.02, _MARGIN_MIN, _MARGIN_MAX))
    if name == "bear":
        return replace(
            base, label="bear",
            g0=_clip(base.g0 - 0.04, -0.10, _G0_MAX),
            ebitda_margin=_clip(base.ebitda_margin - 0.02, _MARGIN_MIN, _MARGIN_MAX))
    raise ValueError(f"Unknown scenario: {name}")


def build_projection(base_revenue: float, a: Assumptions) -> Projection:
    """Roll the assumptions forward into per-year unlevered FCF.

    Two fades run in lock-step with the growth fade, and they matter:
    * growth eases from g0 toward the terminal rate;
    * **capex intensity eases from the historical (growth-phase) level toward the
      depreciation level** — because a company in steady state reinvests to
      *maintain*, not to keep expanding at growth-phase intensity forever. Holding
      growth capex into the terminal year is the classic error that makes a DCF
      understate a heavy-reinvestment compounder by an order of magnitude.
    """
    years: list[ProjYear] = []
    prev_rev = base_revenue
    # terminal maintenance capex ≈ depreciation (net investment supports only g_term)
    terminal_capex_pct = max(a.dep_pct_rev, a.dep_pct_rev * (1 + a.g_terminal))
    for y in range(1, a.horizon + 1):
        frac = (y - 1) / max(a.horizon - 1, 1)
        g = a.g0 + (a.g_terminal - a.g0) * frac
        capex_pct = a.capex_pct_rev + (terminal_capex_pct - a.capex_pct_rev) * frac
        revenue = prev_rev * (1 + g)
        ebitda = revenue * a.ebitda_margin
        dep = revenue * a.dep_pct_rev
        ebit = ebitda - dep
        nopat = ebit * (1 - a.tax_rate)
        capex = revenue * capex_pct
        delta_nwc = (revenue - prev_rev) * a.nwc_pct_rev
        fcff = nopat + dep - capex - delta_nwc
        years.append(ProjYear(
            year=y, revenue=round(revenue, 2), ebitda=round(ebitda, 2),
            dep=round(dep, 2), ebit=round(ebit, 2), nopat=round(nopat, 2),
            capex=round(capex, 2), delta_nwc=round(delta_nwc, 2), fcff=round(fcff, 2)))
        prev_rev = revenue
    return Projection(assumptions=a, base_revenue=base_revenue, years=years)
