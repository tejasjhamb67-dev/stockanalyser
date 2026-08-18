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

from .appraisal import Appraisal, build_appraisal
from .catalysts import Catalyst, build_catalysts
from .consensus import ConsensusView, build_consensus
from .core import ResearchOutput, research
from .coverage import (
    EarningsPreview, EarningsReview, RevisionLine, ThesisTracker,
    earnings_preview, earnings_review, estimate_revisions, thesis_tracker,
)
from .mandate import Depth, Mandate, MandateRouter, Side
from .markets import MarketProfile, PROFILES, infer_profile
from .memory import CoverageEntry, CoverageMemory, coverage_note
from .modeling import Assumptions, Projection, build_projection, derive_assumptions
from .narrative import build_narrative
from .planner import ResearchPlan, plan_research
from .products import Call, decide_call
from .render_html import render_html
from .serialize import research_to_dict
from .universe import UniverseRow, rank_universe, render_conviction_list

__all__ = [
    "research", "ResearchOutput",
    "Mandate", "MandateRouter", "Side", "Depth",
    "MarketProfile", "PROFILES", "infer_profile",
    "ResearchPlan", "plan_research",
    "Call", "decide_call",
    "Appraisal", "build_appraisal",
    "Assumptions", "Projection", "build_projection", "derive_assumptions",
    "ConsensusView", "build_consensus",
    "Catalyst", "build_catalysts",
    "CoverageEntry", "CoverageMemory", "coverage_note",
    "EarningsReview", "EarningsPreview", "RevisionLine", "ThesisTracker",
    "earnings_review", "earnings_preview", "estimate_revisions", "thesis_tracker",
    "UniverseRow", "rank_universe", "render_conviction_list",
    "render_html", "build_narrative", "research_to_dict",
]
