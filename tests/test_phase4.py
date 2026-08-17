"""Tests for Phase 4 — L5 living coverage + universe conviction ranking.

Offline and deterministic; coverage memory isolated to a tmp store per test.
"""
from __future__ import annotations

import pytest

from stockanalyser.config import Config
from stockanalyser.data import resolve_and_fetch
from stockanalyser.agent import (
    research, MandateRouter, build_appraisal, build_consensus,
    earnings_review, earnings_preview, estimate_revisions, thesis_tracker,
    rank_universe, render_conviction_list, CoverageEntry, Side,
)
from stockanalyser.agent.markets import PROFILES
from stockanalyser.agent.planner import plan_research

CFG = Config(provider="offline", use_llm=False)


def _data(name):
    _, data, _ = resolve_and_fetch(name, CFG)
    return data


# ── earnings review / preview ────────────────────────────────────────────────
def test_earnings_review_reports_yoy():
    rev = earnings_review(_data("RELIANCE").fundamentals)
    assert rev is not None
    assert rev.revenue_yoy is not None
    assert rev.lines and any("Revenue" in ln for ln in rev.lines)


def test_earnings_preview_from_consensus():
    d = _data("RELIANCE")
    ap = build_appraisal(d.fundamentals, PROFILES["IN"], CFG)
    cv = build_consensus(ap, d.fundamentals)
    pv = earnings_preview(cv)
    assert pv is not None and pv.est_revenue is not None


# ── estimate revisions ───────────────────────────────────────────────────────
def test_estimate_revisions_detect_change():
    d = _data("RELIANCE")
    ap = build_appraisal(d.fundamentals, PROFILES["IN"], CFG)
    cv = build_consensus(ap, d.fundamentals)
    rev_now = next(e.fy1 for e in cv.estimates if e.metric == "Revenue")
    # a prior entry whose estimate was 10% lower -> current run is a +ve revision
    prev = CoverageEntry("R", "R", "2026-01-01", "sell-side", "IN", "Buy", "Mod",
                         100.0, 5.0, 60.0, "Buy", 0.2, "pass", [],
                         est_rev_fy1=rev_now * 0.9, est_ebitda_fy1=None, est_eps_fy1=None)
    lines = estimate_revisions(prev, cv)
    rline = next(l for l in lines if l.metric == "Revenue")
    assert rline.delta_pct == pytest.approx(11.1, abs=0.3)   # +1/0.9 - 1 ≈ +11%


def test_no_revisions_without_prior():
    d = _data("RELIANCE")
    cv = build_consensus(build_appraisal(d.fundamentals, PROFILES["IN"], CFG), d.fundamentals)
    assert estimate_revisions(None, cv) == []


# ── thesis tracker ───────────────────────────────────────────────────────────
def test_thesis_tracker_diffs_monitorables():
    prev = CoverageEntry("R", "R", "2026-01-01", "sell-side", "IN", "Buy", "Mod",
                         100.0, 5.0, 60.0, "Buy", 0.2, "pass", ["A", "B"])
    cur = CoverageEntry("R", "R", "2026-04-01", "sell-side", "IN", "Hold", "-",
                        90.0, -5.0, 55.0, "Hold", 0.18, "pass", ["B", "C"])
    tr = thesis_tracker([prev], cur, prev, ["B", "C"])
    assert tr.new_monitorables == ["C"]
    assert tr.resolved_monitorables == ["A"]
    assert tr.persisting == ["B"]
    assert tr.rating_trajectory[-1] == ("2026-04-01", "Hold")


# ── planner + end-to-end L5 ──────────────────────────────────────────────────
def test_l5_plan_is_coverage():
    plan = plan_research(MandateRouter().route("x", depth="L5"))
    assert plan.product == "coverage"


def test_end_to_end_living_coverage(tmp_path):
    out = research("RELIANCE", side="sell-side", depth="L5", config=CFG,
                   coverage_store=str(tmp_path))
    p = out.product
    assert "LIVING COVERAGE" in p
    assert "Results review" in p
    assert "Preview" in p
    assert out.coverage_note.startswith("INITIATING")


def test_l5_second_run_shows_trajectory_and_unchanged_estimates(tmp_path):
    research("RELIANCE", depth="L5", config=CFG, coverage_store=str(tmp_path))
    out2 = research("RELIANCE", depth="L5", config=CFG, coverage_store=str(tmp_path))
    assert "Rating trajectory" in out2.product
    # static offline data -> estimates unchanged across the two runs
    assert "estimates unchanged" in out2.product


# ── universe conviction ranking ──────────────────────────────────────────────
def test_rank_universe_orders_by_conviction_and_gates_redflag():
    rows = rank_universe(["RELIANCE", "Hitachi Energy", "REDFLAG"],
                         side="buy-side", depth="L3", config=CFG)
    assert len(rows) == 3
    # sorted descending by conviction
    convs = [r.conviction for r in rows]
    assert convs == sorted(convs, reverse=True)
    # the forensic red-flag name is sunk to the bottom
    assert rows[-1].query == "REDFLAG"
    assert rows[-1].gate == "fail"


def test_render_conviction_list_smoke():
    rows = rank_universe(["RELIANCE", "REDFLAG"], side="sell-side", depth="L2", config=CFG)
    txt = render_conviction_list(rows, Side.SELL_SIDE)
    assert "CONVICTION LIST" in txt
    assert "RELIANCE" in txt
