"""Conviction management across a coverage universe.

A covering analyst does not just hold single names — they run a book and keep a
ranked best-ideas list. This runs the agent across several names and ranks them by
a **conviction score** that blends business quality (the composite) with the
valuation edge (upside to the triangulated target), hard-gated by forensics: a
red-flagged name cannot sit at the top of a conviction list however cheap it looks.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from .core import research
from .mandate import Depth, Side


@dataclass
class UniverseRow:
    query: str
    name: str
    ticker: str
    verdict: str
    rating: str
    composite: float | None
    target_upside: float | None
    gate: str
    conviction: float
    error: str = ""


def _conviction_score(composite: float | None, upside: float | None, gate: str) -> float:
    """A best-ideas rank is driven by the actual call — the return to the target —
    with business quality as a modest tilt and forensics as a hard veto. When no
    target exists (shallow depth), fall back to quality centred at zero."""
    if upside is not None:
        edge = max(-60.0, min(60.0, upside))            # return to target dominates
        quality = ((composite if composite is not None else 50.0) - 50.0) * 0.3
        score = edge + quality
    else:
        score = (composite if composite is not None else 0.0) - 50.0
    if gate == "fail":
        score -= 100.0                                  # a red flag sinks it
    return round(score, 1)


def rank_universe(
    queries: list[str],
    *,
    side: Side | str | None = None,
    market: str | None = None,
    depth: Depth | int | str = Depth.DEEP_DIVE,
    config: Config | None = None,
) -> list[UniverseRow]:
    """Research each name and return the conviction-ranked list (best first)."""
    rows: list[UniverseRow] = []
    for q in queries:
        try:
            out = research(q, side=side, depth=depth, market=market, config=config,
                           record_coverage=False)
            upside = out.appraisal.target_upside_pct if out.appraisal else None
            rows.append(UniverseRow(
                query=q, name=out.company.name, ticker=out.company.ticker,
                verdict=out.verdict.value, rating=out.call.headline,
                composite=out.composite_score, target_upside=upside, gate=out.call.gate,
                conviction=_conviction_score(out.composite_score, upside, out.call.gate)))
        except Exception as exc:
            rows.append(UniverseRow(
                query=q, name=q, ticker="?", verdict="error", rating="—",
                composite=None, target_upside=None, gate="n/a", conviction=-999.0,
                error=f"{type(exc).__name__}: {exc}"))
    rows.sort(key=lambda r: r.conviction, reverse=True)
    return rows


def render_conviction_list(rows: list[UniverseRow], side: Side) -> str:
    L: list[str] = []
    bar = "═" * 74
    L.append(bar)
    label = "BEST IDEAS" if side is Side.BUY_SIDE else "CONVICTION LIST"
    L.append(f" {label} — {side.label}, ranked by conviction")
    L.append(bar)
    L.append(f" {'#':>2}  {'ticker'.ljust(16)} {'conv':>5}  {'comp':>5}  "
             f"{'target↑':>8}  {'gate':>5}  rating")
    for i, r in enumerate(rows, 1):
        if r.error:
            L.append(f" {i:>2}  {r.ticker.ljust(16)}  —      —        —       —     {r.error}")
            continue
        comp = f"{r.composite:.0f}" if r.composite is not None else " n/a"
        up = f"{r.target_upside:+.0f}%" if r.target_upside is not None else "  n/a"
        L.append(f" {i:>2}  {r.ticker.ljust(16)} {r.conviction:>5.0f}  {comp:>5}  "
                 f"{up:>8}  {r.gate:>5}  {r.rating}")
    L.append(bar)
    L.append(" Conviction = return-to-target (capped ±60) + quality tilt; forensic red flags sink to bottom.")
    L.append(" target↑ n/a means the name was ranked on quality only (run at L3+ for targets).")
    L.append(" Decision-support only — not investment advice.")
    return "\n".join(L)
