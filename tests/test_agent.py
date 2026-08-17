"""Tests for the equity-research agent layer (Phase 1): mandate, markets,
planner, forensic gate, side-specific calls, and end-to-end products.

All offline and deterministic — no network, no LLM.
"""
from __future__ import annotations

import pytest

from stockanalyser.config import Config
from stockanalyser.agent import research, Side, Depth, MandateRouter, infer_profile
from stockanalyser.agent.planner import plan_research
from stockanalyser.agent.products import decide_call
from stockanalyser.models import LensResult, Verdict

CFG = Config(provider="offline", use_llm=False)


# ── mandate routing ──────────────────────────────────────────────────────────
def test_router_defaults_to_sell_side_brief():
    m = MandateRouter().route("Hitachi Energy")
    assert m.side is Side.SELL_SIDE
    assert m.depth is Depth.BRIEF


def test_router_infers_buy_side_from_language():
    m = MandateRouter().route("should I buy this for my portfolio, and how big a position?")
    assert m.side is Side.BUY_SIDE


def test_router_infers_sell_side_from_language():
    m = MandateRouter().route("initiate coverage with a rating and price target")
    assert m.side is Side.SELL_SIDE
    assert m.depth is Depth.INITIATION


def test_router_infers_depth_snapshot():
    m = MandateRouter().route("give me a quick take on RELIANCE")
    assert m.depth is Depth.SNAPSHOT


def test_explicit_overrides_beat_inference():
    m = MandateRouter().route("quick take", side="buy-side", depth="L4")
    assert m.side is Side.BUY_SIDE and m.depth is Depth.INITIATION


def test_bad_side_and_depth_raise():
    with pytest.raises(ValueError):
        MandateRouter().route("x", side="middle-office")
    with pytest.raises(ValueError):
        MandateRouter().route("x", depth="L9")


# ── market profiles ──────────────────────────────────────────────────────────
def test_market_inferred_from_query_phrase():
    assert infer_profile(query="a Japanese chipmaker").key == "JP"
    assert infer_profile(query="London-listed bank on the LSE").key == "GB"


def test_market_inferred_from_exchange_then_currency():
    assert infer_profile(exchange="NSE").key == "IN"
    assert infer_profile(currency="AUD").key == "AU"


def test_unknown_market_is_generic():
    p = infer_profile(query="a company somewhere")
    assert p.is_generic


def test_india_profile_leads_with_pledging():
    p = infer_profile(exchange="NSE")
    assert any("pledg" in g.lower() for g in p.governance_focus)


# ── planner ──────────────────────────────────────────────────────────────────
def test_snapshot_runs_minimal_lens_set():
    plan = plan_research(MandateRouter().route("x", depth="L0"))
    assert plan.product == "snapshot"
    assert plan.lenses == ["Technical", "Spike", "Valuation"]


def test_brief_runs_all_nine():
    plan = plan_research(MandateRouter().route("x", depth="L2"))
    assert plan.product == "tearsheet"
    assert len(plan.lenses) == 9


def test_deeper_tiers_degrade_with_note():
    plan = plan_research(MandateRouter().route("x", depth="L4"))
    assert plan.product == "tearsheet"
    assert plan.notes and "later build phase" in plan.notes[0]


# ── forensic gate + side calls ───────────────────────────────────────────────
def _lenses(quality_score, verdict_driver=80):
    return {
        "Quality": LensResult("Quality", score=quality_score),
        "Fundamental": LensResult("Fundamental", score=verdict_driver),
    }


def test_forensic_gate_vetoes_sell_side_buy():
    call = decide_call(Side.SELL_SIDE, Verdict.STRONG_BUY, _lenses(quality_score=25))
    assert call.gate == "fail"
    assert "forensic" in call.headline.lower()


def test_forensic_gate_vetoes_buy_side_own():
    call = decide_call(Side.BUY_SIDE, Verdict.BUY, _lenses(quality_score=20))
    assert call.gate == "fail"
    assert call.headline.startswith("Avoid")


def test_clean_gate_allows_buy():
    call = decide_call(Side.SELL_SIDE, Verdict.BUY, _lenses(quality_score=75))
    assert call.gate == "pass" and call.headline == "Buy"


def test_side_changes_the_call_vocabulary():
    sell = decide_call(Side.SELL_SIDE, Verdict.STRONG_BUY, _lenses(80))
    buy = decide_call(Side.BUY_SIDE, Verdict.STRONG_BUY, _lenses(80))
    assert sell.headline == "Buy"
    assert buy.headline.startswith("Own")


# ── end-to-end ───────────────────────────────────────────────────────────────
def test_end_to_end_sell_side_tearsheet():
    out = research("Hitachi Energy", side="sell-side", depth="L2", config=CFG)
    assert out.mandate.side is Side.SELL_SIDE
    assert out.mandate.market.key == "IN"          # refined from NSE listing
    assert len(out.lenses) == 9
    assert out.composite_score is not None
    assert "Rating:" in out.product
    assert "not investment advice" in out.product.lower()


def test_end_to_end_buy_side_framing_differs():
    out = research("Hitachi Energy", side="buy-side", depth="L2", config=CFG)
    assert "Position stance:" in out.product
    assert "PM view (buy-side)" in out.product


def test_end_to_end_snapshot_is_minimal():
    out = research("RELIANCE", depth="L0", config=CFG)
    assert out.plan.product == "snapshot"
    assert set(out.lenses) == {"Technical", "Spike", "Valuation"}
    assert "MANDATE" in out.product


def test_end_to_end_redflag_gate_fails():
    out = research("REDFLAG", side="buy-side", depth="L2", config=CFG)
    assert out.call.gate == "fail"                 # Quality lens below the floor
    assert "Avoid" in out.call.headline            # a red-flagged name is never Own
    assert "Forensic gate FAILED" in out.product


def test_market_profile_line_present():
    out = research("Hitachi Energy", depth="L1", config=CFG)
    assert "Market: India" in out.product
    assert "Triage:" in out.product
