"""Market profiles — one engine, every geography.

A ``MarketProfile`` is the swappable bundle of conventions that make research in
one market different from another: the accounting regime, the regulator and its
disclosure cadence, the reporting currency, the benchmark index, the governance
risks that lead locally, and the macro anchor. Selecting a market re-parameterises
how the lenses are *framed* — the forensic read hunts promoter pledging in Mumbai
and litigation reserves in New York.

Profiles are deliberately declarative data, not behaviour: the analysis lenses
stay market-agnostic; the agent uses the profile to frame the mandate, weight
which risks lead, and label provenance. New markets are added by appending a row.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    """Static conventions for one market/geography."""
    key: str                       # short code: "US", "IN", "JP", ...
    name: str                      # human label
    region: str                    # "Americas" / "Europe" / "Asia ex-Japan" / ...
    accounting: str                # "US GAAP" / "IFRS" / "Ind-AS" / ...
    regulator: str                 # "SEC" / "SEBI" / "ESMA" / ...
    reporting_cadence: str         # "quarterly" / "semi-annual"
    currency: str                  # ISO-ish code used for reporting
    benchmarks: tuple[str, ...]    # local index reference set
    governance_focus: tuple[str, ...]   # the risks the local read should lead with
    macro_anchor: str              # the rate/FX that frames the top-down
    notes: str = ""

    @property
    def headline(self) -> str:
        return (f"{self.name} · {self.accounting} · {self.regulator} · "
                f"{self.reporting_cadence} reporting · {self.currency}")

    @property
    def is_generic(self) -> bool:
        return self.key == "XX"

    @property
    def default_wacc(self) -> float:
        """A market-anchored discount rate — the local risk-free + equity premium
        blend, used as the DCF default when nothing better is supplied. Real spreads:
        higher in EM/India, lower in Japan/developed Europe."""
        return _DEFAULT_WACC.get(self.key, 0.11)


# market-anchored default discount rates (blended cost of capital)
_DEFAULT_WACC: dict[str, float] = {
    "US": 0.09, "CA": 0.10, "GB": 0.09, "EU": 0.09, "IN": 0.13,
    "JP": 0.07, "HK": 0.10, "CN": 0.11, "AU": 0.09, "SG": 0.09, "XX": 0.11,
}


# ── the registry ─────────────────────────────────────────────────────────────
GENERIC = MarketProfile(
    key="XX", name="Global (unresolved)", region="Global",
    accounting="IFRS (assumed)", regulator="local", reporting_cadence="quarterly",
    currency="local", benchmarks=("MSCI World",),
    governance_focus=("controlling shareholders", "related-party transactions",
                      "audit quality"),
    macro_anchor="US rates / DXY",
    notes="Placeholder used until the market is inferred from the resolved listing.",
)

PROFILES: dict[str, MarketProfile] = {p.key: p for p in [
    MarketProfile(
        key="US", name="United States", region="Americas",
        accounting="US GAAP", regulator="SEC", reporting_cadence="quarterly",
        currency="USD", benchmarks=("S&P 500", "Nasdaq 100", "Russell 2000"),
        governance_focus=("litigation & legal reserves", "buyback discipline",
                          "stock-based-comp dilution"),
        macro_anchor="Fed funds / UST 10y"),
    MarketProfile(
        key="CA", name="Canada", region="Americas",
        accounting="IFRS", regulator="CSA / OSC", reporting_cadence="quarterly",
        currency="CAD", benchmarks=("S&P/TSX Composite",),
        governance_focus=("resource reserve accounting", "dual-class structures",
                          "related-party transactions"),
        macro_anchor="BoC / CAD, commodities"),
    MarketProfile(
        key="GB", name="United Kingdom", region="Europe",
        accounting="IFRS", regulator="FCA", reporting_cadence="semi-annual",
        currency="GBP", benchmarks=("FTSE 100", "FTSE 250"),
        governance_focus=("board independence", "pension deficits", "dividend cover"),
        macro_anchor="BoE / GBP"),
    MarketProfile(
        key="EU", name="Europe (Eurozone)", region="Europe",
        accounting="IFRS", regulator="ESMA + national", reporting_cadence="semi-annual",
        currency="EUR", benchmarks=("STOXX 600", "DAX", "CAC 40"),
        governance_focus=("board & works-council structure", "state stakes",
                          "dividend cover"),
        macro_anchor="ECB / EUR"),
    MarketProfile(
        key="IN", name="India", region="Asia ex-Japan",
        accounting="Ind-AS", regulator="SEBI", reporting_cadence="quarterly",
        currency="INR", benchmarks=("NIFTY 50", "SENSEX", "NIFTY sectoral"),
        governance_focus=("promoter holding & pledging", "related-party transactions",
                          "auditor changes & qualifications"),
        macro_anchor="RBI repo / INR"),
    MarketProfile(
        key="JP", name="Japan", region="Japan",
        accounting="J-GAAP / IFRS", regulator="FSA / JPX", reporting_cadence="quarterly",
        currency="JPY", benchmarks=("TOPIX", "Nikkei 225"),
        governance_focus=("cross-shareholdings", "capital efficiency / ROE agenda",
                          "parent-subsidiary listings"),
        macro_anchor="BoJ / JPY"),
    MarketProfile(
        key="HK", name="Hong Kong", region="Asia ex-Japan",
        accounting="HKFRS", regulator="SFC / HKEX", reporting_cadence="semi-annual",
        currency="HKD", benchmarks=("Hang Seng", "HSCEI"),
        governance_focus=("controlling shareholder & connected transactions",
                          "free float", "audit access"),
        macro_anchor="HKMA peg / HKD"),
    MarketProfile(
        key="CN", name="China (A-shares)", region="Asia ex-Japan",
        accounting="China ASBE", regulator="CSRC", reporting_cadence="quarterly",
        currency="CNY", benchmarks=("CSI 300", "ChiNext"),
        governance_focus=("state ownership & VIE structures",
                          "related-party & governance opacity", "audit access"),
        macro_anchor="PBoC / CNY"),
    MarketProfile(
        key="AU", name="Australia & NZ", region="Australia & NZ",
        accounting="IFRS (AASB)", regulator="ASIC / ASX", reporting_cadence="semi-annual",
        currency="AUD", benchmarks=("S&P/ASX 200",),
        governance_focus=("franking credits", "resource reserve accounting",
                          "continuous disclosure"),
        macro_anchor="RBA / AUD, commodities"),
    MarketProfile(
        key="SG", name="Singapore", region="Asia ex-Japan",
        accounting="SFRS (IFRS)", regulator="MAS / SGX", reporting_cadence="semi-annual",
        currency="SGD", benchmarks=("Straits Times Index",),
        governance_focus=("controlling shareholders", "REIT structures",
                          "related-party transactions"),
        macro_anchor="MAS / SGD"),
]}

# exchange code → market key
EXCHANGE_MARKET: dict[str, str] = {
    "NSE": "IN", "BSE": "IN",
    "NASDAQ": "US", "NYSE": "US", "AMEX": "US", "NYSEARCA": "US",
    "TSX": "CA", "TSXV": "CA",
    "LSE": "GB", "LON": "GB",
    "XETRA": "EU", "FRA": "EU", "EPA": "EU", "AMS": "EU", "BIT": "EU", "BME": "EU",
    "TSE": "JP", "TYO": "JP", "JPX": "JP",
    "HKEX": "HK", "SEHK": "HK", "HKG": "HK",
    "SSE": "CN", "SZSE": "CN", "SHA": "CN", "SHE": "CN",
    "ASX": "AU", "NZX": "AU",
    "SGX": "SG",
}

# reporting currency → market key (last-resort inference)
CURRENCY_MARKET: dict[str, str] = {
    "USD": "US", "CAD": "CA", "GBP": "GB", "GBX": "GB", "EUR": "EU",
    "INR": "IN", "JPY": "JP", "HKD": "HK", "CNY": "CN", "RMB": "CN",
    "AUD": "AU", "NZD": "AU", "SGD": "SG",
}

# query phrase → market key (so "a Japanese chipmaker" routes to JP)
_QUERY_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("india", "indian", "nse", "bse", "nifty", "sensex"), "IN"),
    (("united states", "u.s.", " us ", "america", "nasdaq", "nyse", "s&p"), "US"),
    (("canada", "canadian", "tsx"), "CA"),
    (("united kingdom", " uk ", "britain", "british", "london", "lse", "ftse"), "GB"),
    (("europe", "european", "eurozone", "germany", "german", "france", "french",
      "dax", "stoxx", "xetra"), "EU"),
    (("japan", "japanese", "tokyo", "topix", "nikkei"), "JP"),
    (("hong kong", "hkex", "hang seng"), "HK"),
    (("china", "chinese", "shanghai", "shenzhen", "a-share", "a share", "csi"), "CN"),
    (("australia", "australian", "asx", "new zealand"), "AU"),
    (("singapore", "sgx", "straits times"), "SG"),
)


def get_profile(key: str | None) -> MarketProfile | None:
    if not key:
        return None
    return PROFILES.get(key.upper())


def profile_for_exchange(exchange: str | None) -> MarketProfile | None:
    if not exchange:
        return None
    return get_profile(EXCHANGE_MARKET.get(exchange.upper()))


def infer_profile(
    *,
    market: str | None = None,
    exchange: str | None = None,
    currency: str | None = None,
    query: str | None = None,
) -> MarketProfile:
    """Best-effort market resolution, in priority order:

    explicit key → exchange → query phrase → reporting currency → GENERIC.
    """
    if market:
        p = get_profile(market)
        if p:
            return p
    p = profile_for_exchange(exchange)
    if p:
        return p
    if query:
        q = f" {query.lower()} "
        for phrases, key in _QUERY_HINTS:
            if any(phrase in q for phrase in phrases):
                return PROFILES[key]
    if currency:
        key = CURRENCY_MARKET.get(currency.upper())
        if key:
            return PROFILES[key]
    return GENERIC
