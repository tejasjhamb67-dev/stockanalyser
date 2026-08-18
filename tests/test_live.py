"""Tests for the live yfinance adapter — the pure mappers plus a full end-to-end
run of the agent through a fake yfinance module (no network).

Real Yahoo fetches can't run in CI/sandboxes with restricted egress; these lock
down the yfinance→models transformation and the provider/agent wiring instead.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd
import pytest

from stockanalyser.config import Config
from stockanalyser.data.live import (
    YFinanceProvider, parse_fundamentals, company_from_info, price_frame,
)
from stockanalyser.models import Company


# ── synthetic yfinance-shaped fixtures ───────────────────────────────────────
def _cols():
    # yfinance orders statement columns newest → oldest
    return [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"),
            pd.Timestamp("2022-12-31"), pd.Timestamp("2021-12-31")]


def _financials():
    c = _cols()
    return pd.DataFrame({
        c[0]: {"Total Revenue": 1000, "EBITDA": 250, "EBIT": 200,
               "Reconciled Depreciation": 50, "Interest Expense": 10,
               "Pretax Income": 190, "Tax Provision": 48, "Net Income": 142,
               "Diluted Average Shares": 100},
        c[1]: {"Total Revenue": 900, "EBITDA": 220, "EBIT": 175,
               "Reconciled Depreciation": 45, "Interest Expense": 10,
               "Pretax Income": 165, "Tax Provision": 41, "Net Income": 124,
               "Diluted Average Shares": 100},
        c[2]: {"Total Revenue": 820, "EBITDA": 200, "EBIT": 158,
               "Reconciled Depreciation": 42, "Interest Expense": 9,
               "Pretax Income": 149, "Tax Provision": 37, "Net Income": 112,
               "Diluted Average Shares": 100},
        c[3]: {"Total Revenue": 750, "EBITDA": 180, "EBIT": 140,
               "Reconciled Depreciation": 40, "Interest Expense": 8,
               "Pretax Income": 132, "Tax Provision": 33, "Net Income": 99,
               "Diluted Average Shares": 100},
    })


def _balance_sheet():
    c = _cols()
    def col(a, l, inv, rec, cash, debt, eq, pay):
        return {"Total Assets": a, "Current Assets": 500, "Current Liabilities": l,
                "Inventory": inv, "Accounts Receivable": rec,
                "Cash And Cash Equivalents": cash, "Total Debt": debt,
                "Stockholders Equity": eq, "Accounts Payable": pay,
                "Ordinary Shares Number": 100}
    return pd.DataFrame({
        c[0]: col(1200, 300, 120, 150, 200, 300, 700, 110),
        c[1]: col(1100, 280, 110, 140, 180, 320, 650, 100),
        c[2]: col(1000, 260, 100, 130, 160, 310, 600, 95),
        c[3]: col(900, 240, 95, 120, 150, 300, 540, 90),
    })


def _cashflow():
    c = _cols()
    def col(cfo, capex, da):
        return {"Operating Cash Flow": cfo, "Capital Expenditure": capex,
                "Depreciation And Amortization": da}
    return pd.DataFrame({
        c[0]: col(210, -90, 50), c[1]: col(185, -85, 45),
        c[2]: col(168, -80, 42), c[3]: col(150, -75, 40),
    })


def _info():
    return {"longName": "Acme Corp", "sector": "Technology", "industry": "Software",
            "currency": "USD", "regularMarketPrice": 55.0, "sharesOutstanding": 100,
            "marketCap": 5500, "trailingAnnualDividendRate": 1.2,
            "longBusinessSummary": "Acme builds things."}


def _history():
    idx = pd.date_range("2023-01-02", periods=500, freq="B", tz="America/New_York")
    close = pd.Series(50 + np.linspace(0, 10, 500), index=idx)
    return pd.DataFrame({"Open": close * 0.99, "High": close * 1.01,
                         "Low": close * 0.98, "Close": close,
                         "Volume": 1_000_000}, index=idx)


# ── pure mapper unit tests ───────────────────────────────────────────────────
def test_parse_fundamentals_full_lineitems():
    f = parse_fundamentals("ACME", _financials(), _balance_sheet(), _cashflow(), _info())
    assert f is not None and len(f.statements) == 4
    assert [s.period for s in f.statements] == ["FY2021", "FY2022", "FY2023", "FY2024"]
    latest = f.statements[-1]
    assert latest.revenue == 1000 and latest.ebitda == 250 and latest.net_income == 142
    assert latest.capex == 90            # sign normalised to positive
    assert latest.receivables == 150 and latest.payables == 110 and latest.inventory == 120
    assert latest.dividend_per_share == 1.2
    assert f.price == 55.0 and f.shares_outstanding == 100


def test_parse_fundamentals_derives_ebitda_when_missing():
    fin = _financials().drop(index="EBITDA")     # force EBITDA = EBIT + Depreciation
    f = parse_fundamentals("ACME", fin, _balance_sheet(), _cashflow(), _info())
    assert f.statements[-1].ebitda == pytest.approx(200 + 50)


def test_parse_fundamentals_none_without_income():
    assert parse_fundamentals("X", None, _balance_sheet(), _cashflow(), _info()) is None


def test_company_from_info_maps_market_fields():
    c = company_from_info("ACME", "NASDAQ", _info())
    assert c.name == "Acme Corp" and c.currency == "USD" and c.exchange == "NASDAQ"
    assert c.sector == "Technology"


def test_price_frame_tz_naive_ohlcv():
    frame = price_frame(_history())
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.tz is None
    assert price_frame(None) is None


# ── resolution / symbol mapping ──────────────────────────────────────────────
def test_candidates_detect_global_suffixes():
    p = YFinanceProvider()
    assert p._candidates("BP.L") == [("BP.L", "LSE", "BP")]
    assert p._candidates("7203.T") == [("7203.T", "TSE", "7203")]
    bare = p._candidates("RELIANCE")
    assert bare[0][1] == "NASDAQ" and ("RELIANCE.NS", "NSE", "RELIANCE") in bare


def test_yf_symbol_reconstruction():
    p = YFinanceProvider()
    assert p._yf_symbol(Company("BP", "BP", exchange="LSE")) == "BP.L"
    assert p._yf_symbol(Company("AAPL", "Apple", exchange="NASDAQ")) == "AAPL"
    assert p._yf_symbol(Company("RELIANCE", "RIL", exchange="NSE")) == "RELIANCE.NS"


# ── end-to-end through a fake yfinance module ────────────────────────────────
class _FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol
    def get_info(self):
        return _info()
    def history(self, period=None, interval=None):
        return _history()
    news = []
    @property
    def financials(self):
        return _financials()
    @property
    def balance_sheet(self):
        return _balance_sheet()
    @property
    def cashflow(self):
        return _cashflow()


@pytest.fixture
def fake_yf(monkeypatch):
    mod = types.ModuleType("yfinance")
    mod.Ticker = _FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    yield


def test_agent_runs_end_to_end_on_yfinance(fake_yf):
    from stockanalyser.agent import research
    cfg = Config(provider="yfinance", use_llm=False)
    out = research("ACME", depth="L3", config=cfg)
    # data actually came from the (fake) live provider, framed for its market
    assert out.data_sources["fundamentals"] == "yfinance"
    assert out.mandate.market.key == "US"          # inferred from NASDAQ listing
    assert out.appraisal is not None
    assert out.appraisal.wacc == pytest.approx(0.09)   # US WACC anchor
    assert "United States" in out.product
    assert out.company.name == "Acme Corp"
