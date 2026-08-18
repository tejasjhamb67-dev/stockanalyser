"""Coverage memory — the agent's track record.

An analyst who *covers* a name remembers the last call and is accountable for it.
This persists, per symbol, a small record of each initiation/update — the rating,
target, thesis anchors and model growth — and diffs a fresh run against the prior
one to produce the coverage note: an initiation, or an update that says exactly
what changed (rating moves, target revisions, thesis drift).

Storage is plain JSON per symbol under a store directory (one file, newest last),
so it is inspectable and trivially portable. All I/O is defensive: a read-only or
missing store degrades to "memory unavailable", never a crash in the research path.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def default_store() -> Path:
    return Path.home() / ".stockanalyser" / "coverage"


@dataclass
class CoverageEntry:
    symbol: str
    name: str
    date: str
    side: str
    market: str
    rating: str
    conviction: str
    target: float | None
    upside_pct: float | None
    composite: float | None
    verdict: str
    base_growth: float | None
    gate: str
    monitorables: list[str] = field(default_factory=list)
    # persisted forward estimates, so the next run can compute revisions
    est_rev_fy1: float | None = None
    est_ebitda_fy1: float | None = None
    est_eps_fy1: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CoverageEntry":
        known = {k: d.get(k) for k in cls.__dataclass_fields__}
        return cls(**known)


class CoverageMemory:
    """A tiny JSON-backed store of per-symbol coverage history."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_store()

    def _path(self, symbol: str) -> Path:
        safe = "".join(c for c in symbol.upper() if c.isalnum() or c in "._-")
        return self.root / f"{safe}.json"

    def history(self, symbol: str) -> list[CoverageEntry]:
        p = self._path(symbol)
        if not p.exists():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return [CoverageEntry.from_dict(d) for d in raw]
        except (json.JSONDecodeError, OSError, TypeError):
            return []

    def load(self, symbol: str) -> CoverageEntry | None:
        hist = self.history(symbol)
        return hist[-1] if hist else None

    def record(self, entry: CoverageEntry) -> bool:
        """Append an entry; returns False if the store isn't writable (never raises)."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            hist = self.history(entry.symbol)
            hist.append(entry)
            self._path(entry.symbol).write_text(
                json.dumps([e.to_dict() for e in hist], indent=2), encoding="utf-8")
            return True
        except OSError:
            return False


def now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def coverage_note(prev: CoverageEntry | None, new: CoverageEntry) -> str:
    """Human-readable initiation/update line comparing the prior call to this one."""
    if prev is None:
        return f"INITIATING COVERAGE — {new.rating} ({new.side}), first call on record."

    parts: list[str] = [f"UPDATE (prior call {prev.date})"]
    if prev.rating != new.rating:
        parts.append(f"rating {prev.rating} → {new.rating}")
    else:
        parts.append(f"rating maintained at {new.rating}")

    if prev.target is not None and new.target is not None:
        delta = new.target - prev.target
        pct = (delta / prev.target * 100) if prev.target else 0.0
        if abs(pct) >= 1:
            parts.append(f"target {prev.target:,.0f} → {new.target:,.0f} ({pct:+.0f}%)")
        else:
            parts.append(f"target unchanged (~{new.target:,.0f})")

    # thesis drift: monitorables that appeared or dropped since last time
    old_m, new_m = set(prev.monitorables), set(new.monitorables)
    added = new_m - old_m
    dropped = old_m - new_m
    if added:
        parts.append(f"{len(added)} new monitorable(s)")
    if dropped:
        parts.append(f"{len(dropped)} resolved/dropped")
    return " · ".join(parts) + "."
