"""Tests for Phase 3 — L4 initiation: estimates/consensus, catalyst calendar,
coverage memory (track-the-call), and the assembled initiation report.

Offline and deterministic. Coverage memory is isolated to a tmp store per test.
"""
from __future__ import annotations

import pytest

from stockanalyser.config import Config
from stockanalyser.data import resolve_and_fetch
from stockanalyser.agent import (
    research, MandateRouter, build_appraisal, build_consensus, build_catalysts,
    CoverageMemory, CoverageEntry, coverage_note,
)
from stockanalyser.agent.markets import PROFILES
from stockanalyser.agent.planner import plan_research

CFG = Config(provider="offline", use_llm=False)


def _data(name):
    _, data, _ = resolve_and_fetch(name, CFG)
    return data


# ── estimates / consensus ────────────────────────────────────────────────────
def test_consensus_has_forward_estimates_and_variant():
    d = _data("RELIANCE")
    ap = build_appraisal(d.fundamentals, PROFILES["IN"], CFG)
    cv = build_consensus(ap, d.fundamentals)
    assert cv is not None
    metrics = {e.metric for e in cv.estimates}
    assert {"Revenue", "EBITDA"}.issubset(metrics)
    # FY2 revenue should exceed FY1 in the base case (growth > 0)
    rev = next(e for e in cv.estimates if e.metric == "Revenue")
    assert rev.fy2 > rev.fy1
    assert "price-implied" in cv.source or "model only" in cv.source


def test_consensus_none_without_appraisal():
    assert build_consensus(None, _data("RELIANCE").fundamentals) is None


# ── catalysts ────────────────────────────────────────────────────────────────
def test_catalysts_built_and_sorted_desc():
    cats = build_catalysts(_data("POWERINDIA"))
    assert cats                                  # sample has corporate actions
    dates = [c.date for c in cats]
    assert dates == sorted(dates, reverse=True)


# ── coverage memory ──────────────────────────────────────────────────────────
def test_memory_records_and_reloads(tmp_path):
    mem = CoverageMemory(tmp_path)
    assert mem.load("ACME") is None
    e = CoverageEntry(symbol="ACME", name="Acme", date="2026-01-01", side="sell-side",
                      market="IN", rating="Buy", conviction="Moderate", target=100.0,
                      upside_pct=10.0, composite=70.0, verdict="Buy", base_growth=0.2,
                      gate="pass", monitorables=["watch margins"])
    assert mem.record(e) is True
    back = mem.load("ACME")
    assert back is not None and back.rating == "Buy" and back.target == 100.0


def test_coverage_note_initiation_then_update(tmp_path):
    mem = CoverageMemory(tmp_path)
    first = CoverageEntry("ACME", "Acme", "2026-01-01", "sell-side", "IN", "Buy",
                          "Moderate", 100.0, 10.0, 70.0, "Buy", 0.2, "pass",
                          ["watch margins"])
    assert coverage_note(None, first).startswith("INITIATING COVERAGE")
    mem.record(first)
    second = CoverageEntry("ACME", "Acme", "2026-04-01", "sell-side", "IN", "Sell",
                           "High", 80.0, -20.0, 55.0, "Avoid", 0.15, "pass",
                           ["watch margins", "new debt raise"])
    note = coverage_note(mem.load("ACME"), second)
    assert "UPDATE" in note
    assert "Buy → Sell" in note
    assert "100" in note and "80" in note        # target revision shown
    assert "new monitorable" in note


def test_memory_unwritable_store_is_graceful(tmp_path):
    # point the store at a path under a file (can't mkdir) → record returns False
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    mem = CoverageMemory(blocker / "sub")
    ok = mem.record(CoverageEntry("X", "X", "2026-01-01", "sell-side", "IN", "Buy",
                                  "Moderate", 1.0, 1.0, 50.0, "Hold", 0.1, "pass", []))
    assert ok is False


# ── planner ──────────────────────────────────────────────────────────────────
def test_initiation_plan():
    plan = plan_research(MandateRouter().route("x", depth="L4"))
    assert plan.product == "initiation"


def test_living_coverage_degrades_to_initiation():
    plan = plan_research(MandateRouter().route("x", depth="L5"))
    assert plan.product == "initiation"
    assert plan.notes and "later build phase" in plan.notes[0]


# ── end-to-end initiation ────────────────────────────────────────────────────
def test_end_to_end_initiation_report(tmp_path):
    out = research("RELIANCE", side="sell-side", depth="L4", config=CFG,
                   coverage_store=str(tmp_path))
    p = out.product
    assert "INITIATION OF COVERAGE" in p
    assert "1 · Industry & positioning" in p
    assert "2 · Investment thesis" in p
    assert "3 · Estimates & consensus" in p
    assert "4 · Valuation" in p
    assert "5 · Risks & monitorables" in p
    assert "12-month target" in p
    assert out.consensus is not None
    assert out.coverage_note.startswith("INITIATING COVERAGE")


def test_initiation_then_second_run_is_update(tmp_path):
    research("RELIANCE", side="sell-side", depth="L4", config=CFG,
             coverage_store=str(tmp_path))
    out2 = research("RELIANCE", side="sell-side", depth="L4", config=CFG,
                    coverage_store=str(tmp_path))
    assert out2.coverage_note.startswith("UPDATE")
    assert "COVERAGE UPDATE" in out2.product


def test_initiation_honours_forensic_gate(tmp_path):
    out = research("REDFLAG", side="buy-side", depth="L4", config=CFG,
                   coverage_store=str(tmp_path))
    assert out.call.gate == "fail"
    assert "Forensic gate FAILED" in out.product


def test_record_coverage_false_does_not_persist(tmp_path):
    out = research("RELIANCE", depth="L4", config=CFG, coverage_store=str(tmp_path),
                   record_coverage=False)
    assert out.coverage_note.startswith("INITIATING")
    assert CoverageMemory(tmp_path).load("RELIANCE") is None
