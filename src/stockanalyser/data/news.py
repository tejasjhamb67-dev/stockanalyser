"""Live news headlines → NewsItem, feeding the spike-attribution engine.

Uses the Google News RSS endpoint (no API key). Network-gated and fully
defensive: any failure yields an empty list so the pipeline never breaks. The
RSS parsing is factored into a pure function so it is unit-tested offline.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

from ..models import Company, NewsItem

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
_TAG = re.compile(r"<[^>]+>")


def parse_rss(xml_text: str, limit: int = 25) -> list[NewsItem]:
    """Pure parser: RSS XML → NewsItem list. No network, unit-testable."""
    items: list[NewsItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub = item.findtext("pubDate")
        when = _parse_date(pub)
        src_el = item.find("source")
        source = (src_el.text if src_el is not None else "") or "news"
        desc = _TAG.sub("", item.findtext("description") or "").strip()
        link = item.findtext("link") or ""
        items.append(NewsItem(date=when, headline=title, summary=desc[:280],
                              source=source, url=link))
        if len(items) >= limit:
            break
    return items


def _parse_date(raw: Optional[str]) -> date:
    if raw:
        try:
            return parsedate_to_datetime(raw).date()
        except (TypeError, ValueError):
            pass
    return datetime.utcnow().date()


def fetch_news(company: Company, limit: int = 25, timeout: int = 12) -> list[NewsItem]:
    """Network-gated fetch. Returns [] on any failure (offline, blocked, error)."""
    try:
        import requests
    except Exception:
        return []
    query = f'"{company.name}" OR {company.symbol} stock'
    url = GOOGLE_NEWS_RSS.format(q=quote_plus(query))
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "stockanalyser/0.1"})
        resp.raise_for_status()
        return parse_rss(resp.text, limit=limit)
    except Exception:
        return []
