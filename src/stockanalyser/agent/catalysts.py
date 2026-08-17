"""Catalyst calendar — the dated events that could move the thesis.

Assembled from what the provider actually gives us: corporate actions (results,
dividends, buybacks, splits), earnings-call dates, and recent news. No future dates
are invented — a forward results date only appears if the data carries it. The most
recent events lead; the note flags the next scheduled results as the live monitorable.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import CompanyData


@dataclass
class Catalyst:
    date: str
    label: str
    kind: str          # "results" | "corp-action" | "call" | "news"


def build_catalysts(data: CompanyData, limit: int = 6) -> list[Catalyst]:
    items: list[Catalyst] = []

    for ca in data.corporate_actions:
        kind = "results" if ca.kind.lower() in ("results", "earnings") else "corp-action"
        label = f"{ca.kind.title()}" + (f" — {ca.detail}" if ca.detail else "")
        items.append(Catalyst(date=str(ca.date), label=label, kind=kind))

    for ec in data.earnings_calls:
        if ec.date:
            items.append(Catalyst(date=str(ec.date),
                                  label=f"Earnings call — {ec.period}", kind="call"))

    for nw in data.news[:4]:
        items.append(Catalyst(date=str(nw.date), label=nw.headline[:80], kind="news"))

    # newest first, de-duplicated on (date,label)
    seen: set[tuple[str, str]] = set()
    ordered: list[Catalyst] = []
    for c in sorted(items, key=lambda x: x.date, reverse=True):
        key = (c.date, c.label)
        if key not in seen:
            seen.add(key)
            ordered.append(c)
    return ordered[:limit]
