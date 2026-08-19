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
from .appraisal import Appraisal, build_appraisal
from .catalysts import Catalyst, build_catalysts
from .consensus import ConsensusView, build_consensus
from .coverage import (
    earnings_preview, earnings_review, estimate_revisions, thesis_tracker,
)
from .mandate import Depth, Mandate, MandateRouter, Side
from .memory import CoverageEntry, coverage_note, now_date, open_coverage_memory
from .narrative import build_narrative
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
    appraisal: Appraisal | None = None
    consensus: ConsensusView | None = None
    catalysts: list[Catalyst] = field(default_factory=list)
    coverage_note: str = ""
    review: object | None = None            # L5: EarningsReview
    preview: object | None = None           # L5: EarningsPreview
    revisions: list = field(default_factory=list)   # L5: list[RevisionLine]
    tracker: object | None = None           # L5: ThesisTracker
    narrative: str = ""                      # the analyst read (prose)
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
    coverage_store: str | None = None,
    record_coverage: bool = True,
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

    warnings = _provenance_warnings(company, data, source, lenses)
    generated_at = _now()

    # L3+: build the driver model + triangulated valuation first, so the call can be
    # reconciled with the price target (a rating must be consistent with fair value)
    appraisal = None
    if plan.product in ("deepdive", "initiation", "coverage"):
        appraisal = build_appraisal(data.fundamentals, mandate.market, config)

    call = products.decide_call(mandate.side, verdict, lenses, appraisal)

    # L4/L5: estimates/consensus, catalyst calendar, and coverage memory (track the call)
    consensus = catalysts = None
    note = ""
    cov = None
    if plan.product in ("initiation", "coverage"):
        consensus = build_consensus(appraisal, data.fundamentals, street=data.consensus)
        catalysts = build_catalysts(data)
        cov = _update_coverage(
            company, mandate, call, appraisal, composite, verdict, monitor,
            consensus, coverage_store, record_coverage)
        note = cov.note

    review = preview = tracker = None
    revisions: list = []
    if plan.product == "coverage":
        review = earnings_review(data.fundamentals)
        preview = earnings_preview(consensus)
        revisions = estimate_revisions(cov.prev, consensus)
        tracker = thesis_tracker(cov.history, cov.entry, cov.prev, monitor)

    out = ResearchOutput(
        mandate=mandate, company=company, generated_at=generated_at, plan=plan,
        lenses=lenses, composite_score=composite, verdict=verdict, call=call,
        appraisal=appraisal, consensus=consensus, catalysts=catalysts or [],
        coverage_note=note, review=review, preview=preview, revisions=revisions,
        tracker=tracker,
        bull_thesis=bull, bear_thesis=bear, monitorables=monitor,
        data_sources={
            "prices": data.prices.source if data.prices else "n/a",
            "fundamentals": data.fundamentals.source if data.fundamentals else "n/a",
            "resolver": source,
        },
        warnings=warnings,
    )

    # the analyst read — deterministic (offline) or LLM-enhanced when a key is present
    if plan.product in ("tearsheet", "deepdive", "initiation", "coverage"):
        out.narrative = build_narrative(out, use_llm=config.use_llm)

    if plan.product == "initiation":
        out.product = products.render_initiation(
            mandate=mandate, company=company, generated_at=generated_at, lenses=lenses,
            composite=composite, verdict=verdict, call=call, bull=bull, bear=bear,
            monitor=monitor, appraisal=appraisal, consensus=consensus,
            catalysts=catalysts, coverage_note=note, plan_notes=plan.notes,
            warnings=warnings, narrative=out.narrative)
    elif plan.product == "coverage":
        out.product = products.render_coverage(
            mandate=mandate, company=company, generated_at=generated_at, call=call,
            verdict=verdict, composite=composite, appraisal=appraisal,
            coverage_note=note, review=review, preview=preview, revisions=revisions,
            tracker=tracker, monitor=monitor, plan_notes=plan.notes, warnings=warnings,
            narrative=out.narrative, consensus=consensus)
    else:
        out.product = products.render_product(
            mandate=mandate, company=company, generated_at=generated_at, lenses=lenses,
            composite=composite, verdict=verdict, bull=bull, bear=bear, monitor=monitor,
            call=call, product=plan.product, plan_notes=plan.notes, warnings=warnings,
            appraisal=appraisal, narrative=out.narrative)
    return out


@dataclass
class _Coverage:
    note: str
    prev: CoverageEntry | None
    entry: CoverageEntry
    history: list[CoverageEntry]


def _update_coverage(company, mandate, call, appraisal, composite, verdict, monitor,
                     consensus, store, record: bool) -> _Coverage:
    """Diff this call against the last one on record, then persist it. Fully defensive —
    coverage tracking must never break the research path."""
    est = {e.metric: e.fy1 for e in consensus.estimates} if consensus else {}
    entry = CoverageEntry(
        symbol=company.symbol, name=company.name, date=now_date(),
        side=mandate.side.value, market=mandate.market.key,
        rating=call.headline, conviction=call.conviction,
        target=appraisal.weighted_target if appraisal else None,
        upside_pct=appraisal.target_upside_pct if appraisal else None,
        composite=composite, verdict=verdict.value,
        base_growth=appraisal.base_growth if appraisal else None,
        gate=call.gate, monitorables=list(monitor[:4]),
        est_rev_fy1=est.get("Revenue"), est_ebitda_fy1=est.get("EBITDA"),
        est_eps_fy1=est.get("EPS"))
    try:
        mem = open_coverage_memory(store)
        history = mem.history(company.symbol)         # prior calls (excludes this one)
        prev = history[-1] if history else None
        note = coverage_note(prev, entry)
        if record and not mem.record(entry):
            note += " (coverage store not writable — not persisted)"
        return _Coverage(note=note, prev=prev, entry=entry, history=history)
    except Exception as exc:  # never sink research over memory bookkeeping
        return _Coverage(note=f"Coverage memory unavailable ({type(exc).__name__}).",
                         prev=None, entry=entry, history=[])


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
