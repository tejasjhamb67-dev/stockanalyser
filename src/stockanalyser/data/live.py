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

from ..models import (
    AnalystEstimate, Company, FinancialStatement, Fundamentals, PriceHistory,
    StreetConsensus,
)
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

    def consensus(self, company: Company):
        yf = self._yf()
        t = yf.Ticker(self._yf_symbol(company))
        info = _try(lambda: t.get_info()) or {}
        return parse_consensus(
            company.symbol, info,
            price_targets=_try(lambda: t.analyst_price_targets),
            earnings_est=_try(lambda: t.earnings_estimate),
            revenue_est=_try(lambda: t.revenue_estimate),
            recommendations=_try(lambda: t.recommendations))

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


def _try(fn):
    try:
        return fn()
    except Exception:
        return None


# yfinance estimate index labels → our period labels (current & next fiscal year)
_EST_PERIODS = {"0y": "curr FY", "+1y": "next FY"}


def parse_consensus(symbol, info, price_targets=None, earnings_est=None,
                    revenue_est=None, recommendations=None):
    """Map yfinance analyst data (info dict + estimate/recommendation frames) into a
    StreetConsensus, or None when the name has no sell-side coverage."""
    info = info or {}
    pt = price_targets if isinstance(price_targets, dict) else {}
    tgt_mean = _num(info.get("targetMeanPrice")) or _num(pt.get("mean"))
    tgt_high = _num(info.get("targetHighPrice")) or _num(pt.get("high"))
    tgt_low = _num(info.get("targetLowPrice")) or _num(pt.get("low"))
    n = _int(info.get("numberOfAnalystOpinions"))
    rec_key = info.get("recommendationKey")
    rec_mean = _num(info.get("recommendationMean"))
    rec_counts = _rec_counts(recommendations)
    estimates = _est_lines(earnings_est, "EPS") + _est_lines(revenue_est, "Revenue")

    sc = StreetConsensus(
        symbol=symbol, price_target_mean=tgt_mean, price_target_high=tgt_high,
        price_target_low=tgt_low, num_analysts=n,
        recommendation_key=(str(rec_key) if rec_key else None),
        recommendation_mean=rec_mean, rec_counts=rec_counts, estimates=estimates,
        source="yfinance")
    return sc if sc.has_view else None


def _est_lines(df, metric: str) -> list[AnalystEstimate]:
    if df is None or getattr(df, "empty", True):
        return []
    out: list[AnalystEstimate] = []
    for key, label in _EST_PERIODS.items():
        if key not in df.index:
            continue
        row = df.loc[key]
        out.append(AnalystEstimate(
            period=label, metric=metric,
            mean=_num(_cell(row, "avg")), low=_num(_cell(row, "low")),
            high=_num(_cell(row, "high")),
            num_analysts=_int(_cell(row, "numberOfAnalysts"))))
    return out


def _rec_counts(df) -> dict[str, int]:
    if df is None or getattr(df, "empty", True):
        return {}
    # newest row: prefer the '0m' period, else the first row
    row = None
    if "period" in getattr(df, "columns", []):
        m = df[df["period"] == "0m"]
        row = (m.iloc[0] if not m.empty else df.iloc[0])
    else:
        row = df.iloc[0]
    out: dict[str, int] = {}
    for k in ("strongBuy", "buy", "hold", "sell", "strongSell"):
        v = _int(_cell(row, k))
        if v is not None:
            out[k] = v
    return out


def _cell(row, key):
    try:
        return row.get(key)
    except Exception:
        return None


