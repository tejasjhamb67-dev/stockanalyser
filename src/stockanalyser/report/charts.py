"""Tiny dependency-free SVG chart helpers for the dashboard.

Everything returns an inline <svg> string with a viewBox (so it scales), using
CSS custom properties for colour so it adapts to light/dark automatically.
"""
from __future__ import annotations

from html import escape


def _pts(values, w, h, pad=4):
    xs = [x for x in values if x is not None]
    if not xs:
        return "", 0, 0
    lo, hi = min(xs), max(xs)
    rng = (hi - lo) or 1
    n = len(values)
    step = (w - 2 * pad) / max(n - 1, 1)
    pts = []
    for i, v in enumerate(values):
        if v is None:
            continue
        x = pad + i * step
        y = h - pad - (v - lo) / rng * (h - 2 * pad)
        pts.append((x, y))
    return pts, lo, hi


def line_chart(values, width=680, height=140, stroke="var(--accent)", fill=True,
               markers=None, marker_colors=None):
    """values: list[float|None]. markers: list of (index, color) to dot."""
    pts, lo, hi = _pts(values, width, height)
    if not pts:
        return "<div class='muted'>no data</div>"
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = ""
    if fill:
        area = (f"<path d='{path} L{pts[-1][0]:.1f},{height-4} L{pts[0][0]:.1f},{height-4} Z' "
                f"fill='{stroke}' opacity='0.10'/>")
    dots = ""
    if markers:
        step = (width - 8) / max(len(values) - 1, 1)
        for idx, color in markers:
            if 0 <= idx < len(values) and values[idx] is not None:
                x = 4 + idx * step
                _, ylo, yhi = pts, lo, hi
                y = height - 4 - (values[idx] - lo) / ((hi - lo) or 1) * (height - 8)
                dots += f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.5' fill='{color}'/>"
    return (
        f"<svg viewBox='0 0 {width} {height}' class='chart' preserveAspectRatio='none' "
        f"role='img'>{area}<path d='{path}' fill='none' stroke='{stroke}' "
        f"stroke-width='2' stroke-linejoin='round'/>{dots}</svg>"
    )


def bar_chart(values, labels=None, width=680, height=150, color="var(--accent)"):
    vals = [0 if v is None else v for v in values]
    if not vals:
        return "<div class='muted'>no data</div>"
    lo = min(0, min(vals))
    hi = max(vals) or 1
    rng = (hi - lo) or 1
    n = len(vals)
    pad = 6
    bw = (width - 2 * pad) / n * 0.68
    gap = (width - 2 * pad) / n
    zero_y = height - pad - (0 - lo) / rng * (height - 2 * pad - 16)
    bars = ""
    for i, v in enumerate(vals):
        x = pad + i * gap + (gap - bw) / 2
        y = height - pad - 16 - (v - lo) / rng * (height - 2 * pad - 16)
        bh = abs(zero_y - y)
        yy = min(y, zero_y)
        c = color if v >= 0 else "var(--bad)"
        bars += f"<rect x='{x:.1f}' y='{yy:.1f}' width='{bw:.1f}' height='{bh:.1f}' rx='2' fill='{c}'/>"
        if labels and i < len(labels):
            bars += (f"<text x='{x+bw/2:.1f}' y='{height-3}' text-anchor='middle' "
                     f"class='axis'>{escape(str(labels[i]))}</text>")
    return f"<svg viewBox='0 0 {width} {height}' class='chart'>{bars}</svg>"


def gauge(score, size=132):
    """Semicircular 0-100 gauge coloured by band."""
    if score is None:
        return "<div class='muted'>n/a</div>"
    import math
    color = ("var(--good)" if score >= 60 else "var(--warn)" if score >= 45
             else "var(--bad)")
    r = size / 2 - 12
    cx = cy = size / 2
    start = math.pi
    end = math.pi - math.pi * (score / 100)

    def pt(a):
        return cx + r * math.cos(a), cy - r * math.sin(a) + size * 0.12

    x0, y0 = pt(start)
    x1, y1 = pt(end)
    xe, ye = pt(0)
    large = 0
    return (
        f"<svg viewBox='0 0 {size} {size*0.72}' class='gauge'>"
        f"<path d='M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {xe:.1f},{ye:.1f}' "
        f"fill='none' stroke='var(--track)' stroke-width='11' stroke-linecap='round'/>"
        f"<path d='M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 1 {x1:.1f},{y1:.1f}' "
        f"fill='none' stroke='{color}' stroke-width='11' stroke-linecap='round'/>"
        f"<text x='{cx}' y='{cy+size*0.10}' text-anchor='middle' class='gauge-num'>{score:.0f}</text>"
        f"<text x='{cx}' y='{cy+size*0.24}' text-anchor='middle' class='gauge-cap'>/100</text>"
        f"</svg>"
    )


def stacked_area(series_dict, width=680, height=150):
    """series_dict: {label: [values]} drawn as overlaid lines with a legend."""
    palette = ["var(--accent)", "var(--good)", "var(--warn)", "var(--bad)", "var(--muted)"]
    svgs = []
    legend = []
    for i, (label, vals) in enumerate(series_dict.items()):
        c = palette[i % len(palette)]
        svgs.append(line_chart(vals, width, height, stroke=c, fill=False))
        legend.append(f"<span class='chip'><i style='background:{c}'></i>{escape(label)}</span>")
    # overlay by stripping the svg wrappers except first
    return ("<div class='legend'>" + "".join(legend) + "</div>"
            + "<div class='overlay'>" + "".join(svgs) + "</div>")
