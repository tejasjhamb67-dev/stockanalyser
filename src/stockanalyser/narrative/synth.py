"""Turn the scored lenses into a plain-English investment narrative.

Two paths:
  - LLM path (Anthropic): if `anthropic` is installed and a key is present, the
    lens summaries + scores are handed to Claude for a tight analyst write-up.
  - Deterministic path: a template synthesiser that reads the scorecard and
    disagreements. Always available, no network.

The deterministic path is the default and the fallback, so a narrative is
guaranteed even fully offline.
"""
from __future__ import annotations

import os

from ..models import Report, Verdict


def synthesize(report: Report, use_llm: bool = True) -> str:
    if use_llm:
        llm = _try_llm(report)
        if llm:
            return llm
    return _deterministic(report)


# ── LLM path ─────────────────────────────────────────────────────────────────
def _try_llm(report: Report) -> str | None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")):
        return None
    try:
        import anthropic  # noqa
    except Exception:
        return None
    try:
        client = anthropic.Anthropic()
        prompt = _build_prompt(report)
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
    except Exception:
        return None


def _build_prompt(report: Report) -> str:
    lines = [
        "You are a buy-side equity analyst. Write a tight, non-promotional investment "
        "note (~180 words) for the company below, using ONLY the evidence given. "
        "Be explicit about the central tension between the lenses. Do not invent numbers. "
        "End with one line: 'Not investment advice.'",
        "",
        f"Company: {report.company.name} ({report.company.ticker})",
        f"Composite: {report.composite_score}/100 → {report.verdict.value}",
        "",
        "Lens scores & summaries:",
    ]
    for name, lens in report.lenses.items():
        lines.append(f"- {name}: {lens.score if lens.has_score else 'n/a'} — {lens.summary}")
    lines.append("")
    lines.append("Bull points: " + " | ".join(report.bull_thesis))
    lines.append("Bear points: " + " | ".join(report.bear_thesis))
    return "\n".join(lines)


# ── deterministic path ───────────────────────────────────────────────────────
def _deterministic(report: Report) -> str:
    c = report.company
    parts: list[str] = []
    scored = {n: l.score for n, l in report.lenses.items() if l.has_score}

    verdict_line = {
        Verdict.STRONG_BUY: "screens as a high-conviction long",
        Verdict.BUY: "screens constructively",
        Verdict.HOLD: "is a hold — balanced risk/reward",
        Verdict.AVOID: "screens poorly",
        Verdict.STRONG_AVOID: "shows classic value-trap / distress signatures",
        Verdict.INSUFFICIENT: "cannot be scored on the available data",
    }[report.verdict]

    parts.append(
        f"{c.name} ({c.ticker}) {verdict_line}, with a composite of "
        f"{report.composite_score}/100 across {len(scored)} lenses."
    )

    # the central tension: highest vs lowest lens
    if len(scored) >= 2:
        hi = max(scored.items(), key=lambda x: x[1])
        lo = min(scored.items(), key=lambda x: x[1])
        if hi[1] - lo[1] > 15:
            parts.append(
                f"The central tension is {hi[0].lower()} strength ({hi[1]}/100) against "
                f"{lo[0].lower()} weakness ({lo[1]}/100) — resolve that and you have your call."
            )

    # thread the most important lens summaries
    for key in ("Fundamental", "Valuation", "Quality", "Spike", "Qualitative", "Governance"):
        lens = report.lenses.get(key)
        if lens and lens.summary and lens.has_score:
            parts.append(lens.summary)

    if report.bull_thesis:
        parts.append("Bull case: " + "; ".join(s.split("] ", 1)[-1] for s in report.bull_thesis[:3]) + ".")
    if report.bear_thesis:
        parts.append("Bear case: " + "; ".join(s.split("] ", 1)[-1] for s in report.bear_thesis[:3]) + ".")
    if report.monitorables:
        parts.append("Watch: " + "; ".join(m.replace("Watch ", "") for m in report.monitorables[:2]) + ".")

    parts.append("This is a decision-support read, not investment advice.")
    return " ".join(parts)
