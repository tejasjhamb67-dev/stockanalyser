"""Products — the tier-appropriate deliverable, framed by side and market.

The same lens evidence renders differently depending on the mandate:

* the **side** decides the closing call — a sell-side *rating* (Buy/Hold/Sell) or
  a buy-side *position stance* (Own/Pass/Avoid) — and the voice around it;
* the **market** decides the framing line and which governance risks lead;
* the **depth** decides how much is shown (snapshot → screen → tearsheet).

A forensic gate is enforced across both sides: a Quality lens score below 40 caps
any constructive call, encoding the blueprint's "forensics can veto a rating" rule.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import LensResult, Verdict
from .mandate import Depth, Mandate, Side

FORENSIC_FLOOR = 40.0
DISCLAIMER = ("Decision-support only — not investment advice. Offline/illustrative "
              "figures must be replaced with primary filings before acting.")


@dataclass
class Call:
    """The side-specific headline call."""
    headline: str          # rating or stance
    conviction: str
    gate: str              # "pass" | "fail" | "n/a"


_SELL_RATING = {
    Verdict.STRONG_BUY: ("Buy", "High conviction"),
    Verdict.BUY: ("Buy", "Moderate conviction"),
    Verdict.HOLD: ("Neutral / Hold", "—"),
    Verdict.AVOID: ("Sell / Underweight", "Moderate conviction"),
    Verdict.STRONG_AVOID: ("Sell", "High conviction"),
    Verdict.INSUFFICIENT: ("Not Rated", "insufficient data"),
}
_BUY_STANCE = {
    Verdict.STRONG_BUY: ("Own — high conviction", "High"),
    Verdict.BUY: ("Own", "Moderate"),
    Verdict.HOLD: ("Pass / watch", "Low"),
    Verdict.AVOID: ("Avoid", "Moderate"),
    Verdict.STRONG_AVOID: ("Avoid / short candidate", "High"),
    Verdict.INSUFFICIENT: ("Pass — insufficient data", "—"),
}


def _forensic_gate(lenses: dict[str, LensResult]) -> str:
    q = lenses.get("Quality")
    if not (q and q.has_score):
        return "n/a"
    return "fail" if q.score < FORENSIC_FLOOR else "pass"


def decide_call(side: Side, verdict: Verdict, lenses: dict[str, LensResult]) -> Call:
    gate = _forensic_gate(lenses)
    if side is Side.SELL_SIDE:
        headline, conviction = _SELL_RATING[verdict]
        if gate == "fail" and headline == "Buy":
            headline, conviction = "Suspended — forensic red flag", "gate failed (Quality<40)"
    else:
        headline, conviction = _BUY_STANCE[verdict]
        if gate == "fail" and headline.startswith("Own"):
            headline, conviction = "Avoid — forensic red flag", "gate failed (Quality<40)"
    return Call(headline=headline, conviction=conviction, gate=gate)


# ── rendering ────────────────────────────────────────────────────────────────
def _lens_table(lenses: dict[str, LensResult]) -> list[str]:
    rows = []
    for name, lens in lenses.items():
        score = f"{lens.score:>5.0f}" if lens.has_score else "  n/a"
        rows.append(f"  {score}  {name.ljust(12)} {lens.summary[:88]}")
    return rows


def _call_line(mandate: Mandate, call: Call) -> str:
    if mandate.side is Side.SELL_SIDE:
        return f"Rating: {call.headline}   ({call.conviction})"
    return f"Position stance: {call.headline}   (conviction: {call.conviction})"


def _market_framing(mandate: Mandate) -> list[str]:
    m = mandate.market
    lead = ", ".join(m.governance_focus[:3])
    out = [f"Market: {m.headline}",
           f"Benchmarks: {', '.join(m.benchmarks)}   ·   Macro anchor: {m.macro_anchor}",
           f"Local risk lens: {lead}"]
    if m.is_generic:
        out.append("(market unresolved — profile refined once the listing is known)")
    return out


def render_product(
    mandate: Mandate,
    company,
    generated_at: str,
    lenses: dict[str, LensResult],
    composite: float | None,
    verdict: Verdict,
    bull: list[str],
    bear: list[str],
    monitor: list[str],
    call: Call,
    product: str,
    plan_notes: list[str],
    warnings: list[str],
) -> str:
    comp = f"{composite:.1f}/100" if composite is not None else "n/a"
    L: list[str] = []
    bar = "═" * 62
    L.append(bar)
    L.append(f" {company.name}  ({company.ticker})")
    L.append(f" {company.sector or 'Sector n/a'}"
             + (f" · {company.industry}" if company.industry else ""))
    L.append(bar)
    L.append(f" MANDATE  {mandate.headline}")
    for line in _market_framing(mandate):
        L.append(f"          {line}")
    L.append("")
    L.append(f" Composite: {comp}    Verdict: {verdict.value}")
    L.append(f" {_call_line(mandate, call)}")
    if call.gate == "fail":
        L.append(" ⚠ Forensic gate FAILED — constructive calls are capped.")
    L.append("")

    if product in ("screen", "tearsheet"):
        L.append(" Lenses")
        L.extend(_lens_table(lenses))
        L.append("")

    if product == "screen":
        advance = verdict in (Verdict.STRONG_BUY, Verdict.BUY) and call.gate != "fail"
        L.append(f" Triage: {'ADVANCE to deeper work' if advance else 'PASS for now'}"
                 f"  —  forensic gate: {call.gate}")
        L.append("")

    if product == "tearsheet":
        if bull:
            L.append(" Bull case")
            L.extend(f"   + {b}" for b in bull[:4])
        if bear:
            L.append(" Bear case")
            L.extend(f"   - {b}" for b in bear[:4])
        if monitor:
            L.append(" Key debates / monitorables")
            L.extend(f"   • {m}" for m in monitor[:4])
        L.append("")
        L.append(_side_closing(mandate, verdict, call))
        L.append("")

    for note in plan_notes:
        L.append(f" ℹ {note}")
    for w in warnings:
        L.append(f" ⚠ {w}")
    L.append("")
    L.append(f" {DISCLAIMER}")
    return "\n".join(L)


def _side_closing(mandate: Mandate, verdict: Verdict, call: Call) -> str:
    if mandate.side is Side.SELL_SIDE:
        return (" Analyst view (sell-side): framed relative to coverage & benchmark. "
                f"Published stance — {call.headline}. A 12-month price target and the "
                "full model attach at L3+.")
    return (" PM view (buy-side): framed as an absolute capital decision. "
            f"Stance — {call.headline}. Position sizing, entry/exit levels and the "
            "risk/reward skew attach at L3+.")
