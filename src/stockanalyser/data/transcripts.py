"""Real earnings-call transcript ingestion.

The qualitative lens analyses whatever text sits in ``CompanyData.earnings_calls``
— so ingesting *real* transcripts is a sourcing problem, not an analysis one. Two
sources, both optional and both degrading to "nothing" rather than failing:

* **Local files** — drop transcript text in a directory (the common analyst
  workflow: you already have the concall PDF/text). Layout is either
  ``<root>/<SYMBOL>/<PERIOD>.txt`` or flat ``<root>/<SYMBOL>_<PERIOD>.txt``; the
  period is read from the filename and the date from a leading ``Date:`` line or
  the file mtime.
* **FMP API** — Financial Modeling Prep's transcript endpoint, used when
  ``FMP_API_KEY`` is set. The JSON→model mapping is a pure, unit-tested function;
  the HTTP call is a thin wrapper.

Real transcripts, when found, replace the bundled illustrative samples.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ..models import Company, EarningsCall

_TEXT_EXT = {".txt", ".md", ".text"}
_DATE_RE = re.compile(r"^\s*date\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE | re.MULTILINE)


def ingest_transcripts(company: Company, config) -> list[EarningsCall]:
    """Best-effort: local directory first, then the FMP API when keyed. Returns []
    when nothing is configured or found — never raises into the fetch path."""
    calls: list[EarningsCall] = []
    root = getattr(config, "transcripts_dir", None) or os.environ.get("STOCKANALYSER_TRANSCRIPTS")
    if root:
        try:
            calls = load_local_transcripts(root, company)
        except Exception:
            calls = []
    if not calls and os.environ.get("FMP_API_KEY"):
        try:
            calls = FMPTranscriptProvider().fetch(company)
        except Exception:
            calls = []
    return calls


# ── local files ──────────────────────────────────────────────────────────────
def load_local_transcripts(root: str | Path, company: Company) -> list[EarningsCall]:
    root = Path(root)
    if not root.exists():
        return []
    sym = company.symbol.upper()
    files: list[Path] = []
    subdir = root / company.symbol
    if subdir.is_dir():
        files += [p for p in subdir.iterdir() if p.suffix.lower() in _TEXT_EXT]
    for p in root.iterdir():
        if p.is_file() and p.suffix.lower() in _TEXT_EXT and p.stem.upper().startswith(sym):
            files.append(p)

    calls: list[EarningsCall] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if not text:
            continue
        calls.append(EarningsCall(
            period=_period_from_name(p, sym),
            date=_date_from(text, p),
            transcript=text,
            source=f"local:{p.name}"))
    # oldest → newest, so the lens reads calls[-1] as the latest and calls[-2] for drift
    calls.sort(key=lambda c: (c.date or date.min, c.period))
    return calls


def _period_from_name(path: Path, sym: str) -> str:
    stem = path.stem
    up = stem.upper()
    if up.startswith(sym):
        rest = stem[len(sym):].lstrip("_-. ")
        return rest or stem
    return stem


def _date_from(text: str, path: Path) -> Optional[date]:
    m = _DATE_RE.search(text[:400])
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


# ── FMP API ──────────────────────────────────────────────────────────────────
def parse_fmp_transcripts(payload, limit: int = 8) -> list[EarningsCall]:
    """Map FMP earning-call-transcript JSON into EarningsCall objects. Accepts a
    single object or a list; tolerates missing fields; newest last, capped at `limit`."""
    if payload is None:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    calls: list[EarningsCall] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        content = r.get("content") or r.get("transcript")
        if not content:
            continue
        yr, q = r.get("year"), r.get("quarter")
        calls.append(EarningsCall(
            period=_fmp_period(q, yr),
            date=_fmp_date(r.get("date")),
            transcript=str(content),
            source="fmp"))
    calls.sort(key=lambda c: (c.date or date.min, c.period))
    return calls[-limit:]


def _fmp_period(quarter, year) -> str:
    try:
        q = f"Q{int(quarter)}" if quarter is not None else ""
    except (TypeError, ValueError):
        q = str(quarter) if quarter else ""
    if year is not None:
        yy = str(year)[-2:]
        return f"{q}FY{yy}" if q else f"FY{yy}"
    return q or "transcript"


def _fmp_date(raw) -> Optional[date]:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).split(" ")[0])
    except ValueError:
        return None


class FMPTranscriptProvider:
    """Earnings-call transcripts from Financial Modeling Prep (needs FMP_API_KEY)."""
    name = "fmp"
    BASE = "https://financialmodelingprep.com"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("FMP_API_KEY")

    def available(self) -> bool:
        try:
            import requests  # noqa
        except Exception:
            return False
        return bool(self.api_key)

    def fetch(self, company: Company, limit: int = 8) -> list[EarningsCall]:
        if not self.available():
            return []
        import requests
        out: list[EarningsCall] = []
        this_year = datetime.utcnow().year
        for yr in (this_year, this_year - 1):
            try:
                r = requests.get(
                    f"{self.BASE}/api/v4/batch_earning_call_transcript/{company.symbol}",
                    params={"year": yr, "apikey": self.api_key}, timeout=25)
                r.raise_for_status()
                out += parse_fmp_transcripts(r.json())
            except Exception:
                continue
        out.sort(key=lambda c: (c.date or date.min, c.period))
        return out[-limit:]
