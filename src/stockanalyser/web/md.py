"""A small, dependency-free Markdown → HTML renderer.

Covers exactly what the project docs use: ATX headings, paragraphs, unordered
lists, fenced code blocks, pipe tables, blockquotes, horizontal rules, inline
bold/italic/code and links. Not a general Markdown engine — just enough to serve
FRAMEWORK.md as a clean web page without pulling in a dependency.
"""
from __future__ import annotations

import re
from html import escape

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE = re.compile(r"`([^`]+?)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    out = escape(text)
    out = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", out)
    out = _ITAL.sub(lambda m: f"<i>{m.group(1)}</i>", out)
    out = _LINK.sub(lambda m: f"<a href='{m.group(2)}'>{m.group(1)}</a>", out)
    return out


def _table(rows: list[str]) -> str:
    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]
    header = cells(rows[0])
    body = rows[2:]  # rows[1] is the --- separator
    th = "".join(f"<th>{_inline(c)}</th>" for c in header)
    trs = ""
    for r in body:
        tds = "".join(f"<td>{_inline(c)}</td>" for c in cells(r))
        trs += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def render(md: str) -> str:
    lines = md.split("\n")
    html: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # fenced code
        if line.strip().startswith("```"):
            block = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            html.append("<pre><code>" + escape("\n".join(block)) + "</code></pre>")
            continue

        # table (a header line followed by a |---| separator)
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[:\-\s|]+\|[:\-\s|]+$", lines[i + 1]):
            block = [line]
            i += 1
            while i < n and "|" in lines[i]:
                block.append(lines[i])
                i += 1
            html.append(_table(block))
            continue

        # headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            html.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # hr
        if re.match(r"^\s*---+\s*$", line):
            html.append("<hr>")
            i += 1
            continue

        # blockquote
        if line.startswith(">"):
            block = []
            while i < n and lines[i].startswith(">"):
                block.append(lines[i].lstrip("> ").rstrip())
                i += 1
            html.append("<blockquote>" + _inline(" ".join(block)) + "</blockquote>")
            continue

        # unordered list
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            html.append("<ul>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + "</ul>")
            continue

        # blank
        if not line.strip():
            i += 1
            continue

        # paragraph (gather until blank / block starter)
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|>|\s*[-*]\s|```|\s*---+\s*$)", lines[i]) and "|" not in lines[i]:
            para.append(lines[i])
            i += 1
        html.append("<p>" + _inline(" ".join(para)) + "</p>")

    return "\n".join(html)
