"""Valuation triangulation — turn the forecast into a price target three ways.

An L3 appraisal never rests on one number. It runs:

* a **two-stage DCF** on unlevered FCF for each of bull / base / bear, at a
  market-anchored WACC, netting debt to a per-share equity value;
* an **exit-multiple** cross-check (terminal-year EBITDA × an EV/EBITDA exit) so
  the DCF isn't marking its own homework;
* a **reverse DCF** — the growth rate the *current price* already implies — which
  is the honest way to state a variant view: our forecast growth vs the market's.

These reconcile into a scenario-weighted 12-month-style target with a fair-value
range and the up/downside versus the live price.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from ..models import Fundamentals
from .markets import MarketProfile
from .modeling import (
    Assumptions, Projection, build_projection, derive_assumptions, scenario,
)

# default scenario probabilities — base-weighted, symmetric tails
DEFAULT_PROBS = {"bear": 0.25, "base": 0.50, "bull": 0.25}
DEFAULT_EXIT_EV_EBITDA = 12.0     # neutral exit multiple for the cross-check


@dataclass
class DcfOutput:
    fair_value: float | None      # per share
    ev: float
    pv_explicit: float
    pv_terminal: float
    terminal_pct: float           # % of EV coming from terminal value


@dataclass
class ScenarioResult:
    name: str
    prob: float
    assumptions: Assumptions
    dcf: DcfOutput
    upside_pct: float | None


@dataclass
class Appraisal:
    price: float | None
    currency: str
    wacc: float
    terminal_growth: float
    net_debt: float
    shares: float | None
    scenarios: list[ScenarioResult]           # bear, base, bull (in that order)
    weighted_target: float | None
    target_upside_pct: float | None
    fair_low: float | None
    fair_high: float | None
    base_growth: float | None                 # our base-case year-1 growth
    implied_growth: float | None              # reverse-DCF: growth the price implies
    exit_multiple_value: float | None         # cross-check per-share value
    notes: list[str] = field(default_factory=list)

    @property
    def variant(self) -> str | None:
        """One-line variant-perception read: our growth vs the market's."""
        if self.base_growth is None or self.implied_growth is None:
            return None
        diff = (self.base_growth - self.implied_growth) * 100
        if diff > 2:
            return (f"Constructive variant — our base growth {self.base_growth*100:.0f}% "
                    f"tops the ~{self.implied_growth*100:.0f}% the price implies; the "
                    f"market looks too cautious.")
        if diff < -2:
            return (f"Cautious variant — the price already implies ~{self.implied_growth*100:.0f}% "
                    f"growth vs our {self.base_growth*100:.0f}%; expectations look full.")
        return (f"In line with consensus — our {self.base_growth*100:.0f}% base growth is "
                f"roughly what the ~{self.implied_growth*100:.0f}% price-implied rate assumes.")

    def scenario(self, name: str) -> ScenarioResult | None:
        return next((s for s in self.scenarios if s.name == name), None)


def _net_debt(f: Fundamentals) -> float:
    s = f.latest
    if not s:
        return 0.0
    return (s.total_debt or 0.0) - (s.cash or 0.0)


def _shares(f: Fundamentals) -> float | None:
    s = f.latest
    return f.shares_outstanding or (s.shares_outstanding if s else None)


def dcf(projection: Projection, wacc: float, net_debt: float,
        shares: float | None) -> DcfOutput:
    """Two-stage DCF on the projection's FCFF, terminal via Gordon growth."""
    a = projection.assumptions
    g_term = min(a.g_terminal, wacc - 0.01)     # guard: TV needs wacc > g
    pv_explicit = 0.0
    for py in projection.years:
        pv_explicit += py.fcff / (1 + wacc) ** py.year
    terminal_fcff = projection.terminal_fcff * (1 + g_term)
    tv = terminal_fcff / (wacc - g_term)
    pv_terminal = tv / (1 + wacc) ** a.horizon
    ev = pv_explicit + pv_terminal
    equity = ev - net_debt
    fair = equity / shares if shares else None
    return DcfOutput(
        fair_value=round(fair, 1) if fair is not None else None,
        ev=round(ev, 1), pv_explicit=round(pv_explicit, 1),
        pv_terminal=round(pv_terminal, 1),
        terminal_pct=round(pv_terminal / ev * 100, 1) if ev else 0.0)


