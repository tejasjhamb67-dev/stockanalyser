"""Tests for the agent's HTML dashboard renderer — valid, self-contained, and
tier-aware (valuation at L3+, estimates/catalysts at L4, coverage at L5)."""
from __future__ import annotations

import pytest

from stockanalyser.config import Config
from stockanalyser.agent import research, render_html

CFG = Config(provider="offline", use_llm=False)


def _html(name, depth, **kw):
    return render_html(research(name, depth=depth, config=CFG, **kw))


def test_html_is_self_contained_document():
    html = _html("RELIANCE", "L2")
    assert html.startswith("<!doctype html>")
    for slot in ("{{TITLE}}", "{{STYLE}}", "{{BODY}}"):   # no unfilled template slots
        assert slot not in html
    assert "http://" not in html and "https://" not in html   # no external assets
    assert "not investment advice" in html.lower()


def test_html_hero_shows_company_and_mandate():
    html = _html("RELIANCE", "L2", side="buy-side")
    assert "Reliance Industries Ltd" in html
    assert "Buy-side" in html and "India" in html
    assert "Composite score" in html


def test_l3_html_has_valuation_and_scenarios():
    html = _html("RELIANCE", "L3")
    assert "Valuation — driver model" in html
    for scn in ("bear", "base", "bull"):
        assert scn in html
    assert "Scenario-weighted target" in html


def test_l4_html_has_estimates_and_catalysts(tmp_path):
    html = _html("RELIANCE", "L4", coverage_store=str(tmp_path))
    assert "Estimates" in html and "consensus" in html
    assert "Catalyst calendar" in html
    assert "INITIATING COVERAGE" in html


def test_l5_html_has_living_coverage(tmp_path):
    html = _html("RELIANCE", "L5", coverage_store=str(tmp_path))
    assert "Living coverage" in html
    assert "Results review" in html


def test_html_escapes_and_flags_forensic_gate(tmp_path):
    html = _html("REDFLAG", "L4", side="buy-side", coverage_store=str(tmp_path))
    assert "Forensic gate FAILED" in html


def test_l0_html_has_no_valuation_block():
    html = _html("RELIANCE", "L0")
    assert "Valuation — driver model" not in html      # no appraisal at L0
    assert "Lens scorecard" in html
