"""Serialise a ResearchOutput into a plain JSON-able dict for the API layer."""
from __future__ import annotations


def research_to_dict(out) -> dict:
    c, m = out.company, out.mandate
    return {
        "company": {
            "symbol": c.symbol, "name": c.name, "ticker": c.ticker,
            "exchange": c.exchange, "sector": c.sector, "industry": c.industry,
            "currency": c.currency, "market_cap": c.market_cap,
        },
        "mandate": {
            "side": m.side.value, "depth": m.depth.code, "depth_label": m.depth.label,
            "market": m.market.key, "market_name": m.market.name,
            "accounting": m.market.accounting, "regulator": m.market.regulator,
            "benchmark": (m.market.benchmarks[0] if m.market.benchmarks else None),
            "default_wacc": m.market.default_wacc,
        },
        "composite_score": out.composite_score,
        "verdict": out.verdict.value,
        "call": {"headline": out.call.headline, "conviction": out.call.conviction,
                 "forensic_gate": out.call.gate},
        "appraisal": _appraisal(out.appraisal),
        "estimates": _estimates(out.consensus),
        "catalysts": [{"date": x.date, "kind": x.kind, "label": x.label}
                      for x in out.catalysts],
        "coverage_note": out.coverage_note or None,
        "narrative": out.narrative or None,
        "lenses": {name: {"score": lens.score, "summary": lens.summary}
                   for name, lens in out.lenses.items()},
        "bull_thesis": list(out.bull_thesis),
        "bear_thesis": list(out.bear_thesis),
        "monitorables": list(out.monitorables),
        "warnings": list(out.warnings),
        "data_sources": dict(out.data_sources),
        "generated_at": out.generated_at,
        "product_text": out.product,
    }


def _appraisal(a) -> dict | None:
    if a is None:
        return None
    return {
        "currency": a.currency, "wacc": a.wacc, "terminal_growth": a.terminal_growth,
        "net_debt": a.net_debt, "price": a.price,
        "weighted_target": a.weighted_target, "target_upside_pct": a.target_upside_pct,
        "fair_low": a.fair_low, "fair_high": a.fair_high,
        "base_growth": a.base_growth, "implied_growth": a.implied_growth,
        "exit_multiple_value": a.exit_multiple_value, "variant": a.variant,
        "scenarios": [
            {"name": s.name, "prob": s.prob, "g0": s.assumptions.g0,
             "ebitda_margin": s.assumptions.ebitda_margin,
             "fair_value": s.dcf.fair_value, "upside_pct": s.upside_pct,
             "terminal_pct": s.dcf.terminal_pct}
            for s in a.scenarios
        ],
        "notes": list(a.notes),
    }


def _estimates(cv) -> dict | None:
    if cv is None:
        return None
    return {
        "source": cv.source,
        "our_growth": cv.our_growth, "implied_growth": cv.implied_growth,
        "variant": cv.variant,
        "lines": [{"metric": e.metric, "fy1": e.fy1, "fy2": e.fy2} for e in cv.estimates],
    }
