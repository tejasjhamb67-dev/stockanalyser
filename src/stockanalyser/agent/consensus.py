"""Estimates & consensus — our numbers, and where they sit versus the market's.

A covering analyst publishes *estimates* (next two years of revenue / EBITDA / EPS)
and states a *variant* — how their view differs from consensus. Real Street consensus
needs a data provider; offline we do the honest fallback: a **price-implied** consensus
derived from the reverse-DCF (the growth the current price already pays for). Either
way the shape is the same, so a live provider slots in behind ``ConsensusView`` later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Fundamentals


@dataclass
class EstimateLine:
    metric: str                 # "Revenue" | "EBITDA" | "EPS"
    fy1: float | None
    fy2: float | None
    unit: str = ""


@dataclass
class ConsensusView:
    source: str                 # where the "consensus" came from
    our_growth: float | None    # our base-case year-1 revenue growth
    implied_growth: float | None
    variant: str | None
    estimates: list[EstimateLine] = field(default_factory=list)
    note: str = ""


def build_consensus(appraisal, f: Fundamentals | None) -> ConsensusView | None:
    """Assemble our forward estimates + the variant-vs-market read from the appraisal."""
    if appraisal is None or f is None or appraisal.base_projection is None:
        return None
    proj = appraisal.base_projection
    latest = f.latest
    shares = f.shares_outstanding or (latest.shares_outstanding if latest else None)

    # net margin from the latest reported year, applied to projected revenue for EPS —
    # a transparent model-derived estimate (labelled as such, never dressed as Street data)
    net_margin = None
    if latest and latest.revenue and latest.net_income is not None and latest.revenue > 0:
        net_margin = latest.net_income / latest.revenue

    estimates: list[EstimateLine] = []
    if len(proj.years) >= 2:
        y1, y2 = proj.years[0], proj.years[1]
        estimates.append(EstimateLine("Revenue", round(y1.revenue, 0), round(y2.revenue, 0)))
        estimates.append(EstimateLine("EBITDA", round(y1.ebitda, 0), round(y2.ebitda, 0)))
        if net_margin is not None and shares:
            eps1 = y1.revenue * net_margin / shares
            eps2 = y2.revenue * net_margin / shares
            estimates.append(EstimateLine("EPS", round(eps1, 1), round(eps2, 1)))

    source = ("price-implied (reverse-DCF)" if appraisal.implied_growth is not None
              else "model only — price-implied growth not bracketable")
    return ConsensusView(
        source=source,
        our_growth=appraisal.base_growth,
        implied_growth=appraisal.implied_growth,
        variant=appraisal.variant,
        estimates=estimates,
        note=("Estimates are model-derived (our forecast), not Street consensus — "
              "connect a data provider for live consensus."),
    )
