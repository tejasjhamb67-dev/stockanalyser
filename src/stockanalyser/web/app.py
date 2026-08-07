"""FastAPI web application wrapping the analysis engine.

Routes
  GET  /                      landing page with search
  GET  /analyse?q=&provider=  full HTML dashboard for a company
  GET  /framework             the analytical model, rendered from FRAMEWORK.md
  GET  /api/analyse?q=        JSON report (machine-readable)
  GET  /api/suggest?q=        name/ticker autocomplete over bundled companies
  GET  /healthz               liveness probe

The engine is provider-pluggable; the site defaults to `auto` (live when
available, bundled snapshots otherwise) so it always returns something.
"""
from __future__ import annotations

import functools
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ..config import Config
from ..data.offline import OfflineProvider
from ..report import (
    CompanyNotFound,
    build_report,
    render_dashboard,
    report_to_dict,
)
from . import pages
from . import md as _md

app = FastAPI(
    title="stockanalyser",
    description="Multi-lens equity analysis — name in, framework + dashboard out.",
    version="0.1.0",
    docs_url="/docs",
)

_OFFLINE = OfflineProvider()
_DEFAULT_PROVIDER = "auto"
_FRAMEWORK_MD = Path(__file__).resolve().parents[3] / "docs" / "FRAMEWORK.md"


def _samples():
    return _OFFLINE.catalogue()


@functools.lru_cache(maxsize=256)
def _cached_report_html(query: str, provider: str) -> tuple[str, int]:
    """Cache rendered dashboards. Returns (html, status)."""
    cfg = Config.default()
    cfg.provider = provider
    try:
        report = build_report(query, cfg)
    except CompanyNotFound as exc:
        return pages.error_page(query, str(exc), _samples()), 404
    html = render_dashboard(report, nav_html=pages.nav_bar(query))
    return html, 200


@functools.lru_cache(maxsize=256)
def _cached_report_json(query: str, provider: str):
    cfg = Config.default()
    cfg.provider = provider
    report = build_report(query, cfg)
    return report_to_dict(report)


@app.get("/", response_class=HTMLResponse)
def index():
    return pages.landing_page(_samples())


@app.get("/analyse", response_class=HTMLResponse)
def analyse(q: str = Query(..., min_length=1, description="Company name or ticker"),
            provider: str = Query(_DEFAULT_PROVIDER)):
    html, status = _cached_report_html(q.strip(), provider)
    return HTMLResponse(html, status_code=status)


@app.get("/framework", response_class=HTMLResponse)
def framework():
    if _FRAMEWORK_MD.exists():
        body = _md.render(_FRAMEWORK_MD.read_text(encoding="utf-8"))
    else:
        body = "<p>Framework document not found.</p>"
    return pages.framework_page(body, _samples())


@app.get("/api/analyse")
def api_analyse(q: str = Query(..., min_length=1), provider: str = Query(_DEFAULT_PROVIDER)):
    try:
        return JSONResponse(_cached_report_json(q.strip(), provider))
    except CompanyNotFound as exc:
        return JSONResponse({"error": str(exc), "query": q}, status_code=404)


@app.get("/api/suggest")
def api_suggest(q: str = Query("", description="prefix to match")):
    ql = q.strip().lower()
    out = []
    for c in _samples():
        hay = " ".join([c.symbol, c.name] + c.aliases).lower()
        if not ql or ql in hay:
            out.append({"symbol": c.symbol, "name": c.name, "sector": c.sector})
    return {"query": q, "results": out}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "samples": len(_samples())}


@app.get("/robots.txt", response_class=Response)
def robots():
    return Response("User-agent: *\nAllow: /\n", media_type="text/plain")
