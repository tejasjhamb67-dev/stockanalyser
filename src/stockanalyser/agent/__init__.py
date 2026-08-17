"""The equity-research agent — the analyst layer over the nine-lens engine.

Phase 1: a mandate router (side × market × depth), a planner, lens-as-tool
adapters, and L0–L2 product renderers. Deeper tiers (L3 modelling, L4 initiation,
L5 living coverage) slot in behind the same mandate in later phases.

    from stockanalyser.agent import research, Side, Depth
    out = research("Hitachi Energy", side="buy-side", depth="L2")
    print(out.headline)
    print(out.product)

See docs/equity-research-agent-blueprint.html for the full design.
"""
from __future__ import annotations

from .core import ResearchOutput, research
from .mandate import Depth, Mandate, MandateRouter, Side
from .markets import MarketProfile, PROFILES, infer_profile
from .planner import ResearchPlan, plan_research
from .products import Call, decide_call

__all__ = [
    "research", "ResearchOutput",
    "Mandate", "MandateRouter", "Side", "Depth",
    "MarketProfile", "PROFILES", "infer_profile",
    "ResearchPlan", "plan_research",
    "Call", "decide_call",
]
