"""stockanalyser — a multi-lens equity analysis engine.

Turn a company name into a framework + dashboard:

    from stockanalyser import analyse
    report = analyse("Hitachi Energy")

See docs/FRAMEWORK.md for the analytical model.
"""
from __future__ import annotations

from .config import Config
from .models import Report

__all__ = ["analyse", "Config", "Report", "__version__"]
__version__ = "0.1.0"


def analyse(query: str, config: "Config | None" = None) -> "Report":
    """Resolve a name/ticker, pull data, run all lenses, return a Report.

    Thin convenience wrapper around report.builder.build_report so the common
    case is a one-liner while power users can drive the pieces directly.
    """
    from .report.builder import build_report

    return build_report(query, config=config)
