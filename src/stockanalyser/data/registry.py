"""Provider selection + name resolution with graceful fallback.

The builder asks the registry for a `(company, data, provider)` triple given a
free-text query. The registry walks a provider chain (live first when the user
opts in, offline always last) and picks the first provider that can both resolve
the name AND return a usable price history — so a live provider that's down or
rate-limited transparently falls back to the bundled snapshots.
"""
from __future__ import annotations

from typing import Optional

from ..config import Config
from ..models import Company, CompanyData
from .base import DataProvider
from .offline import OfflineProvider
from .live import (
    AlphaVantageProvider, FMPProvider, ScreenerProvider, YFinanceProvider,
)


def build_chain(config: Config) -> list[DataProvider]:
    offline = OfflineProvider()
    if config.provider == "offline":
        return [offline]
    if config.provider == "fmp":
        return [FMPProvider(), offline]
    if config.provider == "yfinance":
        return [YFinanceProvider(), offline]
    if config.provider == "alphavantage":
        return [AlphaVantageProvider(), offline]
    if config.provider == "screener":
        return [ScreenerProvider(), offline]
    # auto: try live providers that declare themselves available, else offline.
    # FMP first — a keyed API is reliable from servers where yfinance (Yahoo scraping)
    # gets blocked from datacenter IPs.
    chain: list[DataProvider] = []
    for p in (FMPProvider(), YFinanceProvider(), AlphaVantageProvider()):
        try:
            if p.available():
                chain.append(p)
        except Exception:
            pass
    chain.append(offline)
    return chain


def resolve_and_fetch(query: str, config: Config) -> Optional[tuple[Company, CompanyData, str]]:
    chain = build_chain(config)
    offline = chain[-1]
    resolved: Optional[tuple[Company, DataProvider]] = None

    for provider in chain:
        try:
            company = provider.resolve(query)
        except Exception:
            company = None
        if company is None:
            continue
        try:
            has_prices = provider.prices(company) is not None
        except Exception:
            has_prices = False
        if has_prices:
            resolved = (company, provider)
            break
        # remember first successful resolution even without prices
        if resolved is None:
            resolved = (company, provider)

    if resolved is None:
        return None

    company, provider = resolved
    data = provider.fetch(company)

    # Backfill any missing feed from the offline snapshots (best-effort enrichment)
    if provider is not offline:
        try:
            off_company = offline.resolve(company.symbol) or offline.resolve(company.name)
        except Exception:
            off_company = None
        if off_company is not None:
            off = offline.fetch(off_company)
            data.fundamentals = data.fundamentals or off.fundamentals
            data.consensus = data.consensus or off.consensus
            data.ownership = data.ownership or off.ownership
            data.news = data.news or off.news
            data.corporate_actions = data.corporate_actions or off.corporate_actions
            data.earnings_calls = data.earnings_calls or off.earnings_calls
            data.peers = data.peers or off.peers
            if not data.benchmarks:
                data.benchmarks = off.benchmarks

        # For a real live company with no snapshot news, pull live headlines so
        # spike attribution has something to correlate against.
        if not data.news:
            try:
                from .news import fetch_news
                data.news = fetch_news(company)
            except Exception:
                pass

    # Ingest real earnings-call transcripts (local dir or FMP) if configured — these
    # replace the bundled illustrative samples. Runs for every provider, incl. offline.
    try:
        from .transcripts import ingest_transcripts
        real_calls = ingest_transcripts(company, config)
        if real_calls:
            data.earnings_calls = real_calls
    except Exception:
        pass

    return company, data, provider.name
