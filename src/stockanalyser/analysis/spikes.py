"""Spike detection + attribution — the lens that explains *why* a stock moved.

Pipeline:
  1. Detect abnormal days (rolling z-score of log-returns + volume surge + gaps).
  2. Decompose each move into market-beta / sector / stock-specific *alpha*, so a
     pop that merely tracked the sector is not mistaken for a company story.
  3. Attribute the residual alpha to ranked candidate causes found in a window
     around the day — results dates, corporate actions, news, earnings calls,
     bulk/block deals — each with an evidence note and a confidence weight.
  4. Report a primary attribution per spike, or 'unexplained' when evidence is thin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from ..config import SpikeConfig
from ..models import CompanyData, LensResult, Signal


@dataclass
class Attribution:
    cause: str
    weight: float
    evidence: str


@dataclass
class Spike:
    date: pd.Timestamp
    ret_pct: float
    zscore: float
    volume_z: float
    gap_pct: float
    market_ret_pct: float
    sector_ret_pct: float
    alpha_pct: float                 # stock-specific residual
    kind: str                        # gap-up / gap-down / breakout / distribution ...
    attributions: list[Attribution] = field(default_factory=list)

    @property
    def primary(self) -> Optional[Attribution]:
        return self.attributions[0] if self.attributions else None

    @property
    def explained(self) -> bool:
        return bool(self.attributions) and self.attributions[0].weight >= 0.35


def _beta(stock_ret: pd.Series, mkt_ret: pd.Series) -> float:
    aligned = pd.concat([stock_ret, mkt_ret], axis=1).dropna()
    if len(aligned) < 30:
        return 1.0
    cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    var = cov[1, 1]
    return float(cov[0, 1] / var) if var > 0 else 1.0


def detect_spikes(data: CompanyData, cfg: SpikeConfig) -> list[Spike]:
    df = data.prices.frame
    close = df["close"]
    logret = np.log(close / close.shift(1))
    ret_pct = close.pct_change() * 100

    lookback = min(cfg.lookback, len(logret) - 1)
    roll_mean = logret.rolling(lookback, min_periods=30).mean()
    roll_std = logret.rolling(lookback, min_periods=30).std()
    z = (logret - roll_mean) / roll_std

    vol_z = _volume_z(df)
    gap = (df["open"] / close.shift(1) - 1) * 100

    # market / sector returns aligned to the stock's dates
    mkt = _bench_returns(data, ("NIFTY", "SPX", "SENSEX"))
    sec = _bench_returns(data, ("SECTOR",))
    beta = _beta(logret, np.log1p(mkt / 100)) if mkt is not None else 1.0

    spikes: list[Spike] = []
    for dt in df.index:
        zz = z.get(dt, np.nan)
        rr = ret_pct.get(dt, np.nan)
        if np.isnan(zz) or np.isnan(rr):
            continue
        if abs(zz) < cfg.return_sigma or abs(rr) < cfg.min_abs_return:
            continue
        m = float(mkt.get(dt, 0.0)) if mkt is not None else 0.0
        s = float(sec.get(dt, 0.0)) if sec is not None else 0.0
        alpha = rr - beta * m
        gp = float(gap.get(dt, 0.0))
        spikes.append(Spike(
            date=dt, ret_pct=round(rr, 2), zscore=round(float(zz), 2),
            volume_z=round(float(vol_z.get(dt, 0.0)), 2), gap_pct=round(gp, 2),
            market_ret_pct=round(m, 2), sector_ret_pct=round(s, 2),
            alpha_pct=round(alpha, 2), kind=_classify(rr, gp, alpha, float(vol_z.get(dt, 0.0))),
        ))
    return spikes


def _classify(rr: float, gap: float, alpha: float, vol_z: float) -> str:
    if gap > 2 and rr > 0:
        return "gap-up"
    if gap < -2 and rr < 0:
        return "gap-down"
    if rr > 0 and vol_z > 2:
        return "accumulation breakout"
    if rr < 0 and vol_z > 2:
        return "distribution"
    return "momentum surge" if rr > 0 else "sharp fall"


def _volume_z(df: pd.DataFrame, window: int = 20) -> pd.Series:
    v = df["volume"].astype(float)
    mean = v.rolling(window, min_periods=5).mean()
    std = v.rolling(window, min_periods=5).std().replace(0, np.nan)
    return ((v - mean) / std).fillna(0.0)


def _bench_returns(data: CompanyData, names) -> Optional[pd.Series]:
    for nm in names:
        bh = data.benchmarks.get(nm)
        if bh is not None and len(bh.frame) > 5:
            r = bh.frame["close"].pct_change() * 100
            return r.reindex(data.prices.frame.index)
    return None


def attribute(spike: Spike, data: CompanyData, cfg: SpikeConfig) -> None:
    """Fill spike.attributions with ranked candidate causes."""
    window = timedelta(days=cfg.event_window + 2)
    d = spike.date.date()
    cand: list[Attribution] = []

    # 1. corporate actions (results are the single strongest same-day cause)
    for ca in data.corporate_actions:
        if abs((ca.date - d).days) <= cfg.event_window:
            w = 0.9 if ca.kind == "results" else 0.55
            cand.append(Attribution(
                cause=f"Corporate action: {ca.kind}", weight=w,
                evidence=f"{ca.kind} on {ca.date} ({ca.detail})"))

    # 2. earnings calls near the move
    for ec in data.earnings_calls:
        if ec.date and abs((ec.date - d).days) <= cfg.event_window:
            cand.append(Attribution(
                cause=f"Earnings call ({ec.period})", weight=0.6,
                evidence=f"Concall on {ec.date} — check guidance/tone"))

    # 3. news flow
    for nw in data.news:
        if abs((nw.date - d).days) <= cfg.event_window:
            direction = "positive" if spike.ret_pct > 0 else "negative"
            cand.append(Attribution(
                cause="News flow", weight=0.5,
                evidence=f"[{nw.date}] {nw.headline}"))

    # 4. bulk/block deals (from ownership)
    if data.ownership:
        for deal in data.ownership.bulk_block_deals:
            try:
                deal_date = (pd.Timestamp.today().normalize() - timedelta(days=int(deal.get("days_ago", 0)))).date()
            except Exception:
                continue
            if abs((deal_date - d).days) <= cfg.event_window:
                cand.append(Attribution(
                    cause="Bulk/Block deal", weight=0.55,
                    evidence=f"{deal.get('action','?')} by {deal.get('party','?')} (~{deal.get('qty_pct','?')}% of equity)"))

    # 5. sector/market — only if the stock-specific alpha is small
    move_from_market = spike.ret_pct - spike.alpha_pct
    if abs(spike.alpha_pct) < abs(spike.ret_pct) * 0.4 and abs(move_from_market) > 1.5:
        cand.append(Attribution(
            cause="Sector / market move", weight=0.75,
            evidence=(f"Only {spike.alpha_pct:+.1f}% was stock-specific; "
                      f"~{move_from_market:+.1f}% came from market/sector "
                      f"(index {spike.market_ret_pct:+.1f}%, sector {spike.sector_ret_pct:+.1f}%)")))

    # rank; if the move is clearly stock-specific, upweight company events
    if abs(spike.alpha_pct) >= abs(spike.ret_pct) * 0.6:
        for c in cand:
            if c.cause.startswith(("Corporate", "Earnings", "News", "Bulk")):
                c.weight = min(1.0, c.weight + 0.1)

    cand.sort(key=lambda a: a.weight, reverse=True)
    if not cand:
        cand.append(Attribution(
            cause="Unexplained", weight=0.2,
            evidence="No results/news/deal/sector event found in the window — "
                     "flag for manual review (rumour, derivative expiry, delivery-based buying?)"))
    spike.attributions = cand


def analyse(data: CompanyData, cfg: SpikeConfig | None = None) -> LensResult:
    cfg = cfg or SpikeConfig()
    res = LensResult(lens="Spike")
    if data.prices is None or len(data.prices.frame) < 60:
        res.summary = "Insufficient history for spike attribution."
        return res

    spikes = detect_spikes(data, cfg)
    for sp in spikes:
        attribute(sp, data, cfg)

    res.data["spikes"] = [
        {
            "date": str(sp.date.date()), "ret_pct": sp.ret_pct, "zscore": sp.zscore,
            "volume_z": sp.volume_z, "gap_pct": sp.gap_pct, "alpha_pct": sp.alpha_pct,
            "market_ret_pct": sp.market_ret_pct, "sector_ret_pct": sp.sector_ret_pct,
            "kind": sp.kind,
            "primary_cause": sp.primary.cause if sp.primary else "Unexplained",
            "confidence": round(sp.primary.weight, 2) if sp.primary else 0.0,
            "evidence": sp.primary.evidence if sp.primary else "",
            "all_causes": [{"cause": a.cause, "weight": round(a.weight, 2), "evidence": a.evidence}
                           for a in sp.attributions],
        }
        for sp in spikes
    ]

    signals: list[Signal] = []
    for sp in spikes[-6:][::-1]:
        stance = "bullish" if sp.ret_pct > 0 else "bearish"
        signals.append(Signal(
            name=f"{sp.date.date()}  {sp.ret_pct:+.1f}%  [{sp.kind}]",
            value=f"α {sp.alpha_pct:+.1f}%",
            interpretation=f"{sp.primary.cause} — {sp.primary.evidence}" if sp.primary else "unexplained",
            stance=stance if sp.explained else "warning",
            confidence=sp.primary.weight if sp.primary else 0.2,
        ))
    res.signals = signals

    n = len(spikes)
    explained = sum(1 for s in spikes if s.explained)
    ups = [s for s in spikes if s.ret_pct > 0]
    downs = [s for s in spikes if s.ret_pct < 0]
    # score: reward well-explained, alpha-positive, volume-backed accumulation
    if n == 0:
        res.score = 55.0
        res.summary = "No abnormal price spikes detected in the window — quiet, range-bound tape."
        return res

    accum = sum(1 for s in ups if s.volume_z > 1.5)
    distrib = sum(1 for s in downs if s.volume_z > 1.5)
    bias = (accum - distrib) / max(n, 1)
    res.score = round(float(np.clip(55 + bias * 45, 5, 95)), 1)
    res.summary = (
        f"Detected {n} abnormal move(s); {explained}/{n} attributable to a concrete "
        f"event. {len(ups)} up / {len(downs)} down. "
        f"{accum} volume-backed accumulation vs {distrib} distribution day(s). "
        + (f"Most recent: {spikes[-1].date.date()} {spikes[-1].ret_pct:+.1f}% → "
           f"{spikes[-1].primary.cause}." if spikes and spikes[-1].primary else "")
    )
    return res
