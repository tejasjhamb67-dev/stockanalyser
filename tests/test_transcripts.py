"""Tests for real earnings-call transcript ingestion (local files + FMP parser),
and the end-to-end override of the bundled samples. Offline, no network."""
from __future__ import annotations

from stockanalyser.config import Config
from stockanalyser.models import Company
from stockanalyser.data.transcripts import (
    load_local_transcripts, parse_fmp_transcripts, ingest_transcripts,
)
from stockanalyser.agent import research

CFG = Config(provider="offline", use_llm=False)
ACME = Company(symbol="ACME", name="Acme Corp")


# ── local files ──────────────────────────────────────────────────────────────
def test_load_local_flat_layout(tmp_path):
    (tmp_path / "ACME_Q3FY24.txt").write_text("Date: 2024-01-15\nSolid quarter, strong demand.")
    (tmp_path / "ACME_Q4FY24.txt").write_text("Date: 2024-04-20\nRecord margins, robust growth.")
    (tmp_path / "OTHER_Q1.txt").write_text("not acme")
    calls = load_local_transcripts(tmp_path, ACME)
    assert [c.period for c in calls] == ["Q3FY24", "Q4FY24"]     # sorted oldest→newest by date
    assert str(calls[0].date) == "2024-01-15"
    assert calls[-1].source.startswith("local:")
    assert "Record margins" in calls[-1].transcript


def test_load_local_subdir_layout(tmp_path):
    d = tmp_path / "ACME"
    d.mkdir()
    (d / "Q1FY25.md").write_text("Guidance raised for the coming year.")
    calls = load_local_transcripts(tmp_path, ACME)
    assert len(calls) == 1 and calls[0].period == "Q1FY25"


def test_load_local_missing_dir_is_empty(tmp_path):
    assert load_local_transcripts(tmp_path / "nope", ACME) == []


def test_ingest_uses_config_dir(tmp_path):
    (tmp_path / "ACME_Q4FY24.txt").write_text("Strong demand and healthy margins.")
    calls = ingest_transcripts(ACME, Config(transcripts_dir=str(tmp_path)))
    assert len(calls) == 1 and calls[0].source.startswith("local:")


# ── FMP parser ───────────────────────────────────────────────────────────────
def test_parse_fmp_transcripts_shape():
    payload = [
        {"symbol": "AAPL", "quarter": 3, "year": 2024, "date": "2024-08-01 17:00:00",
         "content": "Older call, cautious tone."},
        {"symbol": "AAPL", "quarter": 4, "year": 2024, "date": "2024-11-01",
         "content": "Newer call, record revenue."},
    ]
    calls = parse_fmp_transcripts(payload)
    assert [c.period for c in calls] == ["Q3FY24", "Q4FY24"]     # newest last
    assert str(calls[-1].date) == "2024-11-01" and calls[-1].source == "fmp"


def test_parse_fmp_single_and_empty():
    one = parse_fmp_transcripts({"quarter": 1, "year": 2025, "content": "hi"})
    assert len(one) == 1 and one[0].period == "Q1FY25"
    assert parse_fmp_transcripts([{"quarter": 1, "year": 2025}]) == []   # no content -> skipped
    assert parse_fmp_transcripts(None) == []


# ── end-to-end: real transcript overrides the bundled sample ─────────────────
def test_research_ingests_local_transcript(tmp_path):
    # a deliberately bearish transcript with a red-flag phrase
    (tmp_path / "RELIANCE_Q4FY24.txt").write_text(
        "Date: 2024-05-01\nThis was a challenging quarter. Demand was weak and margins "
        "faced pressure amid a challenging environment, with a decline in volumes and "
        "delayed client payments.")
    cfg = Config(provider="offline", use_llm=False, transcripts_dir=str(tmp_path))
    out = research("RELIANCE", depth="L2", config=cfg)
    q = out.lenses["Qualitative"]
    assert q.data["source"].startswith("local:")          # not the bundled sample
    assert q.data["sentiment"] < 0                          # bearish tone detected
    assert q.data["red_flags"]                              # red-flag phrase caught


def test_research_without_transcripts_dir_uses_sample():
    out = research("RELIANCE", depth="L2", config=CFG)
    # bundled illustrative sample still flows when nothing is configured
    assert out.lenses["Qualitative"].has_score
