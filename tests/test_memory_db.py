"""Tests for database-backed coverage memory (SQLite, via SQLAlchemy).

The Postgres path is the same code on a different URL; here we exercise SQLite
(file-backed, no network) plus the backend-selection factory and an end-to-end
initiation→update across two runs persisted to a database.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy", reason="install the [db] extra to run DB tests")

from stockanalyser.config import Config
from stockanalyser.agent import research
from stockanalyser.agent.memory import (
    CoverageEntry, CoverageMemory, SqlCoverageMemory, coverage_note,
    open_coverage_memory,
)

CFG = Config(provider="offline", use_llm=False)


def _entry(symbol="ACME", rating="Buy", target=100.0, monitors=("watch margins",)):
    return CoverageEntry(symbol=symbol, name="Acme", date="2026-01-01", side="sell-side",
                         market="IN", rating=rating, conviction="Moderate", target=target,
                         upside_pct=10.0, composite=70.0, verdict="Buy", base_growth=0.2,
                         gate="pass", monitorables=list(monitors),
                         est_rev_fy1=1000.0, est_ebitda_fy1=200.0, est_eps_fy1=5.0)


def _url(tmp_path):
    return f"sqlite:///{tmp_path}/coverage.db"


# ── the SQL store ────────────────────────────────────────────────────────────
def test_sql_record_and_reload(tmp_path):
    mem = SqlCoverageMemory(_url(tmp_path))
    assert mem.load("ACME") is None
    assert mem.record(_entry()) is True
    back = mem.load("ACME")
    assert back is not None and back.rating == "Buy" and back.target == 100.0
    assert back.est_rev_fy1 == 1000.0 and back.monitorables == ["watch margins"]


def test_sql_persists_across_instances(tmp_path):
    SqlCoverageMemory(_url(tmp_path)).record(_entry())
    # a brand-new instance (fresh engine) sees the persisted row
    hist = SqlCoverageMemory(_url(tmp_path)).history("ACME")
    assert len(hist) == 1 and hist[0].rating == "Buy"


def test_sql_history_is_ordered_and_diffable(tmp_path):
    mem = SqlCoverageMemory(_url(tmp_path))
    mem.record(_entry(rating="Buy", target=100.0, monitors=("A", "B")))
    mem.record(_entry(rating="Sell", target=80.0, monitors=("B", "C")))
    hist = mem.history("ACME")
    assert [e.rating for e in hist] == ["Buy", "Sell"]
    note = coverage_note(hist[-2], hist[-1])
    assert "Buy → Sell" in note and "100" in note and "80" in note


def test_sql_case_insensitive_symbol(tmp_path):
    mem = SqlCoverageMemory(_url(tmp_path))
    mem.record(_entry(symbol="Acme"))
    assert mem.load("ACME") is not None       # stored upper-cased, queried upper-cased


# ── the factory ──────────────────────────────────────────────────────────────
def test_factory_selects_sql_for_url(tmp_path):
    assert isinstance(open_coverage_memory(_url(tmp_path)), SqlCoverageMemory)


def test_factory_selects_json_for_path(tmp_path):
    assert isinstance(open_coverage_memory(str(tmp_path)), CoverageMemory)


def test_factory_reads_env_database_url(tmp_path, monkeypatch):
    monkeypatch.setenv("COVERAGE_DATABASE_URL", _url(tmp_path))
    assert isinstance(open_coverage_memory(None), SqlCoverageMemory)


def test_factory_normalizes_postgres_scheme(monkeypatch):
    # postgres:// and postgresql:// both pin the psycopg driver (no DB contact here)
    from stockanalyser.agent.memory import _normalize_db_url
    assert _normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert _normalize_db_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


# ── end-to-end through the agent, persisted to a database ────────────────────
def test_research_persists_to_database(tmp_path):
    url = _url(tmp_path)
    out1 = research("RELIANCE", side="sell-side", depth="L4", config=CFG, coverage_store=url)
    assert out1.coverage_note.startswith("INITIATING")
    out2 = research("RELIANCE", side="sell-side", depth="L4", config=CFG, coverage_store=url)
    assert out2.coverage_note.startswith("UPDATE")
    # the database now holds both calls
    assert len(SqlCoverageMemory(url).history("RELIANCE")) == 2
