"""The agent orchestrator: request → mandate → plan → tools → product.

This is the control loop that turns the analysis engine into an analyst. It sets
the mandate (side × market × depth), resolves the listing and refines the market
from its exchange, runs the planned lens-tools, scores them, decides the
side-specific call, and renders the tier-appropriate product.

Deliberately reuses the engine's own pieces — ``resolve_and_fetch``, the lens
runners, and ``scoring`` — so there is one source of truth for the analytics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..analysis import scoring
from ..config import Config
from ..data import resolve_and_fetch
from ..models import Company, LensResult, Verdict
from ..report.builder import CompanyNotFound
from . import markets, products
from .mandate import Depth, Mandate, MandateRouter, Side
from .planner import ResearchPlan, plan_research
from .products import Call
from .tools import run_tools


@dataclass
class ResearchOutput:
    """Everything the agent produces for one request."""
    mandate: Mandate
    company: Company
    generated_at: str
    plan: ResearchPlan
    lenses: dict[str, LensResult]
    composite_score: float | None
    verdict: Verdict
    call: Call
    bull_thesis: list[str] = field(default_factory=list)
    bear_thesis: list[str] = field(default_factory=list)
    monitorables: list[str] = field(default_factory=list)
    product: str = ""                       # the rendered deliverable (text)
    data_sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def headline(self) -> str:
        return (f"{self.mandate.headline} → {self.call.headline} "
                f"(composite {self.composite_score}/100)")


def research(
    query: str,
    *,
    side: Side | str | None = None,
    depth: Depth | int | str | None = None,
    market: str | None = None,
    config: Config | None = None,
) -> ResearchOutput:
    """Run the equity-research agent over one name and return a mandate-framed output."""
    config = config or Config.default()

    mandate = MandateRouter().route(query, side=side, depth=depth, market=market)

    resolved = resolve_and_fetch(query, config)
    if resolved is None:
        raise CompanyNotFound(
            f"Could not resolve '{query}'. Try a ticker (e.g. POWERINDIA) or a known name."
        )
    company, data, source = resolved

    # refine the market from the resolved listing if it is still generic
    if mandate.market.is_generic:
        refined = markets.infer_profile(
            exchange=company.exchange, currency=company.currency, query=query)
        mandate = mandate.with_market(refined)

    plan = plan_research(mandate)
    lenses = run_tools(plan.lenses, data, config)

    composite = scoring.composite(lenses, config.weights)
    verdict = scoring.verdict_from(composite)
    bull, bear, monitor = scoring.bull_bear_monitorables(lenses)
    call = products.decide_call(mandate.side, verdict, lenses)

    warnings = _provenance_warnings(company, data, source, lenses)

    rendered = products.render_product(
        mandate=mandate, company=company, generated_at=_now(), lenses=lenses,
        composite=composite, verdict=verdict, bull=bull, bear=bear, monitor=monitor,
        call=call, product=plan.product, plan_notes=plan.notes, warnings=warnings,
    )

    return ResearchOutput(
        mandate=mandate, company=company, generated_at=_now(), plan=plan,
        lenses=lenses, composite_score=composite, verdict=verdict, call=call,
        bull_thesis=bull, bear_thesis=bear, monitorables=monitor, product=rendered,
        data_sources={
            "prices": data.prices.source if data.prices else "n/a",
            "fundamentals": data.fundamentals.source if data.fundamentals else "n/a",
            "resolver": source,
        },
        warnings=warnings,
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _provenance_warnings(company, data, source, lenses) -> list[str]:
    warnings: list[str] = []
    sources = {
        data.prices.source if data.prices else "n/a",
        data.fundamentals.source if data.fundamentals else "n/a",
        source,
    }
    if "offline-sample" in sources:
        warnings.append(
            "Data is from bundled ILLUSTRATIVE snapshots (offline mode). Figures are "
            "approximate/synthetic — connect a live provider before acting.")
    if company.sector is None:
        warnings.append("Unknown symbol — only synthetic price history was available.")
    fund = lenses.get("Fundamental")
    if "Fundamental" in lenses and not (fund and fund.has_score):
        warnings.append(
            "No fundamentals available — this rests on price/technical lenses alone; "
            "treat it as a trading read, not a business assessment.")
    return warnings
