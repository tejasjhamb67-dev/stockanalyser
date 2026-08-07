"""Qualitative lens: earnings-call & filings NLP.

Deterministic by default (keyword sentiment, theme extraction, red-flag phrase
detection, guidance detection, and theme-drift across quarters). If an Anthropic
key is present and use_llm is on, the narrative module layers richer reasoning on
top — but this lens always returns a defensible, offline result on its own.
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np

from ..models import CompanyData, LensResult, Signal

POSITIVE = {
    "record", "strong", "robust", "growth", "expansion", "beat", "outperform",
    "momentum", "healthy", "improved", "improving", "confident", "optimistic",
    "resilient", "leadership", "tailwind", "demand", "margin expansion", "highest",
    "pleased", "double-digit", "accelerat",
}
NEGATIVE = {
    "challenging", "headwind", "weak", "decline", "pressure", "slowdown", "delay",
    "delayed", "stretched", "cautious", "uncertain", "shortfall", "miss", "impair",
    "loss", "litigation", "refinanc", "stress", "temporary", "difficult",
}
REDFLAGS = {
    "working capital continues to be stretched": "Working-capital stress",
    "delayed client payments": "Receivables/collection problem",
    "refinance": "Refinancing / debt-rollover risk",
    "in discussions with lenders": "Lender negotiations — distress signal",
    "challenging environment": "Management hedging on the environment",
    "aggressive growth guidance": "Aggressive guidance without a clear mechanism",
    "contingent": "Contingent-liability mention",
    "qualified opinion": "Auditor qualification",
}
GUIDANCE_CUES = ["expect", "guidance", "outlook", "we anticipate", "we see", "target",
                 "coming year", "medium term", "going forward"]

THEME_LEXICON = {
    "order book / pipeline": ["order", "backlog", "pipeline", "book"],
    "margins": ["margin", "profitability", "cost", "pricing"],
    "demand / volumes": ["demand", "volume", "footfall", "arpu"],
    "capex / capacity": ["capex", "capacity", "expansion", "localis", "invest"],
    "energy transition / green": ["energy transition", "renewable", "grid", "green", "hvdc"],
    "balance sheet / debt": ["debt", "leverage", "refinanc", "working capital", "collections"],
    "competition": ["competition", "competitive", "market share"],
}


def _sentiment(text: str) -> float:
    t = text.lower()
    pos = sum(t.count(w) for w in POSITIVE)
    neg = sum(t.count(w) for w in NEGATIVE)
    if pos + neg == 0:
        return 0.0
    return round((pos - neg) / (pos + neg), 2)


def _themes(text: str) -> list[tuple[str, int]]:
    t = text.lower()
    counts = Counter()
    for theme, kws in THEME_LEXICON.items():
        counts[theme] = sum(t.count(k) for k in kws)
    return [(k, v) for k, v in counts.most_common() if v > 0]


def _guidance(text: str) -> list[str]:
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        low = sent.lower()
        if any(cue in low for cue in GUIDANCE_CUES) and len(sent) < 300:
            out.append(sent.strip())
    return out[:4]


def _redflags(text: str) -> list[str]:
    t = text.lower()
    return [label for phrase, label in REDFLAGS.items() if phrase in t]


def analyse(data: CompanyData) -> LensResult:
    res = LensResult(lens="Qualitative")
    calls = [c for c in data.earnings_calls if c.transcript]
    if not calls:
        res.summary = "No earnings-call transcripts available."
        return res

    signals: list[Signal] = []
    latest = calls[-1]
    sent = _sentiment(latest.transcript)
    themes = _themes(latest.transcript)
    guidance = _guidance(latest.transcript)
    flags = _redflags(latest.transcript)

    res.data["latest_period"] = latest.period
    res.data["sentiment"] = sent
    res.data["themes"] = themes
    res.data["guidance"] = guidance
    res.data["red_flags"] = flags

    stance = "bullish" if sent > 0.2 else "bearish" if sent < -0.2 else "neutral"
    signals.append(Signal("Management tone", sent,
                          "Upbeat commentary" if sent > 0.2 else "Cautious/negative commentary" if sent < -0.2 else "Balanced tone",
                          stance, 0.6))

    if themes:
        top = ", ".join(f"{k}" for k, _ in themes[:3])
        signals.append(Signal("Key themes", top, f"Management is focused on: {top}", "neutral", 0.4))

    for g in guidance[:2]:
        signals.append(Signal("Guidance", "", g, "neutral", 0.4))

    for fl in flags:
        signals.append(Signal("⚠ Red-flag language", fl, f"Concall phrasing flags: {fl}", "warning", 0.6))

    # theme drift across quarters (needs >=2 calls)
    drift_note = ""
    if len(calls) >= 2:
        prev_themes = dict(_themes(calls[-2].transcript))
        cur_themes = dict(themes)
        dropped = [t for t in prev_themes if prev_themes.get(t, 0) > 0 and cur_themes.get(t, 0) == 0]
        emerged = [t for t in cur_themes if cur_themes.get(t, 0) > 0 and prev_themes.get(t, 0) == 0]
        if dropped or emerged:
            drift_note = (("New emphasis on " + ", ".join(emerged) + ". " if emerged else "")
                          + ("Stopped talking about " + ", ".join(dropped) + " (why?)." if dropped else ""))
            signals.append(Signal("Theme drift", "", drift_note, "warning" if dropped else "neutral", 0.4))
    res.data["theme_drift"] = drift_note

    # score: sentiment mapped to 0-100, penalised by red flags
    base = (sent + 1) / 2 * 100
    penalty = min(40, len(flags) * 15)
    res.score = round(float(np.clip(base - penalty, 5, 95)), 1)

    res.summary = (
        f"{latest.period} concall tone {'positive' if sent>0.2 else 'negative' if sent<-0.2 else 'neutral'} "
        f"(sentiment {sent}). Top themes: {', '.join(k for k,_ in themes[:3]) if themes else 'n/a'}. "
        + (f"⚠ {len(flags)} red-flag phrase(s): {', '.join(flags)}. " if flags else "")
        + (drift_note or "")
    )
    return res
