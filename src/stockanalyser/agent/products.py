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


def decide_call(side: Side, verdict: Verdict, lenses: dict[str, LensResult],
                appraisal=None) -> Call:
    gate = _forensic_gate(lenses)
    if side is Side.SELL_SIDE:
        headline, conviction = _SELL_RATING[verdict]
        if gate == "fail" and headline == "Buy":
            headline, conviction = "Suspended — forensic red flag", "gate failed (Quality<40)"
    else:
        headline, conviction = _BUY_STANCE[verdict]
        if gate == "fail" and headline.startswith("Own"):
            headline, conviction = "Avoid — forensic red flag", "gate failed (Quality<40)"

    # valuation overlay (L3+): the rating must be consistent with the price target.
    # A name trading far above triangulated fair value can't be Buy/Own however good
    # the business; one trading far below it earns a constructive call.
    if appraisal is not None and appraisal.target_upside_pct is not None and gate != "fail":
        headline, conviction = _valuation_overlay(
            side, headline, conviction, appraisal.target_upside_pct)
    return Call(headline=headline, conviction=conviction, gate=gate)


def _valuation_overlay(side: Side, headline: str, conviction: str, upside: float):
    constructive = (headline == "Buy") or headline.startswith("Own")
    neutral = headline in ("Neutral / Hold", "Pass / watch")
    if upside <= -20 and constructive:
        # trading well above fair value — cap the call
        if side is Side.SELL_SIDE:
            headline = "Sell / Underweight" if upside <= -40 else "Neutral / Hold"
        else:
            headline = "Avoid" if upside <= -40 else "Pass / watch"
        conviction = f"valuation caps it — {upside:+.0f}% to fair value"
    elif upside >= 25 and neutral:
        # trading well below fair value — a strong business at a cheap price earns a bid
        headline = "Buy" if side is Side.SELL_SIDE else "Own"
        conviction = f"valuation-led — {upside:+.0f}% to fair value"
    return headline, conviction


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
    appraisal=None,
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
    L.append(f"          As of {generated_at}")
    L.append("")
    L.append(f" Composite: {comp}    Verdict: {verdict.value}")
    L.append(f" {_call_line(mandate, call)}")
    if call.gate == "fail":
        L.append(" ⚠ Forensic gate FAILED — constructive calls are capped.")
    L.append("")

    if product in ("screen", "tearsheet", "deepdive"):
        L.append(" Lenses")
        L.extend(_lens_table(lenses))
        L.append("")

    if product == "screen":
        advance = verdict in (Verdict.STRONG_BUY, Verdict.BUY) and call.gate != "fail"
        L.append(f" Triage: {'ADVANCE to deeper work' if advance else 'PASS for now'}"
                 f"  —  forensic gate: {call.gate}")
        L.append("")

    if product == "deepdive":
        L.extend(_valuation_block(appraisal))

    if product in ("tearsheet", "deepdive"):
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
        L.append(_side_closing(mandate, verdict, call, appraisal))
        L.append("")

    for note in plan_notes:
        L.append(f" ℹ {note}")
    for w in warnings:
        L.append(f" ⚠ {w}")
    L.append("")
    L.append(f" {DISCLAIMER}")
    return "\n".join(L)


def _valuation_block(appraisal) -> list[str]:
    """The L3 model + triangulated valuation section."""
    if appraisal is None:
        return [" Valuation", "   Model not computable — insufficient statement history.", ""]
    a = appraisal
    ccy = a.currency
    L = [" Valuation — driver model + triangulation",
         f"   WACC {a.wacc*100:.1f}%  ·  terminal growth {a.terminal_growth*100:.1f}%  "
         f"·  net debt {a.net_debt:,.0f} {ccy}  ·  price {a.price:,.0f} {ccy}"]
    L.append("   ┌ scenario   growth   EBITDA-margin   DCF value   up/down")
    for s in a.scenarios:
        val = s.dcf.fair_value
        if val is None or val <= 0:
            fv, up = "uncov.", "  n/a"      # cash flows don't cover net debt
        else:
            fv = f"{val:,.0f}"
            up = f"{s.upside_pct:+.0f}%" if s.upside_pct is not None else "  n/a"
        L.append(f"   │ {s.name.ljust(8)} p={s.prob:.2f}  "
                 f"{s.assumptions.g0*100:>4.0f}%   {s.assumptions.ebitda_margin*100:>5.0f}%"
                 f"        {fv:>8}   {up:>6}")
    if a.weighted_target is not None:
        L.append(f"   └ scenario-weighted target: {a.weighted_target:,.0f} {ccy}  "
                 f"({a.target_upside_pct:+.0f}% vs price)   range {a.fair_low:,.0f}–{a.fair_high:,.0f}")
    if a.exit_multiple_value is not None:
        L.append(f"   Exit-multiple cross-check (12x EV/EBITDA terminal): "
                 f"~{a.exit_multiple_value:,.0f} {ccy}/sh")
    if a.scenarios and a.scenarios[1].dcf.terminal_pct:
        L.append(f"   Terminal value = {a.scenarios[1].dcf.terminal_pct:.0f}% of base-case EV")
    if a.variant:
        L.append(f"   Variant perception: {a.variant}")
    for n in a.notes:
        L.append(f"   ℹ {n}")
    L.append("")
    return L


def _side_closing(mandate: Mandate, verdict: Verdict, call: Call, appraisal=None) -> str:
    tgt = ""
    if appraisal is not None and appraisal.weighted_target is not None:
        tgt = (f" Target {appraisal.weighted_target:,.0f} {appraisal.currency} "
               f"({appraisal.target_upside_pct:+.0f}%).")
    if mandate.side is Side.SELL_SIDE:
        return (" Analyst view (sell-side): framed relative to coverage & benchmark. "
                f"Published stance — {call.headline}.{tgt}"
                + ("" if tgt else " A 12-month price target and full model attach at L3+."))
    # buy-side: express the risk/reward skew from the scenario tree
    skew = ""
    if appraisal is not None:
        bull = appraisal.scenario("bull")
        bear = appraisal.scenario("bear")
        if bull and bear and bull.upside_pct is not None and bear.upside_pct is not None:
            skew = (f" Risk/reward: {bull.upside_pct:+.0f}% (bull) vs {bear.upside_pct:+.0f}% "
                    f"(bear) — skew {_skew_word(bull.upside_pct, bear.upside_pct)}.")
    return (" PM view (buy-side): framed as an absolute capital decision. "
            f"Stance — {call.headline}.{tgt}{skew}"
            + ("" if appraisal else " Sizing and entry/exit attach at L3+."))


def _skew_word(up: float, down: float) -> str:
    if down >= 0:
        return "favourable (both cases positive)"
    ratio = up / abs(down) if down else float("inf")
    if ratio >= 2:
        return f"favourable (~{ratio:.1f}:1)"
    if ratio >= 1:
        return f"balanced (~{ratio:.1f}:1)"
    return f"unfavourable (~{ratio:.1f}:1)"
