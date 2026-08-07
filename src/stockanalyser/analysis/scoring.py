"""Synthesis: combine lens sub-scores into a composite, a verdict, and an
auto-drafted bull thesis / bear thesis / monitorables.

The composite re-normalises weights over only the lenses that actually produced a
score, so a missing lens never silently drags the number to zero — and the
component scores are always carried through so disagreements stay visible.
"""
from __future__ import annotations

from ..config import ScoreWeights
from ..models import LensResult, Verdict


def composite(lenses: dict[str, LensResult], weights: ScoreWeights) -> float | None:
    w = weights.as_dict()
    num = 0.0
    den = 0.0
    for name, lens in lenses.items():
        if lens.has_score and name in w:
            num += w[name] * lens.score
            den += w[name]
    if den == 0:
        return None
    return round(num / den, 1)


def verdict_from(score: float | None) -> Verdict:
    if score is None:
        return Verdict.INSUFFICIENT
    if score >= 75:
        return Verdict.STRONG_BUY
    if score >= 60:
        return Verdict.BUY
    if score >= 45:
        return Verdict.HOLD
    if score >= 30:
        return Verdict.AVOID
    return Verdict.STRONG_AVOID


def _collect(lenses, stance):
    out = []
    for lens in lenses.values():
        for sig in lens.signals:
            if sig.stance == stance:
                out.append((lens.lens, sig))
    return out


def bull_bear_monitorables(lenses: dict[str, LensResult]) -> tuple[list[str], list[str], list[str]]:
    bull, bear, monitor = [], [], []

    # bull: strongest bullish signals across lenses, ranked by confidence
    bulls = sorted(_collect(lenses, "bullish"), key=lambda x: x[1].confidence, reverse=True)
    for lens_name, sig in bulls[:5]:
        bull.append(f"[{lens_name}] {sig.name}: {sig.interpretation}")

    # bear: bearish + warnings
    bears = sorted(_collect(lenses, "bearish") + _collect(lenses, "warning"),
                   key=lambda x: x[1].confidence, reverse=True)
    for lens_name, sig in bears[:5]:
        bear.append(f"[{lens_name}] {sig.name}: {sig.interpretation}")

    # monitorables: warnings + the lens with the widest disagreement from the pack
    warns = _collect(lenses, "warning")
    for lens_name, sig in warns[:3]:
        monitor.append(f"Watch [{lens_name}] {sig.name} — {sig.interpretation}")

    scored = [(n, l.score) for n, l in lenses.items() if l.has_score]
    if scored:
        avg = sum(s for _, s in scored) / len(scored)
        outlier = max(scored, key=lambda x: abs(x[1] - avg))
        if abs(outlier[1] - avg) > 20:
            direction = "far stronger" if outlier[1] > avg else "far weaker"
            monitor.append(
                f"{outlier[0]} ({outlier[1]}/100) is {direction} than the other lenses "
                f"(avg {avg:.0f}) — the crux of the thesis.")
    return bull, bear, monitor
