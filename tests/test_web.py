"""Web app + news-parser tests (offline, no network)."""
from __future__ import annotations

import pytest
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
