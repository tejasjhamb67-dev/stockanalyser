"""Tests for the sector/industry browse universe — the pure FMP screener mapper,
market-cap ranking, offline fallback, and the /browse web routes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from stockanalyser.config import Config
from stockanalyser.data import universe as U
from stockanalyser.data.live import FMPProvider
from stockanalyser.web.app import app

client = TestClient(app)

_SCREEN = [
    {"symbol": "AAPL", "companyName": "Apple Inc.", "sector": "Technology",
     "industry": "Consumer Electronics", "exchangeShortName": "NASDAQ",
     "marketCap": 3_000_000_000_000, "price": 195.0, "currency": "USD"},
    {"symbol": "MSFT", "companyName": "Microsoft Corp.", "sector": "Technology",
     "industry": "Software—Infrastructure", "exchangeShortName": "NASDAQ",
     "marketCap": 3_100_000_000_000, "price": 420.0, "currency": "USD"},
    {"symbol": "TINY", "companyName": "Tiny Co", "sector": "Technology",
     "industry": "Software—Application", "exchangeShortName": "NASDAQ",
     "marketCap": 5_000_000, "price": 3.0, "currency": "USD"},
    {"symbol": "BAD"},                       # missing name/cap — must survive
    "not-a-dict",                            # junk — must be skipped
]


def test_parse_fmp_screener_maps_and_survives_junk():
    rows = U.parse_fmp_screener(_SCREEN)
    assert [r.symbol for r in rows] == ["AAPL", "MSFT", "TINY", "BAD"]
    aapl = rows[0]
    assert aapl.name == "Apple Inc." and aapl.industry == "Consumer Electronics"
    assert aapl.exchange == "NASDAQ" and aapl.market_cap == 3_000_000_000_000
    assert U.parse_fmp_screener(None) == [] and U.parse_fmp_screener({}) == []


def test_rank_sorts_by_market_cap_desc_and_limits():
    rows = U.parse_fmp_screener(_SCREEN)
    top2 = U._rank(rows, 2)
    assert [r.symbol for r in top2] == ["MSFT", "AAPL"]     # MSFT cap > AAPL cap


def test_industries_in_are_unique_and_sorted():
    rows = U.parse_fmp_screener(_SCREEN)
    inds = U.industries_in(rows)
    assert inds == sorted(inds)
    assert "Consumer Electronics" in inds


def test_canonical_sector_case_insensitive():
    assert U.canonical_sector("technology") == "Technology"
    assert U.canonical_sector("FINANCIAL SERVICES") == "Financial Services"
    assert U.canonical_sector("Nonsense") is None


def test_build_universe_uses_fmp_when_screen_returns(monkeypatch):
    monkeypatch.setattr(FMPProvider, "available", lambda self: True)
    monkeypatch.setattr(FMPProvider, "screener_raw", lambda self, **kw: _SCREEN)
    rows, industries, source = U.build_universe(sector="Technology", limit=50,
                                                config=Config(provider="auto"))
    assert source == "fmp"
    assert rows[0].symbol == "MSFT"                          # ranked by cap
    assert industries == sorted(industries)


def test_build_universe_falls_back_to_offline_when_no_key():
    # provider forced offline → never touches the network, returns sample names
    rows, industries, source = U.build_universe(sector="Energy", limit=50,
                                                config=Config(provider="offline"))
    assert source == "offline-sample"
    # fuzzy match: "Energy" catches the sample tagged "Energy / Conglomerate"
    assert rows and all("energy" in (r.sector or "").lower() for r in rows)


def test_browse_index_lists_all_sectors():
    r = client.get("/browse")
    assert r.status_code == 200
    body = r.text
    for s in U.SECTORS:
        assert s in body
    assert "Browse by sector" in body


def test_browse_sector_page_renders_offline(monkeypatch):
    # force offline so the test is network-free and deterministic
    monkeypatch.setattr(FMPProvider, "available", lambda self: False)
    r = client.get("/browse", params={"sector": "energy"})
    assert r.status_code == 200
    assert "Energy" in r.text and "table" in r.text.lower()


def test_browse_unknown_sector_is_404():
    r = client.get("/browse", params={"sector": "Nonsense"})
    assert r.status_code == 404


def test_api_universe_json_shape(monkeypatch):
    monkeypatch.setattr(FMPProvider, "available", lambda self: True)
    monkeypatch.setattr(FMPProvider, "screener_raw", lambda self, **kw: _SCREEN)
    r = client.get("/api/universe", params={"sector": "Technology"})
    assert r.status_code == 200
    data = r.json()
    assert data["sector"] == "Technology" and data["source"] == "fmp"
    assert data["results"][0]["symbol"] == "MSFT"
