"""The one interface every data source implements.

The analysis engine only ever talks to a `DataProvider`; it never knows whether
the bytes came from a bundled snapshot, yfinance, Alpha Vantage or a broker API.
That is the whole point — swap the provider, keep the analytics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import (
    Company,
    CompanyData,
    Fundamentals,
    Ownership,
    PriceHistory,
    StreetConsensus,
)


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot operate here (no network, no key, missing dep)."""


class DataProvider(ABC):
    name: str = "base"

    def available(self) -> bool:
        """Cheap check: can this provider run in the current environment?
        Adapters that need network/keys override this so the registry can skip them."""
        return True

    # ── identity ────────────────────────────────────────────────────────────
    @abstractmethod
    def resolve(self, query: str) -> Optional[Company]:
        """Map a free-text name/ticker to a Company, or None if not found."""

    # ── the individual feeds ──────────────────────────────────────────────────
    @abstractmethod
    def prices(self, company: Company) -> Optional[PriceHistory]: ...

    def fundamentals(self, company: Company) -> Optional[Fundamentals]:
        return None

    def consensus(self, company: Company) -> Optional[StreetConsensus]:
        """Sell-side analyst consensus (price target, ratings, forward estimates).
        Only live providers implement this; offline/synthetic sources return None."""
        return None

    def ownership(self, company: Company) -> Optional[Ownership]:
        return None

    def news(self, company: Company):
        return []

    def corporate_actions(self, company: Company):
        return []

    def earnings_calls(self, company: Company):
        return []

    def peers(self, company: Company) -> list[str]:
        return []

    def benchmarks(self, company: Company) -> dict[str, PriceHistory]:
        return {}

    # ── the aggregate the builder actually calls ────────────────────────────
    def fetch(self, company: Company) -> CompanyData:
        """Assemble a CompanyData, tolerating partial feeds. Any feed that raises
        is downgraded to 'missing' rather than sinking the whole report."""
        def _safe(fn, default):
            try:
                return fn(company)
            except Exception:
                return default

        return CompanyData(
            company=company,
            prices=_safe(self.prices, None),
            fundamentals=_safe(self.fundamentals, None),
            consensus=_safe(self.consensus, None),
            ownership=_safe(self.ownership, None),
            news=_safe(self.news, []) or [],
            corporate_actions=_safe(self.corporate_actions, []) or [],
            earnings_calls=_safe(self.earnings_calls, []) or [],
            peers=_safe(self.peers, []) or [],
            benchmarks=_safe(self.benchmarks, {}) or {},
        )
