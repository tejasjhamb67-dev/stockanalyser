"""Lens-as-tool adapters.

The nine analysis lenses are already plain functions; here they are wrapped as
uniform, named tools the planner can select from, run defensively (one failing
tool degrades to an 'insufficient' lens instead of sinking the run), and — later
phases — describe to an LLM tool-caller. The runner map is imported from the
existing report builder so there is a single source of truth for the lens set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..config import Config
from ..models import CompanyData, LensResult
from ..report.builder import LENS_RUNNERS


@dataclass(frozen=True)
class Tool:
    name: str
    run: Callable[[CompanyData, Config], LensResult]


LENS_TOOLS: dict[str, Tool] = {
    name: Tool(name=name, run=runner) for name, runner in LENS_RUNNERS
}

ALL_LENSES: list[str] = [name for name, _ in LENS_RUNNERS]


def run_tools(names: list[str], data: CompanyData, config: Config) -> dict[str, LensResult]:
    """Run the named lens-tools defensively, preserving request order."""
    out: dict[str, LensResult] = {}
    for name in names:
        tool = LENS_TOOLS.get(name)
        if tool is None:
            continue
        try:
            out[name] = tool.run(data, config)
        except Exception as exc:  # never let one tool sink the run
            lr = LensResult(lens=name)
            lr.summary = f"Lens failed: {type(exc).__name__}: {exc}"
            out[name] = lr
    return out
