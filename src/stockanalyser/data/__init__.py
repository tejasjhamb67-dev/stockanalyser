"""Pluggable data layer: one interface, many sources, graceful fallback."""
from .base import DataProvider, ProviderUnavailable
from .offline import OfflineProvider
from .registry import build_chain, resolve_and_fetch

__all__ = [
    "DataProvider",
    "ProviderUnavailable",
    "OfflineProvider",
    "build_chain",
    "resolve_and_fetch",
]