def _implied_growth(base: Assumptions, base_revenue: float, price: float,
                    wacc: float, net_debt: float, shares: float) -> float | None:
    """Reverse-DCF: bisect for the year-1 growth that makes the base-case DCF equal
    the current price. That is the growth the market is paying for today."""
    def fair_at(g0: float) -> float | None:
        proj = build_projection(base_revenue, _with_g0(base, g0))
        return dcf(proj, wacc, net_debt, shares).fair_value

    lo, hi = -0.15, 0.60
    f_lo, f_hi = fair_at(lo), fair_at(hi)
    if f_lo is None or f_hi is None:
        return None
    # fair value is monotonically increasing in growth; require the price to be bracketed
    if not (f_lo <= price <= f_hi):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        fm = fair_at(mid)
        if fm is None:
            return None
        if fm < price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def _with_g0(a: Assumptions, g0: float) -> Assumptions:
    from dataclasses import replace
    return replace(a, g0=g0)


def _exit_multiple_value(projection: Projection, wacc: float, net_debt: float,
                         shares: float | None, ev_ebitda: float) -> float | None:
    """Terminal-year EBITDA × exit EV/EBITDA, **discounted to present** — an
    apples-to-apples cross-check on the DCF, not an undiscounted future number."""
    if not shares:
        return None
    horizon = projection.assumptions.horizon
    terminal_ev = projection.years[-1].ebitda * ev_ebitda
    pv_ev = terminal_ev / (1 + wacc) ** horizon
    equity = pv_ev - net_debt
    return round(equity / shares, 1) if equity > 0 else None


def build_appraisal(
    f: Fundamentals | None,
    market: MarketProfile,
    config: Config | None = None,
    *,
    probs: dict[str, float] | None = None,
) -> Appraisal | None:
    """Full triangulated appraisal, or None when there isn't enough to model."""
    if f is None or not f.statements:
        return None
    config = config or Config.default()
    base = derive_assumptions(
        f, horizon=max(config.valuation.dcf_years - 2, 5),
        terminal_growth=config.valuation.terminal_growth)
    if base is None:
        return None

    latest = f.latest
    base_revenue = latest.revenue
    shares = _shares(f)
    net_debt = _net_debt(f)
    price = f.price
    wacc = market.default_wacc
    probs = probs or DEFAULT_PROBS
    notes: list[str] = []

    scenarios: list[ScenarioResult] = []
    for name in ("bear", "base", "bull"):
        a = scenario(base, name)
        proj = build_projection(base_revenue, a)
        out = dcf(proj, wacc, net_debt, shares)
        upside = ((out.fair_value / price - 1) * 100
                  if out.fair_value and price else None)
        scenarios.append(ScenarioResult(
            name=name, prob=probs.get(name, 0.0), assumptions=a, dcf=out,
            upside_pct=round(upside, 1) if upside is not None else None))

    fvs = [s.dcf.fair_value for s in scenarios if s.dcf.fair_value is not None]
    # a scenario whose cash flows don't even cover net debt gives a non-positive
    # per-share value — it is not a meaningful target, so only weight positive cases
    positive = [s for s in scenarios if s.dcf.fair_value is not None and s.dcf.fair_value > 0]
    weighted = None
    if len(positive) == len(scenarios):
        weighted = round(sum(s.prob * s.dcf.fair_value for s in scenarios), 1)
    elif positive:
        notes.append("At least one scenario's DCF value is non-positive (cash flows do "
                     "not cover net debt) — leaning on the multiples cross-check.")
    target_upside = (round((weighted / price - 1) * 100, 1)
                     if weighted and price else None)

    implied = None
    if price and shares:
        implied = _implied_growth(base, base_revenue, price, wacc, net_debt, shares)
        if implied is None:
            notes.append("Reverse-DCF could not bracket the current price — the market "
                         "is pricing growth outside a plausible band (deep value or bubble).")

    base_proj = build_projection(base_revenue, base)
    exit_val = _exit_multiple_value(base_proj, wacc, net_debt, shares, DEFAULT_EXIT_EV_EBITDA)

    if scenarios[1].dcf.terminal_pct > 80:
        notes.append(f"Terminal value is {scenarios[1].dcf.terminal_pct:.0f}% of the base-case "
                     f"EV — the target leans heavily on assumptions beyond the forecast horizon.")

    return Appraisal(
        price=price, currency=market.currency,
        wacc=wacc, terminal_growth=base.g_terminal, net_debt=round(net_debt, 1),
        shares=shares, scenarios=scenarios, weighted_target=weighted,
        target_upside_pct=target_upside,
        fair_low=round(min(fvs), 1) if fvs else None,
        fair_high=round(max(fvs), 1) if fvs else None,
        base_growth=base.g0, implied_growth=implied,
        exit_multiple_value=exit_val, notes=notes)
