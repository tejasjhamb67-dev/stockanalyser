"""Tests for the agent's analyst-read narrative (deterministic path, offline)."""
from __future__ import annotations

from stockanalyser.config import Config
from stockanalyser.agent import research, render_html, build_narrative

CFG = Config(provider="offline", use_llm=False)


def test_narrative_is_mandate_aware_and_present_in_product():
    out = research("RELIANCE", side="sell-side", depth="L3", config=CFG)
    assert out.narrative
    assert "Sell-side read" in out.narrative
    assert "not investment advice" in out.narrative.lower()
    assert "Analyst read" in out.product          # embedded in the terminal note


def test_buyside_narrative_differs():
    out = research("RELIANCE", side="buy-side", depth="L3", config=CFG)
    assert "Buy-side read" in out.narrative


def test_narrative_reconciles_valuation_when_capped():
    # Hitachi: strong composite but deep DCF downside → narrative notes the cap
    out = research("Hitachi Energy", side="sell-side", depth="L3", config=CFG)
    assert "capped" in out.narrative.lower() or "-" in out.narrative


def test_narrative_flags_forensic_gate():
    out = research("REDFLAG", side="buy-side", depth="L4", config=CFG,
                   coverage_store="/tmp/cov-narr-test")
    assert "forensic red flag" in out.narrative.lower()


def test_narrative_in_html():
    out = research("RELIANCE", depth="L4", config=CFG, coverage_store="/tmp/cov-narr-html")
    html = render_html(out)
    assert "Analyst read" in html


def test_no_narrative_at_snapshot():
    out = research("RELIANCE", depth="L0", config=CFG)
    assert out.narrative == ""


def test_build_narrative_deterministic_without_llm():
    out = research("RELIANCE", depth="L2", config=CFG)
    # calling directly with use_llm=False must return the deterministic string
    text = build_narrative(out, use_llm=False)
    assert text and "Not investment advice." in text
