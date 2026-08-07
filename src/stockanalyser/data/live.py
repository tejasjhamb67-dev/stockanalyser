"""Live data adapters. Real implementations, imported lazily so the package
installs and runs with no network and no optional dependencies.

Each adapter reports `available()` honestly (dependency present?) and raises or
returns None on network failure, letting the registry fall back to the next
provider — the engine never crashes because a feed is down.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..models import Company, FinancialStatement, Fundamentals, PriceHistory
from .base import DataProvider, ProviderUnavailable


class YFinanceProvider(DataProvider):
    """Prices + basic fundamentals via the `yfinance` package.

    Symbol convention: NSE tickers become `<SYMBOL>.NS`, BSE `<SYMBOL>.BO`.
    """
    name = "yfinance"

    def _yf(self):
        try:
            import yfinance as yf  # noqa
            return yf
        except Exception as exc:  # pragma: no cover - depends on env
            raise ProviderUnavailable("yfinance not installed (pip install stockanalyser[live])") from exc

    def available(self) -> bool:
        try:
            self._yf()
            return True
        except ProviderUnavailable:
            return False

    def _yf_symbol(self, company: Company) -> str:
        suffix = {"NSE": ".NS", "BSE": ".BO"}.get(company.exchange, "")
        return f"{company.symbol}{suffix}"

    def resolve(self, query: str) -> Optional[Company]:
        yf = self._yf()
        raw = query.strip().upper().replace(" ", "")
        for sym, exch in ((f"{raw}.NS", "NSE"), (f"{raw}.BO", "BSE"), (raw, "NASDAQ")):
            try:
                t = yf.Ticker(sym)
                info = t.get_info()
                if info and info.get("regularMarketPrice") is not None:
                    return Company(
                        symbol=raw, name=info.get("longName", raw), exchange=exch,
                        sector=info.get("sector"), industry=info.get("industry"),
                        currency=info.get("currency", "INR"),
                        market_cap=info.get("marketCap"),
                        description=info.get("longBusinessSummary"),
                    )
            except Exception:
                continue
        return None

    def prices(self, company: Company) -> Optional[PriceHistory]:
        yf = self._yf()
        hist = yf.Ticker(self._yf_symbol(company)).history(period="2y", interval="1d")
        if hist is None or hist.empty:
            return None
        frame = hist.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
        return PriceHistory(symbol=company.symbol, frame=frame, source=self.name)

    def benchmarks(self, company: Company) -> dict[str, PriceHistory]:
        yf = self._yf()
        out: dict[str, PriceHistory] = {}
        idx = "^NSEI" if company.exchange in ("NSE", "BSE") else "^GSPC"
        try:
            h = yf.Ticker(idx).history(period="2y", interval="1d")
            if h is not None and not h.empty:
                f = h.rename(columns=str.lower)[["open", "high", "low", "close"]]
                f["volume"] = 0
                f.index = pd.to_datetime(f.index).tz_localize(None)
                out["NIFTY" if idx == "^NSEI" else "SPX"] = PriceHistory(idx, f, self.name)
        except Exception:
            pass
        return out

    def fundamentals(self, company: Company) -> Optional[Fundamentals]:
        yf = self._yf()
        t = yf.Ticker(self._yf_symbol(company))
        try:
            fin = t.financials
            bs = t.balance_sheet
            cf = t.cashflow
            info = t.get_info()
        except Exception:
            return None
        if fin is None or fin.empty:
            return None

        def pick(df, *names):
            if df is None or df.empty:
                return None
            for nm in names:
                if nm in df.index:
                    return df.loc[nm]
            return None

        cols = list(fin.columns)
        stmts: list[FinancialStatement] = []
        rev = pick(fin, "Total Revenue")
        ni = pick(fin, "Net Income")
        ebit = pick(fin, "EBIT", "Operating Income")
        interest = pick(fin, "Interest Expense")
        debt = pick(bs, "Total Debt", "Long Term Debt")
        equity = pick(bs, "Stockholders Equity", "Total Stockholder Equity")
        assets = pick(bs, "Total Assets")
        cfo = pick(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = pick(cf, "Capital Expenditure")
        for c in reversed(cols):  # oldest → newest
            stmts.append(FinancialStatement(
                period=str(getattr(c, "year", c)),
                revenue=_g(rev, c), net_income=_g(ni, c), ebit=_g(ebit, c),
                interest=_g(interest, c), total_debt=_g(debt, c), equity=_g(equity, c),
                total_assets=_g(assets, c), cfo=_g(cfo, c), capex=_g(capex, c),
            ))
        return Fundamentals(
            symbol=company.symbol, statements=stmts,
            price=(info or {}).get("regularMarketPrice"),
            shares_outstanding=(info or {}).get("sharesOutstanding"),
            source=self.name,
        )


def _g(series, col):
    if series is None:
        return None
    try:
        val = series.get(col)
        return None if val is None or pd.isna(val) else float(val)
    except Exception:
        return None


class AlphaVantageProvider(DataProvider):
    """Daily prices via Alpha Vantage. Needs ALPHAVANTAGE_API_KEY."""
    name = "alphavantage"

    def __init__(self, api_key: Optional[str] = None) -> None:
        import os
        self.api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")

    def available(self) -> bool:
        try:
            import requests  # noqa
        except Exception:
            return False
        return bool(self.api_key)

    def _req(self, params: dict):
        import requests
        params["apikey"] = self.api_key
        r = requests.get("https://www.alphavantage.co/query", params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def resolve(self, query: str) -> Optional[Company]:
        if not self.available():
            raise ProviderUnavailable("ALPHAVANTAGE_API_KEY not set")
        data = self._req({"function": "SYMBOL_SEARCH", "keywords": query})
        best = (data.get("bestMatches") or [None])[0]
        if not best:
            return None
        return Company(symbol=best["1. symbol"], name=best["2. name"],
                       exchange=best.get("4. region", "US"),
                       currency=best.get("8. currency", "USD"))

    def prices(self, company: Company) -> Optional[PriceHistory]:
        if not self.available():
            raise ProviderUnavailable("ALPHAVANTAGE_API_KEY not set")
        data = self._req({"function": "TIME_SERIES_DAILY", "symbol": company.symbol,
                          "outputsize": "full"})
        ts = data.get("Time Series (Daily)")
        if not ts:
            return None
        rows = {
            pd.Timestamp(d): {
                "open": float(v["1. open"]), "high": float(v["2. high"]),
                "low": float(v["3. low"]), "close": float(v["4. close"]),
                "volume": float(v["5. volume"]),
            } for d, v in ts.items()
        }
        frame = pd.DataFrame(rows).T.sort_index()
        return PriceHistory(symbol=company.symbol, frame=frame, source=self.name)


class ScreenerProvider(DataProvider):
    """Placeholder adapter for screener.in fundamentals.

    screener.in has no public API; a production adapter would authenticate and
    parse the company page/export. Left as a documented extension point that
    declares itself unavailable rather than shipping brittle scraping.
    """
    name = "screener"

    def available(self) -> bool:
        return False

    def resolve(self, query: str) -> Optional[Company]:
        raise ProviderUnavailable("screener adapter is a documented stub — implement fetch/parse to enable")

    def prices(self, company: Company) -> Optional[PriceHistory]:
        return None
