"""Unit + integration tests for the analysis engine (offline, deterministic)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockanalyser import analyse
from stockanalyser.config import Config, SpikeConfig
from stockanalyser.data import OfflineProvider, resolve_and_fetch
from stockanalyser.analysis import indicators as ind
from stockanalyser.analysis import fundamental, quality, spikes, scoring
from stockanalyser.models import Verdict


CFG = Config(provider="offline", use_llm=False)


# ── indicators ───────────────────────────────────────────────────────────────
def _series(vals):
    idx = pd.bdate_range("2023-01-01", periods=len(vals))
    return pd.Series(vals, index=idx)


def test_rsi_bounds():
    up = _series(list(np.linspace(100, 200, 60)))
    down = _series(list(np.linspace(200, 100, 60)))
    assert ind.rsi(up).iloc[-1] > 70          # relentless up → overbought
    assert ind.rsi(down).iloc[-1] < 30        # relentless down → oversold


def test_sma_matches_mean():
    s = _series(list(range(1, 51)))
    assert ind.sma(s, 10).iloc[-1] == pytest.approx(np.mean(range(41, 51)))


def test_macd_cross_sign():
    s = _series(list(np.linspace(100, 150, 80)))
    macd_line, signal, hist = ind.macd(s)
    assert macd_line.iloc[-1] > 0             # uptrend → positive MACD


# ── resolver ─────────────────────────────────────────────────────────────────
def test_name_resolves_to_ticker():
    prov = OfflineProvider()
    c = prov.resolve("hitachi energy")
    assert c is not None and c.symbol == "POWERINDIA"


def test_unknown_symbol_is_synthetic():
    prov = OfflineProvider()
    c = prov.resolve("ZZTOP")
    assert c is not None and c.sector is None


# ── spike detection + attribution ────────────────────────────────────────────
def test_spikes_detected_and_attributed():
    _, data, _ = resolve_and_fetch("POWERINDIA", CFG)
    res = spikes.analyse(data, SpikeConfig())
    sp = res.data["spikes"]
    assert len(sp) >= 3
    # at least one spike attributed to a results/corporate action with high confidence
    assert any(s["primary_cause"].startswith("Corporate action") and s["confidence"] >= 0.6 for s in sp)
    # alpha decomposition present
    assert all("alpha_pct" in s for s in sp)


def test_sector_move_has_low_alpha_attribution():
    _, data, _ = resolve_and_fetch("POWERINDIA", CFG)
    res = spikes.analyse(data, SpikeConfig())
    causes = {s["primary_cause"] for s in res.data["spikes"]}
    # the engineered sector event should surface a sector/market attribution somewhere
    assert any("Sector" in c for c in causes)


# ── fundamentals ─────────────────────────────────────────────────────────────
def test_fundamental_ratios_reasonable():
    _, data, _ = resolve_and_fetch("POWERINDIA", CFG)
    res = fundamental.analyse(data)
    r = res.data["ratios"]
    assert r["roe"] is not None and 5 < r["roe"] < 30
    assert r["debt_equity"] is not None and r["debt_equity"] < 1     # low-debt company
    assert res.score is not None


def test_dupont_reconciles():
    _, data, _ = resolve_and_fetch("POWERINDIA", CFG)
    du = fundamental.analyse(data).data["dupont"]
    recomposed = du["net_margin"]/100 * du["asset_turnover"] * du["equity_multiplier"]
    assert recomposed * 100 == pytest.approx(du["roe"], rel=0.05)


# ── forensic / quality ───────────────────────────────────────────────────────
def test_redflag_forensics_catch_manipulation():
    _, data, _ = resolve_and_fetch("REDFLAG", CFG)
    res = quality.analyse(data)
    # negative cumulative CFO/PAT and a Beneish flag → low score
    assert res.score < 40
    assert res.data["cfo_to_pat_cumulative"] < 0.8


def test_powerindia_forensics_clean():
    _, data, _ = resolve_and_fetch("POWERINDIA", CFG)
    res = quality.analyse(data)
    assert res.score > 70
    assert res.data["altman_z"] > 3          # safe zone


# ── scoring + verdict ────────────────────────────────────────────────────────
def test_composite_ignores_missing_lenses():
    from stockanalyser.models import LensResult
    lenses = {
        "Fundamental": LensResult("Fundamental", score=80),
        "Valuation": LensResult("Valuation", score=None),   # missing
    }
    comp = scoring.composite(lenses, CFG.weights)
    assert comp == 80                                        # not dragged down by None


def test_verdict_bands():
    assert scoring.verdict_from(90) == Verdict.STRONG_BUY
    assert scoring.verdict_from(20) == Verdict.STRONG_AVOID
    assert scoring.verdict_from(None) == Verdict.INSUFFICIENT


# ── end-to-end ───────────────────────────────────────────────────────────────
def test_end_to_end_quality_name_is_buy():
    r = analyse("Hitachi Energy", CFG)
    assert r.verdict in (Verdict.BUY, Verdict.STRONG_BUY, Verdict.HOLD)
    assert r.composite_score is not None
    assert r.narrative and "not investment advice" in r.narrative.lower()
    assert len(r.lenses) == 9


def test_end_to_end_trap_is_avoided():
    r = analyse("REDFLAG", CFG)
    assert r.verdict in (Verdict.AVOID, Verdict.STRONG_AVOID)
    assert any("pledge" in b.lower() or "cash" in b.lower() for b in r.bear_thesis)


def test_dashboard_renders_html():
    from stockanalyser.report import render_dashboard
    r = analyse("RELIANCE", CFG)
    html = render_dashboard(r)
    assert html.startswith("<!doctype html>")
    assert "{{" not in html                                 # no unfilled templates
    assert "Composite score" in html
