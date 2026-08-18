"""Web app + news-parser tests (offline, no network)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="install the [web] extra to run web tests")
from fastapi.testclient import TestClient

from stockanalyser.web.app import app
from stockanalyser.data.news import parse_rss

client = TestClient(app)


def test_landing_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert "Type a company" in r.text
    assert "stockanalyser" in r.text


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_analyse_known_company_renders_dashboard():
    r = client.get("/analyse", params={"q": "Hitachi Energy", "provider": "offline"})
    assert r.status_code == 200
    assert "Composite score" in r.text
    assert "POWERINDIA" in r.text
    assert "{{" not in r.text                     # no unfilled templates


def test_analyse_unknown_is_synthetic_not_error():
    r = client.get("/analyse", params={"q": "ZZQQXX", "provider": "offline"})
    assert r.status_code == 200                    # resolves to synthetic price history


def test_api_analyse_json_shape():
    r = client.get("/api/analyse", params={"q": "REDFLAG", "provider": "offline"})
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] in ("Avoid", "Strong Avoid")
    assert set(["Technical", "Fundamental", "Valuation"]).issubset(data["lenses"].keys())


def test_api_suggest():
    r = client.get("/api/suggest", params={"q": "hitachi"})
    assert r.status_code == 200
    syms = [x["symbol"] for x in r.json()["results"]]
    assert "POWERINDIA" in syms


def test_framework_page():
    r = client.get("/framework")
    assert r.status_code == 200
    assert "nine lenses" in r.text.lower()


# ── research agent routes ─────────────────────────────────────────────────────
def test_landing_shows_research_agent():
    r = client.get("/")
    assert r.status_code == 200
    assert "research report" in r.text.lower()
    assert "/research" in r.text


def test_research_route_renders_initiation():
    r = client.get("/research", params={"q": "RELIANCE", "side": "sell-side",
                                        "depth": "L4", "provider": "offline"})
    assert r.status_code == 200
    assert "INITIATING COVERAGE" in r.text          # coverage-note banner (record off)
    assert "Analyst read" in r.text
    assert "12-mo target" in r.text
    assert "Estimates" in r.text and "Catalyst calendar" in r.text
    assert "{{" not in r.text                       # no unfilled templates
    assert "/research" in r.text                     # the mandate nav is present


def test_research_route_buy_side_l3():
    r = client.get("/research", params={"q": "Hitachi Energy", "side": "buy-side",
                                        "depth": "L3", "provider": "offline"})
    assert r.status_code == 200
    assert "Buy-side" in r.text
    assert "Valuation" in r.text


def test_research_bad_depth_is_400():
    r = client.get("/research", params={"q": "RELIANCE", "depth": "L9",
                                        "provider": "offline"})
    assert r.status_code == 400


def test_api_research_json_shape():
    r = client.get("/api/research", params={"q": "RELIANCE", "side": "sell-side",
                                            "depth": "L3", "provider": "offline"})
    assert r.status_code == 200
    d = r.json()
    assert d["mandate"]["side"] == "sell-side"
    assert d["mandate"]["market"] == "IN"
    assert d["appraisal"] is not None
    assert len(d["appraisal"]["scenarios"]) == 3
    assert d["call"]["headline"]
    assert "Fundamental" in d["lenses"]


def test_api_research_forensic_gate_in_json():
    r = client.get("/api/research", params={"q": "REDFLAG", "side": "buy-side",
                                            "depth": "L4", "provider": "offline"})
    assert r.status_code == 200
    assert r.json()["call"]["forensic_gate"] == "fail"


# ── news parser (pure, offline) ──────────────────────────────────────────────
SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Hitachi Energy wins large HVDC order</title>
    <link>https://example.com/a</link>
    <pubDate>Wed, 06 Aug 2025 09:30:00 GMT</pubDate>
    <description>&lt;p&gt;Order strengthens pipeline&lt;/p&gt;</description>
    <source url="https://ex.com">Example Wire</source>
  </item>
  <item>
    <title>Sector rerating lifts capital-goods stocks</title>
    <link>https://example.com/b</link>
    <pubDate>Tue, 05 Aug 2025 05:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def test_parse_rss_extracts_items():
    items = parse_rss(SAMPLE_RSS)
    assert len(items) == 2
    assert items[0].headline.startswith("Hitachi Energy")
    assert items[0].source == "Example Wire"
    assert "<p>" not in items[0].summary          # tags stripped
    assert str(items[0].date) == "2025-08-06"


def test_parse_rss_bad_xml_is_safe():
    assert parse_rss("not xml at all") == []
