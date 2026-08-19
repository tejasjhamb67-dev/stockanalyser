"""Tests for the FMP data provider — the reliable server-side source that makes
'any stock, live' work. Pure parsers + build_chain wiring + a full end-to-end run
through a faked FMP HTTP layer (no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stockanalyser.config import Config
from stockanalyser.data.live import (
    FMPProvider, parse_fmp_prices, parse_fmp_fundamentals, parse_fmp_street,
    company_from_fmp_profile,
)
from stockanalyser.data.registry import build_chain

CFG = Config(provider="offline", use_llm=False)


# ── synthetic FMP payloads ───────────────────────────────────────────────────
def _income():
    return [
        {"date": "2024-09-30", "calendarYear": "2024", "period": "FY", "revenue": 390000,
         "ebitda": 130000, "operatingIncome": 115000, "depreciationAndAmortization": 11000,
         "interestExpense": 3000, "incomeBeforeTax": 112000, "incomeTaxExpense": 17000,
         "netIncome": 95000, "weightedAverageShsOut": 15500},
        {"date": "2023-09-30", "calendarYear": "2023", "period": "FY", "revenue": 383000,
         "ebitda": 125000, "operatingIncome": 109000, "depreciationAndAmortization": 11000,
         "interestExpense": 3900, "incomeBeforeTax": 108000, "incomeTaxExpense": 16700,
         "netIncome": 97000, "weightedAverageShsOut": 15800},
    ]


def _balance():
    return [
        {"date": "2024-09-30", "totalAssets": 350000, "totalCurrentAssets": 140000,
         "inventory": 6000, "netReceivables": 60000, "cashAndCashEquivalents": 30000,
         "totalCurrentLiabilities": 130000, "totalDebt": 110000,
         "totalStockholdersEquity": 60000, "accountPayables": 60000},
        {"date": "2023-09-30", "totalAssets": 352000, "totalCurrentAssets": 143000,
         "inventory": 6300, "netReceivables": 61000, "cashAndCashEquivalents": 29000,
         "totalCurrentLiabilities": 134000, "totalDebt": 111000,
         "totalStockholdersEquity": 62000, "accountPayables": 62000},
    ]


def _cashflow():
    return [
        {"date": "2024-09-30", "operatingCashFlow": 118000, "capitalExpenditure": -10000,
         "depreciationAndAmortization": 11000},
        {"date": "2023-09-30", "operatingCashFlow": 110000, "capitalExpenditure": -11000,
         "depreciationAndAmortization": 11000},
    ]


def _profile():
    return {"symbol": "AAPL", "companyName": "Apple Inc.", "price": 230.0, "currency": "USD",
            "exchangeShortName": "NASDAQ", "sector": "Technology",
            "industry": "Consumer Electronics", "mktCap": 3.5e12,
            "description": "Apple designs consumer electronics.", "lastDiv": 0.99,
            "sharesOutstanding": 15300}


def _history():
    dates = pd.bdate_range("2023-01-02", periods=260)
    close = 150 + np.linspace(0, 60, 260)
    return {"symbol": "AAPL", "historical": [
        {"date": d.strftime("%Y-%m-%d"), "open": c * 0.99, "high": c * 1.01,
         "low": c * 0.98, "close": round(c, 2), "volume": 1_000_000}
        for d, c in zip(dates, close)]}


# ── pure parsers ─────────────────────────────────────────────────────────────
def test_parse_fmp_fundamentals_full_lineitems():
    f = parse_fmp_fundamentals("AAPL", _income(), _balance(), _cashflow(), _profile())
    assert f is not None and len(f.statements) == 2
    assert [s.period for s in f.statements] == ["FY2023", "FY2024"]   # oldest→newest
    latest = f.statements[-1]
    assert latest.revenue == 390000 and latest.ebitda == 130000 and latest.net_income == 95000
    assert latest.capex == 10000 and latest.receivables == 60000 and latest.payables == 60000
    assert latest.cfo == 118000 and latest.equity == 60000
    assert latest.dividend_per_share == 0.99
    assert f.price == 230.0 and f.shares_outstanding == 15300


def test_parse_fmp_fundamentals_derives_ebitda():
    inc = _income()
    for row in inc:
        row.pop("ebitda")
    f = parse_fmp_fundamentals("AAPL", inc, _balance(), _cashflow(), _profile())
    assert f.statements[-1].ebitda == pytest.approx(115000 + 11000)   # ebit + D&A


def test_parse_fmp_prices_frame():
    frame = parse_fmp_prices(_history())
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.is_monotonic_increasing and len(frame) == 260
    assert parse_fmp_prices({"historical": []}) is None
    assert parse_fmp_prices(None) is None


def test_company_from_fmp_profile():
    c = company_from_fmp_profile(_profile())
    assert c.symbol == "AAPL" and c.exchange == "NASDAQ" and c.currency == "USD"
    assert c.sector == "Technology" and c.market_cap == 3.5e12


def test_parse_fmp_street():
    sc = parse_fmp_street("AAPL", [{"targetConsensus": 250, "targetHigh": 300, "targetLow": 200}],
                          [{"ratingRecommendation": "Buy"}])
    assert sc is not None and sc.price_target_mean == 250 and sc.recommendation_key == "buy"
    assert parse_fmp_street("AAPL", [], []) is None


# ── availability + chain wiring ──────────────────────────────────────────────
def test_available_reflects_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    assert FMPProvider().available() is False
    monkeypatch.setenv("FMP_API_KEY", "x")
    assert FMPProvider().available() is True


def test_chain_prefers_fmp_when_keyed(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "x")
    chain = build_chain(Config(provider="auto"))
    assert chain[0].name == "fmp"                    # keyed FMP leads the auto chain
    assert chain[-1].name == "offline-sample"


def test_chain_explicit_fmp(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "x")
    chain = build_chain(Config(provider="fmp"))
    assert [p.name for p in chain] == ["fmp", "offline-sample"]


# ── end-to-end through a faked FMP HTTP layer ────────────────────────────────
@pytest.fixture
def fake_fmp(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "testkey")

    def fake_get(self, path, **params):
        if "/profile/" in path:
            return [_profile()]
        if "/search" in path:
            return [{"symbol": "AAPL", "name": "Apple Inc."}]
        if "/historical-price-full/" in path:
            return _history()
        if "/income-statement/" in path:
            return _income()
        if "/balance-sheet-statement/" in path:
            return _balance()
        if "/cash-flow-statement/" in path:
            return _cashflow()
        if "/price-target-consensus" in path:
            return [{"targetConsensus": 250, "targetHigh": 300, "targetLow": 200}]
        if "/rating/" in path:
            return [{"ratingRecommendation": "Buy"}]
        return []

    monkeypatch.setattr(FMPProvider, "_get", fake_get)
    yield


def test_agent_runs_end_to_end_on_fmp(fake_fmp):
    from stockanalyser.agent import research
    out = research("AAPL", depth="L3", config=Config(provider="fmp", use_llm=False))
    assert out.data_sources["fundamentals"] == "fmp"
    assert out.data_sources["prices"] == "fmp"
    assert out.company.name == "Apple Inc."
    assert out.mandate.market.key == "US"            # inferred from the NASDAQ listing
    assert out.appraisal is not None
    assert out.appraisal.wacc == pytest.approx(0.09)


def test_fmp_consensus_flows_to_agent(fake_fmp):
    from stockanalyser.agent import research
    out = research("AAPL", side="sell-side", depth="L4", config=Config(provider="fmp", use_llm=False),
                   coverage_store=None, record_coverage=False)
    assert out.consensus is not None and out.consensus.is_street
    assert out.consensus.street_target == 250
