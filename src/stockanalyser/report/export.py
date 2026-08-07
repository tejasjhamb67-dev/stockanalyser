"""Serialise a Report to a plain dict / JSON (for APIs, storage, diffing)."""
from __future__ import annotations

import json
from dataclasses import asdict

from ..models import Report


def report_to_dict(report: Report) -> dict:
    return {
        "company": asdict(report.company),
        "generated_at": report.generated_at,
        "data_sources": report.data_sources,
        "composite_score": report.composite_score,
        "verdict": report.verdict.value,
        "bull_thesis": report.bull_thesis,
        "bear_thesis": report.bear_thesis,
        "monitorables": report.monitorables,
        "narrative": report.narrative,
        "warnings": report.warnings,
        "lenses": {
            name: {
                "score": lens.score,
                "summary": lens.summary,
                "signals": [
                    {"name": s.name, "value": s.value, "interpretation": s.interpretation,
                     "stance": s.stance, "confidence": s.confidence}
                    for s in lens.signals
                ],
                "data": lens.data,
            }
            for name, lens in report.lenses.items()
        },
    }


def report_to_json(report: Report, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent, default=str)
