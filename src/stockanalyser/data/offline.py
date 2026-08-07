"""Offline provider — makes the whole engine runnable with zero network.

Two jobs:
  1. Load bundled *illustrative* fundamental/ownership/news snapshots (JSON).
  2. Deterministically simulate OHLCV price history with a benchmark and a
     sector index, deliberately injecting three kinds of shock so the spike
     attribution engine has real, checkable structure to explain:
        - stock-specific events (earnings/order/block-deal) → high alpha,
        - sector events → the move also shows up in the sector index → low alpha,
        - ordinary market beta.

Nothing here should ever be mistaken for live data — every payload carries a
provenance string and the source is reported as "offline-sample".
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..models import (
    Company,
    CorporateAction,
    EarningsCall,
    FinancialStatement,
    Fundamentals,
    NewsItem,
    Ownership,
    PriceHistory,
    ShareholdingSnapshot,
)
from .base import DataProvider

SAMPLES_DIR = Path(__file__).parent / "samples"
TRADING_DAYS = 252


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


class OfflineProvider(DataProvider):
    name = "offline-sample"

    def __init__(self) -> None:
        self._snapshots: dict[str, dict] = {}
        self._alias_index: dict[str, str] = {}
        self._sim_cache: dict[str, tuple[pd.DataFrame, dict[str, pd.DataFrame]]] = {}
        self._load()

    # ── snapshot loading ─────────────────────────────────────────────────────
    def _load(self) -> None:
        for path in sorted(SAMPLES_DIR.glob("*.json")):
            data = json.loads(path.read_text())
            sym = data["company"]["symbol"].upper()
            self._snapshots[sym] = data
            self._alias_index[_norm(sym)] = sym
            self._alias_index[_norm(data["company"]["name"])] = sym
            for alias in data["company"].get("aliases", []):
                self._alias_index[_norm(alias)] = sym

    # ── identity ─────────────────────────────────────────────────────────────
    def resolve(self, query: str) -> Optional[Company]:
        key = _norm(query)
        sym = self._alias_index.get(key)
        if sym is None:
            # partial containment match against aliases/names
            for alias_key, mapped in self._alias_index.items():
                if key and (key in alias_key or alias_key in key) and len(key) >= 3:
                    sym = mapped
                    break
        if sym is not None:
            return self._company(sym)
        # Unknown ticker: still resolvable as a synthetic, technical-only company
        # so the pipeline never dead-ends. Clearly flagged via a synthetic sector.
        raw = query.strip().upper()
        if raw and raw.replace(".", "").replace("-", "").isalnum():
            return Company(
                symbol=raw, name=raw, exchange="NSE", sector=None,
                description="Unknown symbol — synthetic price history only (no bundled fundamentals).",
            )
        return None

    def _company(self, sym: str) -> Company:
        c = self._snapshots[sym]["company"]
        return Company(
            symbol=c["symbol"], name=c["name"], exchange=c.get("exchange", "NSE"),
            sector=c.get("sector"), industry=c.get("industry"),
            currency=c.get("currency", "INR"), market_cap=c.get("market_cap"),
            aliases=c.get("aliases", []), description=c.get("description"),
        )

    # ── price simulation ─────────────────────────────────────────────────────
    def _seed_cfg(self, company: Company) -> dict:
        snap = self._snapshots.get(company.symbol.upper())
        if snap and "price_seed" in snap:
            return snap["price_seed"]
        # default seed for unknown symbols
        return {"start_price": 500, "annual_drift": 0.10, "annual_vol": 0.30,
                "days": 400, "beta": 1.0, "events": []}

    def _simulate(self, company: Company):
        sym = company.symbol.upper()
        if sym in self._sim_cache:
            return self._sim_cache[sym]

        cfg = self._seed_cfg(company)
        # stable, process-independent seed — Python's hash() is salted per run,
        # which would make the simulated series (and thus scores) non-reproducible.
        seed = int.from_bytes(hashlib.sha256(sym.encode()).digest()[:4], "big")
        rng = np.random.default_rng(seed)

        n = int(cfg.get("days", 400))
        dd = cfg.get("annual_drift", 0.10) / TRADING_DAYS
        dv = cfg.get("annual_vol", 0.30) / np.sqrt(TRADING_DAYS)
        beta = cfg.get("beta", 1.0)

        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)

        # market factor
        m_ret = rng.normal(0.06 / TRADING_DAYS, 0.14 / np.sqrt(TRADING_DAYS), n)
        # sector = market-correlated + own idiosyncratic
        s_ret = 0.9 * m_ret + rng.normal(0.02 / TRADING_DAYS, 0.10 / np.sqrt(TRADING_DAYS), n)
        # stock = beta*market + alpha noise
        i_ret = beta * m_ret + rng.normal(dd, dv, n)

        vol_base = rng.lognormal(mean=np.log(500_000), sigma=0.35, size=n)
        vol_mult = np.ones(n)

        # inject engineered events — map calendar days_ago to the nearest trading
        # day so the price shock lines up with the news/corporate-action dates
        # (which also use calendar days_ago), letting attribution find them.
        today = pd.Timestamp.today().normalize()
        for ev in cfg.get("events", []):
            target = today - timedelta(days=int(ev.get("days_ago", 0)))
            idx = int(dates.get_indexer([target], method="nearest")[0])
            if not (0 <= idx < n):
                continue
            mag = ev.get("magnitude_pct", 0.0) / 100.0
            kind = ev.get("kind", "")
            if kind == "sector":
                # common shock: shows up in sector & market → low stock-specific alpha
                s_ret[idx] += mag
                m_ret[idx] += mag * 0.6
                i_ret[idx] += beta * mag * 0.6 + mag * 0.3
            else:
                # stock-specific shock → high alpha
                i_ret[idx] += mag
            vol_mult[idx] += abs(mag) * 12.0  # surge scales with move size

        def _to_ohlcv(returns, start, volume=None):
            close = start * np.cumprod(1.0 + returns)
            openp = np.empty_like(close)
            openp[0] = start
            openp[1:] = close[:-1]
            intraday = np.abs(rng.normal(0, dv * 0.6, len(close))) * close
            high = np.maximum(openp, close) + intraday
            low = np.minimum(openp, close) - intraday
            low = np.clip(low, 1e-6, None)
            df = pd.DataFrame(
                {"open": openp, "high": high, "low": low, "close": close},
                index=dates,
            )
            if volume is not None:
                df["volume"] = np.round(volume).astype("int64")
            return df

        stock = _to_ohlcv(i_ret, cfg.get("start_price", 500), vol_base * vol_mult)
        # Anchor the simulated series to the snapshot's stated price so the
        # technical view and the valuation view quote the same last price.
        snap = self._snapshots.get(sym)
        target = (snap or {}).get("fundamentals", {}).get("price")
        if target:
            scale = float(target) / float(stock["close"].iloc[-1])
            for col in ("open", "high", "low", "close"):
                stock[col] *= scale
        nifty = _to_ohlcv(m_ret, 22000.0)
        nifty["volume"] = 0
        sector = _to_ohlcv(s_ret, 10000.0)
        sector["volume"] = 0

        out = (stock, {"NIFTY": nifty, "SECTOR": sector})
        self._sim_cache[sym] = out
        return out

    def prices(self, company: Company) -> Optional[PriceHistory]:
        stock, _ = self._simulate(company)
        return PriceHistory(symbol=company.symbol, frame=stock, source=self.name)

    def benchmarks(self, company: Company) -> dict[str, PriceHistory]:
        _, benches = self._simulate(company)
        return {
            k: PriceHistory(symbol=k, frame=v, source=self.name)
            for k, v in benches.items()
        }

    # ── fundamentals / ownership / qualitative from snapshots ─────────────────
    def fundamentals(self, company: Company) -> Optional[Fundamentals]:
        snap = self._snapshots.get(company.symbol.upper())
        if not snap or "fundamentals" not in snap:
            return None
        f = snap["fundamentals"]
        stmts = [FinancialStatement(**{k: v for k, v in s.items()}) for s in f["statements"]]
        return Fundamentals(
            symbol=company.symbol, statements=stmts, price=f.get("price"),
            shares_outstanding=f.get("shares_outstanding"), source=self.name,
        )

    def ownership(self, company: Company) -> Optional[Ownership]:
        snap = self._snapshots.get(company.symbol.upper())
        if not snap or "ownership" not in snap:
            return None
        o = snap["ownership"]
        hist = [ShareholdingSnapshot(**s) for s in o.get("history", [])]
        return Ownership(
            symbol=company.symbol, history=hist,
            bulk_block_deals=o.get("bulk_block_deals", []), source=self.name,
        )

    def _days_ago(self, days: int) -> date:
        return (pd.Timestamp.today().normalize() - timedelta(days=int(days))).date()

    def news(self, company: Company) -> list[NewsItem]:
        snap = self._snapshots.get(company.symbol.upper())
        if not snap:
            return []
        return [
            NewsItem(date=self._days_ago(n["days_ago"]), headline=n["headline"],
                     summary=n.get("summary", ""), source=n.get("source", "illustrative"))
            for n in snap.get("news", [])
        ]

    def corporate_actions(self, company: Company) -> list[CorporateAction]:
        snap = self._snapshots.get(company.symbol.upper())
        if not snap:
            return []
        return [
            CorporateAction(date=self._days_ago(a["days_ago"]), kind=a["kind"],
                            detail=a.get("detail", ""))
            for a in snap.get("corporate_actions", [])
        ]

    def earnings_calls(self, company: Company) -> list[EarningsCall]:
        snap = self._snapshots.get(company.symbol.upper())
        if not snap:
            return []
        return [
            EarningsCall(period=e["period"], date=self._days_ago(e.get("days_ago", 0)),
                         transcript=e.get("transcript", ""), source="illustrative")
            for e in snap.get("earnings_calls", [])
        ]

    def peers(self, company: Company) -> list[str]:
        snap = self._snapshots.get(company.symbol.upper())
        return snap.get("peers", []) if snap else []

    # for the resolver / dashboard: list what we ship
    def catalogue(self) -> list[Company]:
        return [self._company(s) for s in sorted(self._snapshots)]
