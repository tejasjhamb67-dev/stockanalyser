"""The analyst read — a mandate-aware prose note over the agent's evidence.

Two paths, mirroring the engine's own narrative layer:
  - LLM (Anthropic): when `anthropic` is installed and a key is present, the
    mandate, call, target and lens evidence are handed to Claude for a tight,
    side-appropriate write-up.
  - Deterministic: a template that threads the same evidence into prose. Always
    available, fully offline, and the guaranteed fallback.

Either way the numbers come only from the analysis — the model never invents them.
"""
from __future__ import annotations

import os

# match the engine's existing narrative layer (narrative/synth.py) for consistency
NARRATIVE_MODEL = "claude-sonnet-5"


def build_narrative(out, use_llm: bool = True) -> str:
    if use_llm:
        text = _llm(out)
        if text:
            return text
    return _deterministic(out)


# ── LLM path ─────────────────────────────────────────────────────────────────
def _llm(out) -> str | None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")):
        return None
    try:
        import anthropic  # noqa
    except Exception:
        return None
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=NARRATIVE_MODEL,
            max_tokens=700,
            messages=[{"role": "user", "content": _prompt(out)}],
        )
        return "".join(b.text for b in msg.content
                       if getattr(b, "type", "") == "text").strip() or None
    except Exception:
        return None


def _prompt(out) -> str:
    m = out.mandate
    side = m.side.label
    frame = ("a published rating vs coverage/benchmark" if m.side.value == "sell-side"
             else "an absolute capital decision and the risk/reward skew")
    lines = [
        f"You are a senior {side} equity analyst. Write a tight investment note "
        f"(~170 words) using ONLY the evidence below. Frame it as {frame}. Be explicit "
        f"about the central tension between the lenses, and reconcile the business "
        f"quality (composite) with the price target. Do not invent any numbers. "
        f"End with the single line: 'Not investment advice.'",
        "",
        f"Company: {out.company.name} ({out.company.ticker})",
        f"Market: {m.market.headline}",
        f"Mandate: {m.headline}",
        f"Call: {out.call.headline} ({out.call.conviction}); forensic gate {out.call.gate}",
        f"Composite: {out.composite_score}/100 -> {out.verdict.value}",
    ]
    a = out.appraisal
    if a is not None and a.weighted_target is not None:
        lines.append(f"12-mo target: {a.currency} {a.weighted_target:,.0f} "
                     f"({a.target_upside_pct:+.0f}% vs price), range "
                     f"{a.fair_low:,.0f}-{a.fair_high:,.0f}, WACC {a.wacc*100:.0f}%.")
        if a.variant:
            lines.append(f"Variant: {a.variant}")
    lines.append("")
    lines.append("Lens scores & summaries:")
    for name, lens in out.lenses.items():
        lines.append(f"- {name}: {lens.score if lens.has_score else 'n/a'} — {lens.summary}")
    if out.bull_thesis:
        lines.append("Bull: " + " | ".join(_strip(b) for b in out.bull_thesis[:3]))
    if out.bear_thesis:
        lines.append("Bear: " + " | ".join(_strip(b) for b in out.bear_thesis[:3]))
    return "\n".join(lines)


# ── deterministic path ───────────────────────────────────────────────────────
def _deterministic(out) -> str:
    m = out.mandate
    scored = {n: l.score for n, l in out.lenses.items() if l.has_score}
    parts: list[str] = []

    lead_verb = "recommends" if m.side.value == "sell-side" else "would"
    parts.append(
        f"{m.side.label} read: {out.company.name} ({out.company.ticker}) — "
        f"{out.call.headline}. On a composite of {out.composite_score}/100 across "
        f"{len(scored)} lenses, the business {('screens well' if (out.composite_score or 0) >= 60 else 'is middling' if (out.composite_score or 0) >= 45 else 'screens poorly')}.")

    # central tension
    if len(scored) >= 2:
        hi = max(scored.items(), key=lambda x: x[1])
        lo = min(scored.items(), key=lambda x: x[1])
        if hi[1] - lo[1] > 15:
            parts.append(
                f"The crux is {hi[0].lower()} strength ({hi[1]:.0f}) against "
                f"{lo[0].lower()} weakness ({lo[1]:.0f}).")

    # valuation reconciliation
    a = out.appraisal
    if a is not None and a.weighted_target is not None:
        parts.append(
            f"Triangulated fair value is {a.currency} {a.weighted_target:,.0f} "
            f"({a.target_upside_pct:+.0f}% vs price) — so the {out.verdict.value.lower()} "
            f"quality read is {'confirmed' if (a.target_upside_pct or 0) >= 0 else 'capped'} "
            f"by valuation.")
        if a.variant:
            parts.append(a.variant)
    if out.call.gate == "fail":
        parts.append("A forensic red flag caps any constructive call regardless of the rest.")

    if out.bull_thesis:
        parts.append("Bull: " + "; ".join(_strip(b) for b in out.bull_thesis[:2]) + ".")
    if out.bear_thesis:
        parts.append("Bear: " + "; ".join(_strip(b) for b in out.bear_thesis[:2]) + ".")
    if out.monitorables:
        parts.append("Watch: " + _strip(out.monitorables[0]).replace("Watch ", "") + ".")

    parts.append("Not investment advice.")
    return " ".join(parts)


def _strip(s: str) -> str:
    return s.split("] ", 1)[-1] if "] " in s else s
