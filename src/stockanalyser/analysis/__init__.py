"""The nine analysis lenses. Each exposes `analyse(data, ...) -> LensResult`."""
from . import (
    fundamental,
    governance,
    ownership,
    patterns,
    qualitative,
    quality,
    sector,
    spikes,
    technical,
    valuation,
)

__all__ = [
    "technical", "spikes", "fundamental", "quality", "valuation",
    "qualitative", "governance", "sector", "ownership", "patterns",
]
