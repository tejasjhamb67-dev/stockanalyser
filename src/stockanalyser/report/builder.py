"""The orchestrator: query → resolve → fetch → run all lenses → score → narrate.

This is what `stockanalyser.analyse()` and the CLI call. Every lens is run
defensively; one blowing up degrades to an 'insufficient' lens rather than
sinking the whole report.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..analysis import (
    fundamental,
    governance,
    ownership,
    qualitative,
    quality,
    scoring,
    sector,
    spikes,
    technical,
    valuation,
)
from ..config import Config
from ..data import resolve_and_fetch
from ..models import CompanyData, LensResult, Report, Verdict
from ..narrative import synthesize

LENS_RUNNERS = [
    ("Technical", lambda d, c: technical.analyse(d, c.technical)),
    ("Spike", lambda d, c: spikes.analyse(d, c.spike)),
    ("Fundamental", lambda d, c: fundamental.analyse(d)),
    ("Quality", lambda d, c: quality.analyse(d)),
    ("Valuation", lambda d, c: valuation.analyse(d, c.valuation)),
    ("Qualitative", lambda d, c: qualitative.analyse(d)),
    ("Governance", lambda d, c: governance.analyse(d)),
    ("Sector", lambda d, c: sector.analyse(d)),
    ("Ownership", lambda d, c: ownership.analyse(d)),
]


class CompanyNotFound(LookupError):
    pass


def run_lenses(data: CompanyData, config: Config) -> dict[str, LensResult]:
    lenses: dict[str, LensResult] = {}
    for name, runner in LENS_RUNNERS:
        try:
            lenses[name] = runner(data, config)
        except Exception as exc:  # never let one lens sink the report
            lr = LensResult(lens=name)
            lr.summary = f"Lens failed: {type(exc).__name__}: {exc}"
            lenses[name] = lr
    return lenses


def build_report(query: str, config: Config | None = None) -> Report:
    config = config or Config.default()

    resolved = resolve_and_fetch(query, config)
    if resolved is None:
        raise CompanyNotFound(
            f"Could not resolve '{query}'. Try a ticker (e.g. POWERINDIA) or a known name."
        )
    company, data, source = resolved

    lenses = run_lenses(data, config)

    report = Report(
        company=company,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        data_sources={
            "prices": data.prices.source if data.prices else "n/a",
            "fundamentals": data.fundamentals.source if data.fundamentals else "n/a",
            "resolver": source,
        },
        lenses=lenses,
    )

    report.composite_score = scoring.composite(lenses, config.weights)
    report.verdict = scoring.verdict_from(report.composite_score)
    report.bull_thesis, report.bear_thesis, report.monitorables = \
        scoring.bull_bear_monitorables(lenses)

    # provenance / honesty warnings
    if any(s == "offline-sample" for s in report.data_sources.values()):
        report.warnings.append(
            "Data is from bundled ILLUSTRATIVE snapshots (offline mode). "
            "Figures are approximate/synthetic — connect a live provider before acting."
        )
    if company.sector is None:
        report.warnings.append("Unknown symbol — only synthetic price history was available.")
    fund = lenses.get("Fundamental")
    if not (fund and fund.has_score):
        report.warnings.append(
            "No fundamentals available — this verdict rests on price/technical lenses "
            "alone. Treat it as a trading read, not a business assessment."
        )

    report.narrative = synthesize(report, use_llm=config.use_llm)
    return report