def _num(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def _int(v):
    f = _num(v)
    return int(f) if f is not None else None


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


class FMPProvider(DataProvider):
    """Financial Modeling Prep — prices + full fundamentals + profile + consensus for
    (nearly) any global listing, from one key. Reliable from servers (a keyed API,
    not screen-scraping), which is why it's the recommended production source: set
    FMP_API_KEY and any ticker or name goes live.

    Symbols use the same suffixes as Yahoo (RELIANCE.NS, BP.L); a bare name is
    resolved via FMP search.
    """
    name = "fmp"
    BASE = "https://financialmodelingprep.com"

    def __init__(self, api_key: Optional[str] = None) -> None:
        import os
        self.api_key = api_key or os.environ.get("FMP_API_KEY")

    def available(self) -> bool:
        try:
            import requests  # noqa
        except Exception:
            return False
        return bool(self.api_key)

    def _get(self, path: str, **params):
        import requests
        params["apikey"] = self.api_key
        r = requests.get(f"{self.BASE}{path}", params=params, timeout=25)
        r.raise_for_status()
        return r.json()

    def resolve(self, query: str) -> Optional[Company]:
        if not self.available():
            raise ProviderUnavailable("FMP_API_KEY not set")
        raw = query.strip().upper().replace(" ", "") if len(query.split()) == 1 else query.strip()
        # try the query as a direct symbol first, then fall back to search
        for sym in (raw, None):
            if sym is None:
                try:
                    hits = self._get("/api/v3/search", query=query.strip(), limit=5) or []
                except Exception:
                    hits = []
                sym = hits[0].get("symbol") if hits else None
                if not sym:
                    return None
            try:
                prof = self._get(f"/api/v3/profile/{sym}")
            except Exception:
                prof = None
            if prof:
                return company_from_fmp_profile(prof[0] if isinstance(prof, list) else prof)
        return None

    def prices(self, company: Company) -> Optional[PriceHistory]:
        try:
            payload = self._get(f"/api/v3/historical-price-full/{company.symbol}",
                                serietype="line", timeseries=520)
        except Exception:
            return None
        frame = parse_fmp_prices(payload)
        if frame is None:
            return None
        return PriceHistory(symbol=company.symbol, frame=frame, source=self.name)

    def fundamentals(self, company: Company) -> Optional[Fundamentals]:
        def _safe(path, **p):
            try:
                return self._get(path, **p)
            except Exception:
                return None
        income = _safe(f"/api/v3/income-statement/{company.symbol}", limit=6)
        balance = _safe(f"/api/v3/balance-sheet-statement/{company.symbol}", limit=6)
        cashflow = _safe(f"/api/v3/cash-flow-statement/{company.symbol}", limit=6)
        profile = _safe(f"/api/v3/profile/{company.symbol}")
        prof = (profile[0] if isinstance(profile, list) and profile else profile) or {}
        return parse_fmp_fundamentals(company.symbol, income, balance, cashflow, prof)

    def consensus(self, company: Company):
        def _safe(path, **p):
            try:
                return self._get(path, **p)
            except Exception:
                return None
        target = _safe("/api/v4/price-target-consensus", symbol=company.symbol)
        rating = _safe(f"/api/v3/rating/{company.symbol}")
        return parse_fmp_street(company.symbol, target, rating)


# ── FMP pure mappers (network-free, unit-tested) ─────────────────────────────
_FMP_EXCHANGE = {"HKSE": "HKEX", "SHH": "SSE", "SHZ": "SZSE", "JPX": "TSE",
                 "TSE": "TSE", "TSXV": "TSXV", "EURONEXT": "EPA"}


def company_from_fmp_profile(p: dict) -> Company:
    exch = (p.get("exchangeShortName") or p.get("exchange") or "").upper()
    return Company(
        symbol=p.get("symbol"), name=p.get("companyName") or p.get("symbol"),
        exchange=_FMP_EXCHANGE.get(exch, exch or "NASDAQ"),
        sector=p.get("sector") or None, industry=p.get("industry") or None,
        currency=p.get("currency") or "USD", market_cap=_num(p.get("mktCap")),
        description=p.get("description") or None)


def parse_fmp_prices(payload):
    hist = payload.get("historical") if isinstance(payload, dict) else payload
    if not hist:
        return None
    rows = {}
    for h in hist:
        d = h.get("date")
        if not d:
            continue
        rows[pd.Timestamp(d)] = {
            "open": _num(h.get("open")), "high": _num(h.get("high")),
            "low": _num(h.get("low")), "close": _num(h.get("close")),
            "volume": _num(h.get("volume")) or 0.0}
    if not rows:
        return None
    frame = pd.DataFrame(rows).T.sort_index()[["open", "high", "low", "close", "volume"]]
    frame = frame.dropna(subset=["close"])
    return frame if not frame.empty else None


def parse_fmp_fundamentals(symbol, income, balance, cashflow, profile) -> Optional[Fundamentals]:
    if not income:
        return None
    bmap = {r.get("date"): r for r in (balance or [])}
    cmap = {r.get("date"): r for r in (cashflow or [])}
    profile = profile or {}
    stmts: list[FinancialStatement] = []
    for r in reversed(income):      # FMP is newest-first; we want oldest→newest
        d = r.get("date")
        b, c = bmap.get(d, {}), cmap.get(d, {})
        dep = _num(r.get("depreciationAndAmortization")) or _num(c.get("depreciationAndAmortization"))
        ebit = _num(r.get("operatingIncome"))
        ebitda = _num(r.get("ebitda"))
        if ebitda is None and ebit is not None and dep is not None:
            ebitda = ebit + dep
        stmts.append(FinancialStatement(
            period=_fmp_period(r),
            revenue=_num(r.get("revenue")), ebitda=ebitda, depreciation=_absn(dep),
            ebit=ebit, interest=_absn(_num(r.get("interestExpense"))),
            pbt=_num(r.get("incomeBeforeTax")), tax=_num(r.get("incomeTaxExpense")),
            net_income=_num(r.get("netIncome")), total_assets=_num(b.get("totalAssets")),
            current_assets=_num(b.get("totalCurrentAssets")), inventory=_num(b.get("inventory")),
            receivables=_num(b.get("netReceivables")),
            cash=_num(b.get("cashAndCashEquivalents")),
            current_liabilities=_num(b.get("totalCurrentLiabilities")),
            total_debt=_num(b.get("totalDebt")), equity=_num(b.get("totalStockholdersEquity")),
            payables=_num(b.get("accountPayables")), cfo=_num(c.get("operatingCashFlow")),
            capex=_absn(_num(c.get("capitalExpenditure"))),
            shares_outstanding=_num(r.get("weightedAverageShsOut"))))
    if not stmts:
        return None
    div = _num(profile.get("lastDiv"))
    if div:
        stmts[-1].dividend_per_share = div
    shares = _num(profile.get("sharesOutstanding")) or stmts[-1].shares_outstanding
    return Fundamentals(symbol=symbol, statements=stmts,
                        price=_num(profile.get("price")),
                        shares_outstanding=shares, source="fmp")


def _fmp_period(row: dict) -> str:
    yr = row.get("calendarYear")
    per = row.get("period")
    if yr and per and per != "FY":
        return f"{per}FY{str(yr)[-2:]}"
    if yr:
        return f"FY{yr}"
    return str(row.get("date") or "period")


_FMP_RATING = {"strong buy": "strong_buy", "buy": "buy", "outperform": "buy",
               "hold": "hold", "neutral": "hold", "sell": "sell",
               "underperform": "sell", "strong sell": "strong_sell"}


def parse_fmp_street(symbol, target, rating):
    t = (target[0] if isinstance(target, list) and target else target) or {}
    r = (rating[0] if isinstance(rating, list) and rating else rating) or {}
    mean = _num(t.get("targetConsensus")) or _num(t.get("targetMedian"))
    rec = (r.get("ratingRecommendation") or r.get("rating") or "").strip().lower()
    sc = StreetConsensus(
        symbol=symbol, price_target_mean=mean,
        price_target_high=_num(t.get("targetHigh")), price_target_low=_num(t.get("targetLow")),
        recommendation_key=_FMP_RATING.get(rec) or (rec or None),
        source="fmp")
    return sc if sc.has_view else None


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
