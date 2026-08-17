"""Living coverage (L5) — maintaining the call as new information lands.

Where L4 initiates a name, L5 *keeps* it: it reviews the most recent results,
re-runs the estimates and reports how they moved since the last note, tracks the
monitorables (what got resolved, what is new) and the rating's trajectory, and
previews what to watch into the next print.

Estimate revisions and the rating trajectory are only meaningful across time, so
they read from coverage memory. Offline data is static — so a second run correctly
reports "estimates unchanged"; the machinery lights up the moment a live provider
feeds a fresh quarter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Fundamentals
from .memory import CoverageEntry


@dataclass
class EarningsReview:
    period: str
    revenue_yoy: float | None
    ebitda_margin: float | None
    margin_delta_bps: float | None
    eps: float | None
    eps_yoy: float | None
    cfo_to_pat: float | None
    lines: list[str] = field(default_factory=list)


@dataclass
class EarningsPreview:
    label: str
    est_revenue: float | None
    est_ebitda: float | None
    est_eps: float | None
    watch: list[str] = field(default_factory=list)


@dataclass
class RevisionLine:
    metric: str
    old: float | None
    new: float | None
    delta_pct: float | None


@dataclass
class ThesisTracker:
    rating_trajectory: list[tuple[str, str]]      # [(date, rating), ...] oldest→newest
    new_monitorables: list[str]
    resolved_monitorables: list[str]
    persisting: list[str]


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1) * 100


def earnings_review(f: Fundamentals | None) -> EarningsReview | None:
    """Analyst read of the most recent reported period vs the prior one."""
    if f is None:
        return None
    stmts = f.ordered()
    if len(stmts) < 2:
        return None
    latest, prior = stmts[-1], stmts[-2]
    shares = f.shares_outstanding or latest.shares_outstanding

    rev_yoy = _pct(latest.revenue, prior.revenue)
    m_now = (latest.ebitda / latest.revenue * 100
             if latest.ebitda is not None and latest.revenue else None)
    m_prev = (prior.ebitda / prior.revenue * 100
              if prior.ebitda is not None and prior.revenue else None)
    margin_delta = ((m_now - m_prev) * 100 if m_now is not None and m_prev is not None
                    else None)   # in bps
    eps_now = (latest.net_income / shares if latest.net_income is not None and shares else None)
    eps_prev = (prior.net_income / shares if prior.net_income is not None and shares else None)
    eps_yoy = _pct(eps_now, eps_prev)
    cfo_pat = (latest.cfo / latest.net_income
               if latest.cfo is not None and latest.net_income else None)

    lines: list[str] = []
    if rev_yoy is not None:
        lines.append(f"Revenue {rev_yoy:+.1f}% YoY to {latest.revenue:,.0f}.")
    if margin_delta is not None:
        lines.append(f"EBITDA margin {m_now:.1f}% ({margin_delta:+.0f} bps YoY).")
    if eps_yoy is not None:
        lines.append(f"EPS {eps_yoy:+.1f}% YoY to {eps_now:,.1f}.")
    if cfo_pat is not None:
        lines.append(f"Cash conversion (CFO/PAT) {cfo_pat:.2f} — "
                     f"{'healthy' if cfo_pat >= 0.8 else 'watch accrual quality'}.")
    lines.append("Beat/miss vs estimates activates with a live estimates provider.")
    return EarningsReview(period=latest.period, revenue_yoy=_r(rev_yoy),
                          ebitda_margin=_r(m_now), margin_delta_bps=_r(margin_delta),
                          eps=_r(eps_now, 1), eps_yoy=_r(eps_yoy), cfo_to_pat=_r(cfo_pat, 2),
                          lines=lines)


def earnings_preview(consensus) -> EarningsPreview | None:
    """What our model expects next period, and what to watch."""
    if consensus is None or not consensus.estimates:
        return None
    watch = []
    if consensus.variant:
        watch.append(consensus.variant)
    watch.append("Margin trajectory vs the modelled path, and any change to the growth driver.")
    return EarningsPreview(
        label="next reported period (model)",
        est_revenue=_est(consensus, "Revenue"),
        est_ebitda=_est(consensus, "EBITDA"),
        est_eps=_est(consensus, "EPS"),
        watch=watch)


def estimate_revisions(prev: CoverageEntry | None, consensus) -> list[RevisionLine]:
    """How this run's estimates moved versus what we last put on record."""
    if prev is None or consensus is None:
        return []
    pairs = [
        ("Revenue", prev.est_rev_fy1, _est(consensus, "Revenue")),
        ("EBITDA", prev.est_ebitda_fy1, _est(consensus, "EBITDA")),
        ("EPS", prev.est_eps_fy1, _est(consensus, "EPS")),
    ]
    out: list[RevisionLine] = []
    for metric, old, new in pairs:
        if old is None or new is None:
            continue
        delta = (new / old - 1) * 100 if old else None
        # a "revision" means the estimate actually moved; skip unchanged lines
        if delta is None or abs(delta) < 0.1:
            continue
        out.append(RevisionLine(metric, old, new, _r(delta)))
    return out


def thesis_tracker(history: list[CoverageEntry], current: CoverageEntry,
                   prev: CoverageEntry | None, monitor: list[str]) -> ThesisTracker:
    trajectory = [(e.date, e.rating) for e in history] + [(current.date, current.rating)]
    prev_m = set(prev.monitorables) if prev else set()
    now_m = set(monitor)
    return ThesisTracker(
        rating_trajectory=trajectory,
        new_monitorables=sorted(now_m - prev_m),
        resolved_monitorables=sorted(prev_m - now_m),
        persisting=sorted(now_m & prev_m))


# ── helpers ──────────────────────────────────────────────────────────────────
def _est(consensus, metric: str):
    for e in consensus.estimates:
        if e.metric == metric:
            return e.fy1
    return None


def _r(x, ndigits: int = 1):
    return round(x, ndigits) if x is not None else None
