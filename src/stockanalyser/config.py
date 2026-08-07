"""Central tunables. Everything an analyst might want to argue about lives here,
not scattered as magic numbers across the modules."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TechnicalConfig:
    sma_short: int = 50
    sma_long: int = 200
    ema_short: int = 12
    ema_long: int = 26
    rsi_period: int = 14
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_sigma: float = 2.0
    atr_period: int = 14
    volume_ma: int = 20


@dataclass
class SpikeConfig:
    return_sigma: float = 2.5        # |z| of daily return to flag a spike
    volume_sigma: float = 2.0        # volume z-score to call a surge
    gap_pct: float = 3.0             # open-vs-prev-close % to call a gap
    lookback: int = 250              # trading days used to estimate the baseline
    event_window: int = 3            # ± days around a spike to search for causes
    min_abs_return: float = 4.0      # ignore sub-4% "spikes" as noise (percent)


@dataclass
class ValuationConfig:
    dcf_years: int = 10
    terminal_growth: float = 0.04
    discount_rate: float = 0.12      # default WACC when not supplied
    fade_to_terminal: bool = True    # linearly fade stage-1 growth toward terminal


@dataclass
class ScoreWeights:
    """Weights for the composite. Need not sum to 1 — they are normalised over the
    lenses that actually produced a score, so a missing lens never silently zeroes."""
    technical: float = 0.12
    spike: float = 0.06
    fundamental: float = 0.22
    quality: float = 0.16
    valuation: float = 0.16
    qualitative: float = 0.08
    governance: float = 0.08
    sector: float = 0.06
    ownership: float = 0.06

    def as_dict(self) -> dict[str, float]:
        return {
            "Technical": self.technical,
            "Spike": self.spike,
            "Fundamental": self.fundamental,
            "Quality": self.quality,
            "Valuation": self.valuation,
            "Qualitative": self.qualitative,
            "Governance": self.governance,
            "Sector": self.sector,
            "Ownership": self.ownership,
        }


@dataclass
class Config:
    technical: TechnicalConfig = field(default_factory=TechnicalConfig)
    spike: SpikeConfig = field(default_factory=SpikeConfig)
    valuation: ValuationConfig = field(default_factory=ValuationConfig)
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    provider: str = "auto"           # auto | offline | yfinance | alphavantage | screener
    use_llm: bool = True             # use Anthropic for narrative if a key is present

    @classmethod
    def default(cls) -> "Config":
        return cls()
