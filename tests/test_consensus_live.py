"""Tests for real Street consensus via a live provider (offline, fake yfinance).

Covers the pure parser (yfinance analyst shapes -> StreetConsensus), the agent's
Street-aware ConsensusView, and a full L4 run through a fake yfinance module that
supplies both fundamentals and consensus.
"""
from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from stockanalyser.config import Config
from stockanalyser.data import resolve_and_fetch
from stockanalyser.data.live import parse_consensus
from stockanalyser.models import StreetConsensus
from stockanalyser.agent import build_appraisal, build_consensus, research, research_to_dict
from stockanalyser.agent.markets import PROFILES

# reuse the yfinance-shaped fundamentals fixtures from the live-adapter tests
from test_live import _financials, _balance_sheet, _cashflow, _info, _history

CFG = Config(provider="offline", use_llm=False)


def _analyst_info():
    return {**_info(), "targetMeanPrice": 62.0, "targetHighPrice": 75.0,
            "targetLowPrice": 48.0, "numberOfAnalystOpinions": 22,
            "recommendationKey": "buy", "recommendationMean": 2.1}


def _earnings_est():
    return pd.DataFrame(
        {"avg": [1.2, 1.3, 5.4, 6.1], "low": [1.0, 1.1, 5.0, 5.5],
         "high": [1.4, 1.5, 5.8, 6.6], "numberOfAnalysts": [18, 16, 20, 17],
         "growth": [0.1, 0.12, 0.13, 0.13]},
        index=["0q", "+1q", "0y", "+1y"])


def _revenue_est():
    return pd.DataFrame(
        {"avg": [260, 285, 1020, 1150], "low": [250, 275, 990, 1100],
         "high": [270, 295, 1050, 1200], "numberOfAnalysts": [15, 14, 19, 16]},
        index=["0q", "+1q", "0y", "+1y"])


def _recommendations():
    return pd.DataFrame([
        {"period": "0m", "strongBuy": 8, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
        {"period": "-1m", "strongBuy": 7, "buy": 10, "hold": 4, "sell": 1, "strongSell": 0},
    ])


# ── pure parser ──────────────────────────────────────────────────────────────
def test_parse_consensus_from_info_and_frames():
    sc = parse_consensus("ACME", _analyst_info(), earnings_est=_earnings_est(),
                         revenue_est=_revenue_est(), recommendations=_recommendations())
    assert sc is not None and sc.has_view
    assert sc.price_target_mean == 62.0 and sc.price_target_high == 75.0
    assert sc.num_analysts == 22 and sc.recommendation_key == "buy"
    assert sc.rec_counts["strongBuy"] == 8 and sc.rec_counts["hold"] == 3
    # forward EPS + revenue for current & next FY
    eps = [e for e in sc.estimates if e.metric == "EPS"]
    rev = [e for e in sc.estimates if e.metric == "Revenue"]
    assert {e.period for e in eps} == {"curr FY", "next FY"}
    assert next(e.mean for e in eps if e.period == "next FY") == 6.1
    assert next(e.mean for e in rev if e.period == "next FY") == 1150


def test_parse_consensus_price_target_falls_back_to_dict():
    info = {k: v for k, v in _info().items()}          # no target* fields
    sc = parse_consensus("ACME", info, price_targets={"mean": 70, "high": 80, "low": 60})
    assert sc.price_target_mean == 70.0


def test_parse_consensus_none_when_no_coverage():
    assert parse_consensus("ACME", {"currency": "USD"}) is None


# ── agent ConsensusView prefers Street ───────────────────────────────────────
def test_build_consensus_uses_street_when_present():
    _, data, _ = resolve_and_fetch("RELIANCE", CFG)
    ap = build_appraisal(data.fundamentals, PROFILES["IN"], CFG)
    street = StreetConsensus(symbol="RELIANCE", price_target_mean=3600.0,
                             price_target_low=2900.0, price_target_high=4200.0,
                             num_analysts=34, recommendation_key="buy")
    cv = build_consensus(ap, data.fundamentals, street=street)
    assert cv.is_street and "34 analysts" in cv.source
    assert cv.street_target == 3600.0 and cv.street_rating == "buy"
    assert cv.target_gap_pct is not None
    # our ~2075 target is well below the 3600 Street mean -> "below the Street"
    assert "below the street" in (cv.variant or "").lower()


def test_build_consensus_falls_back_without_street():
    _, data, _ = resolve_and_fetch("RELIANCE", CFG)
    ap = build_appraisal(data.fundamentals, PROFILES["IN"], CFG)
    cv = build_consensus(ap, data.fundamentals, street=None)
    assert not cv.is_street
    assert "price-implied" in cv.source or "model only" in cv.source


# ── end-to-end through a fake yfinance with analyst data ──────────────────────
class _FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
    def get_info(self):
        return _analyst_info()
    def history(self, period=None, interval=None):
        return _history()
    news = []
    analyst_price_targets = {"mean": 62.0, "high": 75.0, "low": 48.0}
    @property
    def financials(self):
        return _financials()
    @property
    def balance_sheet(self):
        return _balance_sheet()
    @property
    def cashflow(self):
        return _cashflow()
    @property
    def earnings_estimate(self):
        return _earnings_est()
    @property
    def revenue_estimate(self):
        return _revenue_est()
    @property
    def recommendations(self):
        return _recommendations()


@pytest.fixture
def fake_yf(monkeypatch):
    mod = types.ModuleType("yfinance")
    mod.Ticker = _FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    yield


def test_agent_l4_uses_street_consensus(fake_yf, tmp_path):
    cfg = Config(provider="yfinance", use_llm=False)
    out = research("ACME", side="sell-side", depth="L4", config=cfg,
                   coverage_store=str(tmp_path))
    assert out.consensus is not None and out.consensus.is_street
    assert out.consensus.street_target == 62.0
    assert "Street consensus (22 analysts)" in out.product
    assert "Street: mean target" in out.product

    d = research_to_dict(out)
    assert d["estimates"]["is_street"] is True
    assert d["estimates"]["street_target"] == 62.0
    assert d["estimates"]["street_rating"] == "buy"


def test_agent_l4_html_shows_street(fake_yf, tmp_path):
    from stockanalyser.agent import render_html
    cfg = Config(provider="yfinance", use_llm=False)
    out = research("ACME", depth="L4", config=cfg, coverage_store=str(tmp_path))
    html = render_html(out)
    assert "Street: mean target" in html
    assert "Street estimate" in html
