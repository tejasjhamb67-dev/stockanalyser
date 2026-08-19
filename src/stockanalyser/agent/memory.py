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
import os
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


class SqlCoverageMemory:
    """A database-backed coverage store (SQLAlchemy), so coverage survives across
    an app's restarts and instances — the JSON store's ephemeral-disk problem on a
    PaaS. Works with any SQLAlchemy URL: SQLite locally, Postgres in production.

    Each call is one row (symbol + the full CoverageEntry as JSON), so the schema
    never needs migrating when a field is added. Same interface as CoverageMemory —
    history / load / record — and just as defensive (reads degrade to [], a failed
    write returns False)."""

    def __init__(self, url: str) -> None:
        from sqlalchemy import (Column, Integer, MetaData, String, Table, Text,
                                create_engine)
        self.engine = create_engine(_normalize_db_url(url), future=True, pool_pre_ping=True)
        self.meta = MetaData()
        self.table = Table(
            "coverage", self.meta,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("symbol", String(64), index=True, nullable=False),
            Column("created_at", String(40)),
            Column("entry", Text, nullable=False),
        )
        self.meta.create_all(self.engine)

    def history(self, symbol: str) -> list[CoverageEntry]:
        from sqlalchemy import select
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    select(self.table.c.entry)
                    .where(self.table.c.symbol == symbol.upper())
                    .order_by(self.table.c.id)).all()
            return [CoverageEntry.from_dict(json.loads(r[0])) for r in rows]
        except Exception:
            return []

    def load(self, symbol: str) -> CoverageEntry | None:
        hist = self.history(symbol)
        return hist[-1] if hist else None

    def record(self, entry: CoverageEntry) -> bool:
        from sqlalchemy import insert
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(self.table).values(
                    symbol=entry.symbol.upper(),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    entry=json.dumps(entry.to_dict())))
            return True
        except Exception:
            return False


def _normalize_db_url(url: str) -> str:
    """Accept the common Postgres URL shapes and pin the psycopg (v3) driver."""
    if url.startswith("postgres://"):          # Heroku/Render legacy scheme
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def open_coverage_memory(store: str | Path | None = None):
    """Pick a coverage backend. A SQLAlchemy URL (``sqlite:///…`` / ``postgresql://…``)
    — passed explicitly or via ``$COVERAGE_DATABASE_URL`` / ``$DATABASE_URL`` when no
    store is given — selects the database store; anything else is the JSON directory
    store. So `CoverageMemory` stays the zero-config default for local/CLI use, and a
    deployment just sets a database URL."""
    url: str | None = None
    if store is not None and "://" in str(store):
        url = str(store)
    elif store is None:
        url = os.environ.get("COVERAGE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if url:
        return SqlCoverageMemory(url)
    return CoverageMemory(store)


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
