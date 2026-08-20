"""Sector / industry browse universe — clusters of names ranked by market cap.

Powers the /browse pages: pick a sector (and optionally an industry and a
market), get the top-N listings ranked by market capitalisation, each linking
into its full research report.

Live data comes from FMP's stock screener (a paid plan is needed for non-US
listings); with no key, or when the screen returns nothing, we fall back to the
bundled sample companies so the feature is always demoable. As everywhere in
this codebase the mapping is a pure function (`parse_fmp_screener`) tested with
synthetic payloads, and the source is reported honestly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import Config
from .live import FMPProvider, _num
from .offline import OfflineProvider

# Canonical FMP sector taxonomy (GICS-style). Order roughly by breadth.
SECTORS: list[str] = [
    "Technology", "Financial Services", "Healthcare", "Consumer Cyclical",
    "Communication Services", "Industrials", "Consumer Defensive", "Energy",
    "Basic Materials", "Real Estate", "Utilities",
]

# market key → (label, FMP country code). "" = global (no country filter).
MARKETS: dict[str, tuple[str, Optional[str]]] = {
    "": ("Global", None),
    "US": ("United States", "US"),
    "IN": ("India", "IN"),
    "GB": ("United Kingdom", "GB"),
    "JP": ("Japan", "JP"),
    "HK": ("Hong Kong", "HK"),
    "CN": ("China", "CN"),
    "AU": ("Australia", "AU"),
    "SG": ("Singapore", "SG"),
    "CA": ("Canada", "CA"),
    "DE": ("Germany", "DE"),
}


@dataclass
class UniverseRow:
    symbol: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[float] = None
    price: Optional[float] = None
    currency: str = "USD"


def canonical_sector(name: str) -> Optional[str]:
    """Match a free-text sector to the canonical taxonomy (case-insensitive)."""
    if not name:
        return None
    key = name.strip().lower()
    for s in SECTORS:
        if s.lower() == key:
            return s
    return None


def parse_fmp_screener(payload) -> list[UniverseRow]:
    """FMP /stock-screener payload (list of dicts) → UniverseRow list."""
    if not isinstance(payload, list):
        return []
    out: list[UniverseRow] = []
    for r in payload:
        if not isinstance(r, dict):
            continue
        sym = r.get("symbol")
        if not sym:
            continue
        out.append(UniverseRow(
            symbol=str(sym),
            name=r.get("companyName") or str(sym),
            sector=r.get("sector") or None,
            industry=r.get("industry") or None,
            exchange=(r.get("exchangeShortName") or r.get("exchange") or None),
            market_cap=_num(r.get("marketCap")),
            price=_num(r.get("price")),
            currency=(r.get("currency") or "USD"),
        ))
    return out


def _rank(rows: list[UniverseRow], limit: int) -> list[UniverseRow]:
    return sorted(rows, key=lambda x: (x.market_cap or -1.0), reverse=True)[:limit]


def industries_in(rows: list[UniverseRow]) -> list[str]:
    """Sorted unique industries present in a set of rows (for the filter chips)."""
    seen = {r.industry for r in rows if r.industry}
    return sorted(seen)


def _offline_rows(sector: Optional[str], industry: Optional[str]) -> list[UniverseRow]:
    """Sample names for the offline demo. Matching is fuzzy (substring, either
    direction) so a canonical sector like "Energy" still catches a sample tagged
    "Energy / Conglomerate"."""
    def _match(want: Optional[str], have: Optional[str]) -> bool:
        if not want:
            return True
        w, h = want.lower(), (have or "").lower()
        return bool(h) and (w in h or h in w)

    rows: list[UniverseRow] = []
    for c in OfflineProvider().catalogue():
        if not _match(sector, c.sector):
            continue
        if not _match(industry, c.industry):
            continue
        rows.append(UniverseRow(
            symbol=c.symbol, name=c.name, sector=c.sector, industry=c.industry,
            exchange=c.exchange, market_cap=c.market_cap, price=None,
            currency=c.currency))
    return rows


def build_universe(sector: Optional[str] = None, industry: Optional[str] = None,
                   market: str = "", limit: int = 50,
                   config: Optional[Config] = None) -> tuple[list[UniverseRow], list[str], str]:
    """Return (top-N rows by market cap, industries present, source).

    Tries FMP's live screener when a key is present and the provider isn't forced
    offline; otherwise (or when the screen is empty) falls back to the bundled
    sample names so the page always renders.
    """
    config = config or Config.default()
    country = MARKETS.get(market, ("", None))[1]

    if config.provider != "offline":
        prov = FMPProvider()
        try:
            available = prov.available()
        except Exception:
            available = False
        if available:
            payload = prov.screener_raw(sector=sector, industry=industry,
                                        country=country, limit=max(limit * 4, 200))
            rows = parse_fmp_screener(payload)
            if rows:
                return _rank(rows, limit), industries_in(rows), prov.name

    rows = _offline_rows(sector, industry)
    return _rank(rows, limit), industries_in(rows), OfflineProvider().name
