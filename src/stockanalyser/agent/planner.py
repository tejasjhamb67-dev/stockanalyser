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
MAX_IMPLEMENTED = Depth.BRIEF


@dataclass
class ResearchPlan:
    mandate: Mandate
    lenses: list[str]
    product: str                 # "snapshot" | "screen" | "tearsheet"
    notes: list[str] = field(default_factory=list)


def plan_research(mandate: Mandate) -> ResearchPlan:
    depth = mandate.depth
    notes: list[str] = []

    if depth <= Depth.SNAPSHOT:
        return ResearchPlan(mandate, list(_SNAPSHOT_LENSES), "snapshot", notes)
    if depth == Depth.SCREEN:
        return ResearchPlan(mandate, list(_SCREEN_LENSES), "screen", notes)

    # L2 and every deeper tier run the full lens set; deeper tiers still render
    # the L2 tearsheet for now, with a note that the flagship product is pending.
    if depth > MAX_IMPLEMENTED:
        notes.append(
            f"Requested {depth.label}; the dedicated {depth.label} product arrives "
            f"in a later build phase. Showing the L2 tearsheet across all nine lenses."
        )
    return ResearchPlan(mandate, list(ALL_LENSES), "tearsheet", notes)
