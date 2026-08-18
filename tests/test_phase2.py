"""Tests for Phase 2 — the driver model + valuation triangulation (L3 deep dive).

Offline and deterministic. Exercises the forecast maths, the DCF, reverse-DCF
variant read, market-aware WACC, and the end-to-end L3 product.
"""
from __future__ import annotations

import pytest

from stockanalyser.config import Config
from stockanalyser.data import resolve_and_fetch
from stockanalyser.agent import (
    research, Side, Depth, MandateRouter,
    build_appraisal, derive_assumptions, build_projection,
)
from stockanalyser.agent.modeling import scenario
from stockanalyser.agent.markets import PROFILES
from stockanalyser.agent.planner import plan_research

CFG = Config(provider="offline", use_llm=False)


def _fundamentals(name):
    _, data, _ = resolve_and_fetch(name, CFG)
    return data.fundamentals


# ── forecast model ───────────────────────────────────────────────────────────
def test_derive_assumptions_from_history():
    a = derive_assumptions(_fundamentals("POWERINDIA"))
    assert a is not None
    assert -0.05 <= a.g0 <= 0.30
    assert 0.02 <= a.ebitda_margin <= 0.60
    assert 0.10 <= a.tax_rate <= 0.35


def test_projection_compounds_revenue_and_fades_growth():
    f = _fundamentals("POWERINDIA")
    a = derive_assumptions(f, horizon=8)
    proj = build_projection(f.latest.revenue, a)
    assert len(proj.years) == 8
    # revenue strictly grows while g0 > 0
    revs = [y.revenue for y in proj.years]
    assert revs == sorted(revs)
    # growth fades: last-year YoY <= first-year YoY when g0 > terminal
    if a.g0 > a.g_terminal:
        first_yoy = proj.years[0].revenue / f.latest.revenue - 1
        last_yoy = proj.years[-1].revenue / proj.years[-2].revenue - 1
        assert last_yoy <= first_yoy + 1e-9


def test_scenarios_order_bull_above_bear():
    f = _fundamentals("RELIANCE")
    a = derive_assumptions(f)
    bull = build_projection(f.latest.revenue, scenario(a, "bull"))
    bear = build_projection(f.latest.revenue, scenario(a, "bear"))
    assert bull.terminal_fcff > bear.terminal_fcff


# ── appraisal / DCF ──────────────────────────────────────────────────────────
def test_appraisal_produces_three_ordered_scenarios():
    ap = build_appraisal(_fundamentals("RELIANCE"), PROFILES["IN"], CFG)
    assert ap is not None
    names = [s.name for s in ap.scenarios]
    assert names == ["bear", "base", "bull"]
    fvs = [s.dcf.fair_value for s in ap.scenarios]
    assert all(v is not None for v in fvs)
    assert fvs[0] <= fvs[1] <= fvs[2]          # bear ≤ base ≤ bull


def test_weighted_target_within_range():
    ap = build_appraisal(_fundamentals("RELIANCE"), PROFILES["IN"], CFG)
    assert ap.fair_low <= ap.weighted_target <= ap.fair_high


def test_market_wacc_changes_valuation():
    f = _fundamentals("RELIANCE")
    ind = build_appraisal(f, PROFILES["IN"], CFG)     # 13% WACC
    jpn = build_appraisal(f, PROFILES["JP"], CFG)     # 7% WACC
    assert ind.wacc == pytest.approx(0.13)
    assert jpn.wacc == pytest.approx(0.07)
    # a lower discount rate => higher value
    assert jpn.scenarios[1].dcf.fair_value > ind.scenarios[1].dcf.fair_value


def test_reverse_dcf_variant_reads():
    ap = build_appraisal(_fundamentals("RELIANCE"), PROFILES["IN"], CFG)
    # either the price was bracketed (implied growth found + a variant string) or
    # an explicit note explains why it couldn't be
    if ap.implied_growth is not None:
        assert ap.variant is not None
    else:
        assert any("Reverse-DCF" in n for n in ap.notes)


def test_terminal_value_share_reported():
    ap = build_appraisal(_fundamentals("RELIANCE"), PROFILES["IN"], CFG)
    assert 0 <= ap.scenarios[1].dcf.terminal_pct <= 100


def test_no_fundamentals_returns_none():
    assert build_appraisal(None, PROFILES["IN"], CFG) is None


# ── planner + end-to-end ─────────────────────────────────────────────────────
def test_deep_dive_plan_uses_deepdive_product():
    plan = plan_research(MandateRouter().route("x", depth="L3"))
    assert plan.product == "deepdive"
    assert len(plan.lenses) == 9


def test_deep_dive_is_deepdive_not_initiation():
    # L3 is the deep dive; L4 is a distinct initiation product (see test_phase3)
    plan = plan_research(MandateRouter().route("x", depth="L3"))
    assert plan.product == "deepdive"


def test_end_to_end_deep_dive_sell_side():
    out = research("Hitachi Energy", side="sell-side", depth="L3", config=CFG)
    assert out.appraisal is not None
    assert "Valuation — driver model" in out.product
    assert "scenario-weighted target" in out.product
    assert "Target" in out.product and "%" in out.product


def test_end_to_end_deep_dive_buy_side_shows_skew():
    out = research("Hitachi Energy", side="buy-side", depth="L3", config=CFG)
    assert "Risk/reward:" in out.product
    assert "PM view (buy-side)" in out.product


def test_deep_dive_still_honours_forensic_gate():
    out = research("REDFLAG", side="buy-side", depth="L3", config=CFG)
    assert out.call.gate == "fail"
    assert out.appraisal is not None            # still models it, just won't endorse


def test_valuation_overlay_caps_a_richly_priced_name():
    # Hitachi Energy: strong lenses (composite ~Buy) but a P/E ~200 → deep DCF
    # downside. At L3 the target must cap the call — no "Own" at -95% to fair value.
    out = research("Hitachi Energy", side="buy-side", depth="L3", config=CFG)
    assert out.appraisal.target_upside_pct < -20
    assert not out.call.headline.startswith("Own")
    assert "valuation" in out.call.conviction.lower()


def test_valuation_overlay_absent_at_l2():
    # the L2 tearsheet has no appraisal, so the composite call stands unmodified
    out = research("Hitachi Energy", side="buy-side", depth="L2", config=CFG)
    assert out.appraisal is None
    assert out.call.headline.startswith("Own")
