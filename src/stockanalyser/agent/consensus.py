"""Estimates & consensus — our numbers, and where they sit versus the Street's.

When a live provider supplies **real sell-side consensus** (analyst price target,
ratings distribution, forward EPS/revenue estimates), the variant is the genuine
article: our triangulated target vs the Street mean, our call vs the Street rating.
Offline — no coverage data — it falls back to a **price-implied** consensus from the
reverse-DCF (the growth the current price already pays for). Same `ConsensusView`
shape either way, so the products don't care which path produced it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Fundamentals, StreetConsensus


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
    estimates: list[EstimateLine] = field(default_factory=list)   # our model estimates
    note: str = ""
    # Street consensus (only when a live provider supplies it)
    is_street: bool = False
    our_target: float | None = None
    street_target: float | None = None
    street_target_low: float | None = None
    street_target_high: float | None = None
    street_rating: str | None = None
    street_num_analysts: int | None = None
    street_estimates: list[EstimateLine] = field(default_factory=list)
    target_gap_pct: float | None = None       # our target vs the Street mean


def build_consensus(appraisal, f: Fundamentals | None,
                    street: StreetConsensus | None = None) -> ConsensusView | None:
    """Assemble our forward estimates + the variant read. Prefers real Street
    consensus (`street`) and falls back to the appraisal's price-implied view."""
    if appraisal is None or f is None or appraisal.base_projection is None:
        return None
    our_est = _our_estimates(appraisal, f)
    our_target = appraisal.weighted_target

    if street is not None and street.has_view and street.price_target_mean is not None:
        gap = (_pct(our_target, street.price_target_mean)
               if our_target is not None else None)
        n = street.num_analysts
        return ConsensusView(
            source=(f"Street consensus ({n} analysts)" if n else "Street consensus"),
            our_growth=appraisal.base_growth, implied_growth=appraisal.implied_growth,
            variant=_street_variant(our_target, street, gap),
            estimates=our_est, note="Street figures via the live provider.",
            is_street=True, our_target=our_target,
            street_target=street.price_target_mean,
            street_target_low=street.price_target_low,
            street_target_high=street.price_target_high,
            street_rating=(street.recommendation_key.replace("_", " ")
                           if street.recommendation_key else None),
            street_num_analysts=n, street_estimates=_street_estimates(street),
            target_gap_pct=gap)

    # ── price-implied fallback (offline / no coverage) ──
    source = ("price-implied (reverse-DCF)" if appraisal.implied_growth is not None
              else "model only — price-implied growth not bracketable")
    return ConsensusView(
        source=source, our_growth=appraisal.base_growth,
        implied_growth=appraisal.implied_growth, variant=appraisal.variant,
        estimates=our_est, our_target=our_target,
        note=("Estimates are model-derived (our forecast), not Street consensus — "
              "connect a data provider for live consensus."))


# ── helpers ──────────────────────────────────────────────────────────────────
def _our_estimates(appraisal, f: Fundamentals) -> list[EstimateLine]:
    proj = appraisal.base_projection
    latest = f.latest
    shares = f.shares_outstanding or (latest.shares_outstanding if latest else None)
    net_margin = None
    if latest and latest.revenue and latest.net_income is not None and latest.revenue > 0:
        net_margin = latest.net_income / latest.revenue
    out: list[EstimateLine] = []
    if len(proj.years) >= 2:
        y1, y2 = proj.years[0], proj.years[1]
        out.append(EstimateLine("Revenue", round(y1.revenue, 0), round(y2.revenue, 0)))
        out.append(EstimateLine("EBITDA", round(y1.ebitda, 0), round(y2.ebitda, 0)))
        if net_margin is not None and shares:
            out.append(EstimateLine("EPS", round(y1.revenue * net_margin / shares, 1),
                                    round(y2.revenue * net_margin / shares, 1)))
    return out


def _street_estimates(street: StreetConsensus) -> list[EstimateLine]:
    by: dict[str, dict[str, float | None]] = {}
    for e in street.estimates:
        by.setdefault(e.metric, {})[e.period] = e.mean
    out: list[EstimateLine] = []
    for metric in ("Revenue", "EPS"):
        if metric in by:
            d = by[metric]
            out.append(EstimateLine(metric, d.get("curr FY"), d.get("next FY")))
    return out


def _street_variant(our_target, street: StreetConsensus, gap) -> str | None:
    parts: list[str] = []
    st, n = street.price_target_mean, street.num_analysts
    tag = f" ({n} analysts)" if n else ""
    if our_target is not None and st is not None and gap is not None:
        if gap > 5:
            parts.append(f"Above the Street — our {our_target:,.0f} target is {gap:+.0f}% "
                         f"vs the consensus mean {st:,.0f}{tag}; we see more upside than "
                         f"the sell-side.")
        elif gap < -5:
            parts.append(f"Below the Street — our {our_target:,.0f} sits {gap:+.0f}% under "
                         f"the consensus mean {st:,.0f}{tag}; we're more cautious than the "
                         f"sell-side.")
        else:
            parts.append(f"In line with the Street — our {our_target:,.0f} ≈ consensus "
                         f"mean {st:,.0f}{tag}.")
    if street.recommendation_key:
        parts.append(f"Street rates it {street.recommendation_key.replace('_', ' ')}.")
    return " ".join(parts) or None


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 1)
