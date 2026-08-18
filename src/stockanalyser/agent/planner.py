"""The planner — turns a mandate into a concrete run plan.

Given the depth tier it decides which lens-tools to run and which product to
render. Shallow tiers run a cheap subset; L2 and above run all nine lenses. Depth
tiers above what this build implements (L3+) degrade gracefully to the L2
tearsheet with an explicit note — honest about the ceiling, never a crash.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .mandate import Depth, Mandate
from .tools import ALL_LENSES

# lens-tool selection per depth (each tier is a superset of the one below)
_SNAPSHOT_LENSES = ["Technical", "Spike", "Valuation"]
_SCREEN_LENSES = _SNAPSHOT_LENSES + ["Fundamental", "Quality"]

# the deepest tier this build renders as a first-class product
MAX_IMPLEMENTED = Depth.COVERAGE

_PRODUCT_BY_DEPTH = {
    Depth.BRIEF: "tearsheet",
    Depth.DEEP_DIVE: "deepdive",
    Depth.INITIATION: "initiation",
    Depth.COVERAGE: "coverage",
}


@dataclass
class ResearchPlan:
    mandate: Mandate
    lenses: list[str]
    product: str        # snapshot | screen | tearsheet | deepdive | initiation | coverage
    notes: list[str] = field(default_factory=list)


def plan_research(mandate: Mandate) -> ResearchPlan:
    depth = mandate.depth
    notes: list[str] = []

    if depth <= Depth.SNAPSHOT:
        return ResearchPlan(mandate, list(_SNAPSHOT_LENSES), "snapshot", notes)
    if depth == Depth.SCREEN:
        return ResearchPlan(mandate, list(_SCREEN_LENSES), "screen", notes)

    # L2 and deeper all run the full lens set; the product escalates with depth
    product = _PRODUCT_BY_DEPTH[depth]
    return ResearchPlan(mandate, list(ALL_LENSES), product, notes)
