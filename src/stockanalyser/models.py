"""Core data models shared across the engine.

These are deliberately plain dataclasses: providers fill them, analysis modules
read them, the report renders them. Keeping them dependency-light (only stdlib +
a pandas DataFrame for price history) means every layer can be tested in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional

import pandas as pd


class Verdict(str, Enum):
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    AVOID = "Avoid"
    STRONG_AVOID = "Strong Avoid"
    INSUFFICIENT = "Insufficient Data"


@dataclass
class Company:
    """Identity + static descriptors of a listed company."""
    symbol: str                      # canonical ticker, e.g. "POWERINDIA"
    name: str                        # "Hitachi Energy India Ltd"
    exchange: str = "NSE"            # NSE / BSE / NASDAQ ...
    sector: Optional[str] = None
    industry: Optional[str] = None
    currency: str = "INR"
    market_cap: Optional[float] = None      # in currency units
    aliases: list[str] = field(default_factory=list)
    description: Optional[str] = None

    @property
    def ticker(self) -> str:
        return f"{self.exchange}:{self.symbol}"


@dataclass
class PriceHistory:
    """Daily OHLCV. `frame` is indexed by date with columns:
    open, high, low, close, volume  (and optionally 'delivery_pct')."""
    symbol: str
    frame: pd.DataFrame
    source: str = "unknown"

    def __post_init__(self) -> None:
        needed = {"open", "high", "low", "close", "volume"}
        missing = needed - set(self.frame.columns)
        if missing:
            raise ValueError(f"PriceHistory missing columns: {sorted(missing)}")
        if not self.frame.index.is_monotonic_increasing:
            self.frame = self.frame.sort_index()

    @property
    def last_close(self) -> float:
        return float(self.frame["close"].iloc[-1])

    @property
    def span(self) -> str:
        idx = self.frame.index
        return f"{idx[0].date()} → {idx[-1].date()}" if len(idx) else "empty"


@dataclass
class FinancialStatement:
    """One period's condensed statements. All values in the reporting currency
    (crores for INR snapshots, absolute for others — the ratio math is scale-free)."""
    period: str                      # "FY2024", "Q1FY25"
    fiscal_end: Optional[date] = None
    # P&L
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    depreciation: Optional[float] = None
    ebit: Optional[float] = None
    interest: Optional[float] = None
    pbt: Optional[float] = None
    tax: Optional[float] = None
    net_income: Optional[float] = None
    # Balance sheet
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    inventory: Optional[float] = None
    receivables: Optional[float] = None
    cash: Optional[float] = None
    current_liabilities: Optional[float] = None
    total_debt: Optional[float] = None
    equity: Optional[float] = None
    payables: Optional[float] = None
    # Cash flow
    cfo: Optional[float] = None          # cash from operations
    capex: Optional[float] = None
    # Per share / market
    shares_outstanding: Optional[float] = None
    dividend_per_share: Optional[float] = None

    @property
    def fcf(self) -> Optional[float]:
        if self.cfo is None or self.capex is None:
            return None
        return self.cfo - abs(self.capex)


@dataclass
class Fundamentals:
    """Time series of statements + a few market snapshots."""
    symbol: str
    statements: list[FinancialStatement] = field(default_factory=list)
    price: Optional[float] = None            # latest price for valuation ratios
    shares_outstanding: Optional[float] = None
    source: str = "unknown"

    @property
    def latest(self) -> Optional[FinancialStatement]:
        return self.statements[-1] if self.statements else None

    def ordered(self) -> list[FinancialStatement]:
        """Oldest → newest."""
        return list(self.statements)


@dataclass
class AnalystEstimate:
    """One forward Street estimate for a metric in a period."""
    period: str                      # "curr FY" / "next FY"
    metric: str                      # "EPS" / "Revenue"
    mean: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    num_analysts: Optional[int] = None


@dataclass
class StreetConsensus:
    """Sell-side consensus a live provider supplies: analyst price target, the
    ratings distribution, and forward EPS/revenue estimates."""
    symbol: str
    price_target_mean: Optional[float] = None
    price_target_high: Optional[float] = None
    price_target_low: Optional[float] = None
    num_analysts: Optional[int] = None
    recommendation_key: Optional[str] = None    # "buy" / "hold" / "strong_buy" ...
    recommendation_mean: Optional[float] = None  # 1 (strong buy) .. 5 (strong sell)
    rec_counts: dict[str, int] = field(default_factory=dict)
    estimates: list[AnalystEstimate] = field(default_factory=list)
    source: str = "unknown"

    @property
    def has_view(self) -> bool:
        return (self.price_target_mean is not None or bool(self.estimates)
                or self.recommendation_key is not None)


@dataclass
class ShareholdingSnapshot:
    period: str
    promoter: Optional[float] = None         # % of equity
    promoter_pledged: Optional[float] = None  # % of promoter holding pledged
    fii: Optional[float] = None
    dii: Optional[float] = None
    public: Optional[float] = None


@dataclass
class Ownership:
    symbol: str
    history: list[ShareholdingSnapshot] = field(default_factory=list)
    bulk_block_deals: list[dict[str, Any]] = field(default_factory=list)
    source: str = "unknown"


@dataclass
class NewsItem:
    date: date
    headline: str
    summary: str = ""
    source: str = ""
    url: str = ""
    sentiment: Optional[float] = None        # -1..1, filled by qualitative module


@dataclass
class CorporateAction:
    date: date
    kind: str                                # dividend / bonus / split / buyback / results
    detail: str = ""


@dataclass
class EarningsCall:
    period: str
    date: Optional[date] = None
    transcript: str = ""
    source: str = ""


@dataclass
class CompanyData:
    """Everything a provider hands to the analysis layer for one company."""
    company: Company
    prices: Optional[PriceHistory] = None
    fundamentals: Optional[Fundamentals] = None
    consensus: Optional[StreetConsensus] = None
    ownership: Optional[Ownership] = None
    news: list[NewsItem] = field(default_factory=list)
    corporate_actions: list[CorporateAction] = field(default_factory=list)
    earnings_calls: list[EarningsCall] = field(default_factory=list)
    peers: list[str] = field(default_factory=list)
    # optional benchmark/sector index price histories keyed by name
    benchmarks: dict[str, PriceHistory] = field(default_factory=dict)


# ── Analysis outputs ────────────────────────────────────────────────────────

@dataclass
class Signal:
    """One atomic observation from an analysis module."""
    name: str
    value: Any
    interpretation: str
    stance: str = "neutral"          # bullish / bearish / neutral / warning
    confidence: float = 0.5          # 0..1


@dataclass
class LensResult:
    """Output of one analysis lens."""
    lens: str                        # "Technical", "Fundamental", ...
    score: Optional[float] = None    # 0..100, None = insufficient data
    summary: str = ""
    signals: list[Signal] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)   # raw numbers for the dashboard

    @property
    def has_score(self) -> bool:
        return self.score is not None


@dataclass
class Report:
    company: Company
    generated_at: str
    data_sources: dict[str, str] = field(default_factory=dict)
    lenses: dict[str, LensResult] = field(default_factory=dict)
    composite_score: Optional[float] = None
    verdict: Verdict = Verdict.INSUFFICIENT
    bull_thesis: list[str] = field(default_factory=list)
    bear_thesis: list[str] = field(default_factory=list)
    monitorables: list[str] = field(default_factory=list)
    narrative: str = ""
    warnings: list[str] = field(default_factory=list)
