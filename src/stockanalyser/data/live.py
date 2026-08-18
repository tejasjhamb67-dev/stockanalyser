"""Live data adapters. Real implementations, imported lazily so the package
installs and runs with no network and no optional dependencies.

Each adapter reports `available()` honestly (dependency present?) and raises or
returns None on network failure, letting the registry fall back to the next
provider — the engine never crashes because a feed is down.

The yfinance mapping is factored into pure functions (`parse_fundamentals`,
`company_from_info`, `price_frame`) that take yfinance-shaped objects and return
our models, so the transformation is unit-tested without any network.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..models import Company, FinancialStatement, Fundamentals, PriceHistory
from .base import DataProvider, ProviderUnavailable

# yfinance ticker suffix ↔ our exchange code (drives global resolution + market profile)
_SUFFIX_EXCHANGE = {
    "NS": "NSE", "BO": "BSE", "L": "LSE", "T": "TSE", "HK": "HKEX", "AX": "ASX",
    "SI": "SGX", "SS": "SSE", "SZ": "SZSE", "TO": "TSX", "V": "TSXV",
    "PA": "EPA", "DE": "XETRA", "F": "FRA", "AS": "AMS", "MI": "BIT",
    "MC": "BME", "NZ": "NZX",
}
_EXCHANGE_SUFFIX = {v: k for k, v in _SUFFIX_EXCHANGE.items()}
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "US"}

# benchmark index per exchange, for the relative-strength (sector) lens
_BENCH_INDEX = {
    "NSE": ("^NSEI", "NIFTY"), "BSE": ("^BSESN", "SENSEX"),
    "LSE": ("^FTSE", "FTSE"), "TSE": ("^N225", "NIKKEI"),
    "HKEX": ("^HSI", "HSI"), "ASX": ("^AXJO", "ASX200"),
    "XETRA": ("^GDAXI", "DAX"), "EPA": ("^FCHI", "CAC"),
    "TSX": ("^GSPTSE", "TSX"), "SGX": ("^STI", "STI"),
    "NASDAQ": ("^GSPC", "SPX"), "NYSE": ("^GSPC", "SPX"),
}
_DEFAULT_BENCH = ("^GSPC", "SPX")


class YFinanceProvider(DataProvider):
    """Prices + fundamentals via the `yfinance` package, across global exchanges.

    Resolution: a symbol carrying a known suffix is used as-is (``BP.L`` → LSE,
    ``7203.T`` → Tokyo). A bare symbol is tried as US, then NSE, then BSE. The
    resolved exchange code feeds the agent's market profile (accounting regime,
    WACC, benchmark), so a live name is framed for its home market automatically.
    """
    name = "yfinance"

    def _yf(self):
        try:
            import yfinance as yf  # noqa
            return yf
        except Exception as exc:  # pragma: no cover - depends on env
            raise ProviderUnavailable(
                "yfinance not installed (pip install stockanalyser[live])") from exc

    def available(self) -> bool:
        try:
            self._yf()
            return True
        except ProviderUnavailable:
            return False

    def _yf_symbol(self, company: Company) -> str:
        if company.exchange in _EXCHANGE_SUFFIX:
            return f"{company.symbol}.{_EXCHANGE_SUFFIX[company.exchange]}"
        return company.symbol      # US (or already-qualified) symbols carry no suffix

    def _candidates(self, query: str) -> list[tuple[str, str, str]]:
        """(yf_symbol, exchange_code, base_symbol) to try, in order."""
        raw = query.strip().upper().replace(" ", "")
        if "." in raw:
            base, suf = raw.rsplit(".", 1)
            if suf in _SUFFIX_EXCHANGE:
                return [(raw, _SUFFIX_EXCHANGE[suf], base)]
            return [(raw, "NASDAQ", raw)]
        return [(raw, "NASDAQ", raw), (f"{raw}.NS", "NSE", raw), (f"{raw}.BO", "BSE", raw)]

    def resolve(self, query: str) -> Optional[Company]:
        yf = self._yf()
        for yf_sym, exch, base in self._candidates(query):
            try:
                info = yf.Ticker(yf_sym).get_info()
            except Exception:
                continue
            if info and (info.get("regularMarketPrice") is not None
                         or info.get("currentPrice") is not None):
                return company_from_info(base, exch, info)
        return None

    def prices(self, company: Company) -> Optional[PriceHistory]:
        yf = self._yf()
        hist = yf.Ticker(self._yf_symbol(company)).history(period="2y", interval="1d")
        frame = price_frame(hist)
        if frame is None:
            return None
        return PriceHistory(symbol=company.symbol, frame=frame, source=self.name)

    def fundamentals(self, company: Company) -> Optional[Fundamentals]:
        yf = self._yf()
        t = yf.Ticker(self._yf_symbol(company))
        try:
            fin, bs, cf, info = t.financials, t.balance_sheet, t.cashflow, t.get_info()
        except Exception:
            return None
        return parse_fundamentals(company.symbol, fin, bs, cf, info)

    def benchmarks(self, company: Company) -> dict[str, PriceHistory]:
        yf = self._yf()
        idx, label = _BENCH_INDEX.get(company.exchange, _DEFAULT_BENCH)
        try:
            h = yf.Ticker(idx).history(period="2y", interval="1d")
            frame = price_frame(h, allow_zero_volume=True)
            if frame is not None:
                return {label: PriceHistory(idx, frame, self.name)}
        except Exception:
            pass
        return {}

    def news(self, company: Company):
        """Headlines via yfinance, falling back to Google News RSS."""
        from datetime import datetime
        from ..models import NewsItem
        yf = self._yf()
        out = []
        try:
            raw = yf.Ticker(self._yf_symbol(company)).news or []
            for n in raw[:25]:
                content = n.get("content", n)
                title = content.get("title") or n.get("title")
                if not title:
                    continue
                ts = n.get("providerPublishTime")
                when = datetime.fromtimestamp(ts).date() if ts else datetime.utcnow().date()
                url = ""
                cu = content.get("canonicalUrl")
                if isinstance(cu, dict):
                    url = cu.get("url", "")
                out.append(NewsItem(
                    date=when, headline=title,
                    source=(content.get("provider", {}) or {}).get("displayName", "yfinance"),
                    url=url))
        except Exception:
            pass
        if not out:
            try:
                from .news import fetch_news
                out = fetch_news(company)
            except Exception:
                out = []
        return out


# ── pure mappers (network-free, unit-tested) ─────────────────────────────────
def company_from_info(base_symbol: str, exchange: str, info: dict) -> Company:
    return Company(
        symbol=base_symbol,
        name=info.get("longName") or info.get("shortName") or base_symbol,
        exchange=exchange,
        sector=info.get("sector"),
        industry=info.get("industry"),
        currency=info.get("currency", "USD"),
        market_cap=info.get("marketCap"),
        description=info.get("longBusinessSummary"),
    )


def price_frame(hist, allow_zero_volume: bool = False):
    """yfinance history DataFrame → our OHLCV frame (tz-naive), or None."""
    if hist is None or getattr(hist, "empty", True):
        return None
    df = hist.rename(columns=str.lower)
    needed = ["open", "high", "low", "close"]
    if not all(c in df.columns for c in needed):
        return None
    if "volume" not in df.columns:
        if not allow_zero_volume:
            return None
        df = df.assign(volume=0)
    frame = df[["open", "high", "low", "close", "volume"]].copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    return frame


def _row(df, *labels):
    """First matching row Series for any of the candidate labels (case-insensitive)."""
    if df is None or getattr(df, "empty", True):
        return None
    idx = {str(i).lower(): i for i in df.index}
    for lab in labels:
        if lab in df.index:
            return df.loc[lab]
        key = lab.lower()
        if key in idx:
            return df.loc[idx[key]]
    return None


def _g(series, col):
    if series is None:
        return None
    try:
        val = series.get(col)
        return None if val is None or pd.isna(val) else float(val)
    except Exception:
        return None


def _sum(*vals):
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def _absn(v):
    return abs(v) if v is not None else None


def parse_fundamentals(symbol: str, fin, bs, cf, info) -> Optional[Fundamentals]:
    """Map yfinance's income / balance-sheet / cashflow frames + info dict into a
    Fundamentals with the full line-item set the driver model needs."""
    info = info or {}
    if fin is None or getattr(fin, "empty", True):
        return None
    cols = list(fin.columns)

    rev = _row(fin, "Total Revenue", "Revenue", "Operating Revenue")
    ebitda_r = _row(fin, "EBITDA", "Normalized EBITDA")
    ebit_r = _row(fin, "EBIT", "Operating Income", "Total Operating Income As Reported")
    dep_is = _row(fin, "Reconciled Depreciation")
    interest = _row(fin, "Interest Expense", "Interest Expense Non Operating")
    pbt = _row(fin, "Pretax Income", "Pre Tax Income")
    tax = _row(fin, "Tax Provision", "Income Tax Expense")
    ni = _row(fin, "Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations")
    shares_is = _row(fin, "Diluted Average Shares", "Basic Average Shares")

    assets = _row(bs, "Total Assets")
    ca = _row(bs, "Current Assets", "Total Current Assets")
    cl = _row(bs, "Current Liabilities", "Total Current Liabilities")
    inv = _row(bs, "Inventory")
    recv = _row(bs, "Accounts Receivable", "Receivables", "Net Receivables")
    cash = _row(bs, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
    debt = _row(bs, "Total Debt")
    ltd = _row(bs, "Long Term Debt")
    cur_debt = _row(bs, "Current Debt", "Current Debt And Capital Lease Obligation")
    equity = _row(bs, "Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity")
    pay = _row(bs, "Accounts Payable", "Payables", "Payables And Accrued Expenses")
    shares_bs = _row(bs, "Ordinary Shares Number", "Share Issued")

    cfo = _row(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
               "Total Cash From Operating Activities")
    capex = _row(cf, "Capital Expenditure", "Purchase Of PPE")
    dep_cf = _row(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")

    stmts: list[FinancialStatement] = []
    for col in reversed(cols):      # yfinance columns are newest→oldest; we want oldest→newest
        dep = _g(dep_is, col)
        if dep is None:
            dep = _g(dep_cf, col)
        dep = _absn(dep)
        ebit = _g(ebit_r, col)
        ebitda = _g(ebitda_r, col)
        if ebitda is None and ebit is not None and dep is not None:
            ebitda = ebit + dep
        if ebit is None and ebitda is not None and dep is not None:
            ebit = ebitda - dep
        total_debt = _g(debt, col)
        if total_debt is None:
            total_debt = _sum(_g(ltd, col), _g(cur_debt, col))
        shares = _g(shares_is, col) or _g(shares_bs, col)
        stmts.append(FinancialStatement(
            period=_period_label(col),
            revenue=_g(rev, col), ebitda=ebitda, depreciation=dep, ebit=ebit,
            interest=_absn(_g(interest, col)), pbt=_g(pbt, col), tax=_g(tax, col),
            net_income=_g(ni, col), total_assets=_g(assets, col),
            current_assets=_g(ca, col), inventory=_g(inv, col), receivables=_g(recv, col),
            cash=_g(cash, col), current_liabilities=_g(cl, col), total_debt=total_debt,
            equity=_g(equity, col), payables=_g(pay, col), cfo=_g(cfo, col),
            capex=_absn(_g(capex, col)), shares_outstanding=shares,
        ))

    if not stmts:
        return None
    div_rate = info.get("trailingAnnualDividendRate") or info.get("dividendRate")
    if div_rate:
        stmts[-1].dividend_per_share = float(div_rate)
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    return Fundamentals(
        symbol=symbol, statements=stmts,
        price=float(price) if price is not None else None,
        shares_outstanding=info.get("sharesOutstanding"),
        source="yfinance")


def _period_label(col) -> str:
    yr = getattr(col, "year", None)
    return f"FY{yr}" if yr else str(col)


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
