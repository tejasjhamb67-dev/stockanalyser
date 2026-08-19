"""Render a ResearchOutput into a single self-contained, theme-aware HTML page.

The agent's terminal note, as a shareable document: the mandate, the call and
price target, the scenario valuation, the lens scorecard, the thesis, and — at
L4/L5 — estimates, catalysts and the coverage/maintenance sections. No external
assets; all CSS inline, all charts inline SVG; adapts to the viewer's theme.
"""
from __future__ import annotations

from html import escape
from urllib.parse import quote

from ..report import charts

_CONSTRUCTIVE = ("buy", "own")
_NEGATIVE = ("sell", "avoid", "underweight", "suspended")


def _rating_class(headline: str) -> str:
    h = headline.lower()
    if any(w in h for w in _NEGATIVE):
        return "r-neg"
    if any(h.startswith(w) or w in h for w in _CONSTRUCTIVE):
        return "r-pos"
    return "r-neu"


def _fmt(v, nd=0, suffix="", none="—"):
    if v is None:
        return none
    return f"{v:,.{nd}f}{suffix}"


def render_html(out, nav_html: str = "", extra_css: str = "") -> str:
    c = out.company
    m = out.mandate
    body = "\n".join(filter(None, [
        _hero(out),
        _market_strip(m),
        _call_banner(out),
        _analyst_read(out),
        _valuation(out),
        _estimates(out),
        _living_coverage(out),
        _scorecard(out),
        _thesis(out),
        _catalysts(out),
        _footer(out),
    ]))
    return (_PAGE
            .replace("{{TITLE}}", escape(f"{c.name} — {m.side.label} {m.depth.code}"))
            .replace("{{STYLE}}", _CSS + extra_css)
            .replace("{{NAV}}", nav_html)
            .replace("{{BODY}}", body))


def _hero(out):
    c, m = out.company, out.mandate
    rating_cls = _rating_class(out.call.headline)
    call_word = "Rating" if m.side.value == "sell-side" else "Stance"
    target = ""
    if out.appraisal and out.appraisal.weighted_target is not None:
        a = out.appraisal
        up_cls = "up" if (a.target_upside_pct or 0) >= 0 else "down"
        target = (f"<div class='target'>12-mo target "
                  f"<b>{a.currency} {a.weighted_target:,.0f}</b> "
                  f"<span class='{up_cls}'>{a.target_upside_pct:+.0f}%</span></div>")
    chips = "".join(f"<span class='mchip'>{escape(x)}</span>" for x in
                    [m.side.label, m.depth.label, m.market.name])
    return f"""
<header class="hero">
  <div class="hero-main">
    <div class="ticker-line"><span class="exch">{escape(c.exchange)}</span>
      <span class="tkr">{escape(c.symbol)}</span></div>
    <h1>{escape(c.name)}</h1>
    <div class="sub">{escape(c.sector or 'Sector n/a')}{(' · ' + escape(c.industry)) if c.industry else ''}</div>
    <div class="mchips">{chips}</div>
    <div class="callbox {rating_cls}">
      <div class="call-word">{call_word}</div>
      <div class="call-head">{escape(out.call.headline)}</div>
      <div class="call-conv">{escape(out.call.conviction)}</div>
    </div>
    {target}
  </div>
  <div class="hero-verdict">
    {charts.gauge(out.composite_score)}
    <div class="verdict-badge {rating_cls}">{escape(out.verdict.value)}</div>
    <div class="composite-cap">Composite score</div>
  </div>
</header>"""


def _market_strip(m):
    p = m.market
    items = [
        ("Regime", f"{p.accounting} / {p.regulator}"),
        ("Reporting", p.reporting_cadence),
        ("Benchmark", p.benchmarks[0] if p.benchmarks else "—"),
        ("Macro", p.macro_anchor),
        ("WACC anchor", f"{p.default_wacc*100:.0f}%"),
    ]
    cells = "".join(f"<div><span class='k'>{escape(k)}</span>"
                    f"<span class='v'>{escape(str(v))}</span></div>" for k, v in items)
    return f"<section class='strip'>{cells}</section>"


def _call_banner(out):
    bits = []
    if out.coverage_note:
        bits.append(f"<div class='cov'>{escape(out.coverage_note)}</div>")
    if out.call.gate == "fail":
        bits.append("<div class='gatefail'>⚠ Forensic gate FAILED — constructive calls are capped.</div>")
    if out.warnings:
        bits.append("<div class='warn-banner'>⚠ " +
                    " ".join(escape(w) for w in out.warnings) + "</div>")
    return f"<section class='banners'>{''.join(bits)}</section>" if bits else ""


def _analyst_read(out):
    if not getattr(out, "narrative", ""):
        return ""
    return (f"<section class='card analyst'><h2>Analyst read "
            f"<span class='star'>{escape(out.mandate.side.label)}</span></h2>"
            f"<p>{escape(out.narrative)}</p></section>")


def _valuation(out):
    a = out.appraisal
    if a is None:
        return ""
    rows = ""
    for s in a.scenarios:
        fv = a.currency + " " + _fmt(s.dcf.fair_value) if (s.dcf.fair_value or 0) > 0 else "uncov."
        up = _fmt(s.upside_pct, 0, "%") if s.upside_pct is not None else "—"
        up_cls = "up" if (s.upside_pct or 0) >= 0 else "down"
        rows += (f"<tr><td class='scn'>{escape(s.name)}</td>"
                 f"<td>p={s.prob:.2f}</td><td>{s.assumptions.g0*100:.0f}%</td>"
                 f"<td>{s.assumptions.ebitda_margin*100:.0f}%</td>"
                 f"<td class='num'>{fv}</td>"
                 f"<td class='num {up_cls}'>{up}</td></tr>")
    # risk/reward bar: up/downside by scenario
    ups = [(s.upside_pct or 0) for s in a.scenarios]
    bar = charts.bar_chart(ups, labels=[s.name for s in a.scenarios], height=130)
    variant = f"<div class='variant'>{escape(a.variant)}</div>" if a.variant else ""
    extras = []
    if a.exit_multiple_value is not None:
        extras.append(f"exit-multiple cross-check ~{a.currency} {a.exit_multiple_value:,.0f}")
    if a.scenarios and a.scenarios[1].dcf.terminal_pct:
        extras.append(f"terminal value {a.scenarios[1].dcf.terminal_pct:.0f}% of EV")
    extra_line = f"<div class='vx'>{escape(' · '.join(extras))}</div>" if extras else ""
    tgt = ""
    if a.weighted_target is not None:
        tgt = (f"<div class='wtgt'>Scenario-weighted target "
               f"<b>{a.currency} {a.weighted_target:,.0f}</b> "
               f"({a.target_upside_pct:+.0f}% vs price {a.currency} {_fmt(a.price)}) · "
               f"range {a.currency} {_fmt(a.fair_low)}–{_fmt(a.fair_high)}</div>")
    return f"""
<section class="card">
  <h2>Valuation — driver model + triangulation
    <span class="star">DCF · exit-multiple · reverse-DCF, at {a.wacc*100:.0f}% WACC</span></h2>
  <div class="grid two">
    <div class="tablewrap"><table class="scen">
      <thead><tr><th>Scenario</th><th>Prob</th><th>Growth</th><th>Margin</th>
        <th class='num'>DCF value</th><th class='num'>Up/down</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
    <div><div class="chart-cap">Risk / reward — up/downside to target by scenario</div>{bar}</div>
  </div>
  {tgt}
  {extra_line}
  {variant}
</section>"""


def _estimates(out):
    cv = out.consensus
    if cv is None or not cv.estimates:
        return ""
    rows = ""
    for e in cv.estimates:
        rows += (f"<tr><td>{escape(e.metric)}</td>"
                 f"<td class='num'>{_fmt(e.fy1)}</td>"
                 f"<td class='num'>{_fmt(e.fy2)}</td></tr>")
    variant = f"<div class='variant'>{escape(cv.variant)}</div>" if cv.variant else ""
    return f"""
<section class="card">
  <h2>Estimates & consensus <span class="star">{escape(cv.source)}</span></h2>
  <div class="tablewrap"><table class="est">
    <thead><tr><th>Our estimate</th><th class='num'>FY1</th><th class='num'>FY2</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  {_street_html(cv)}
  {variant}
  <div class="note">{escape(cv.note)}</div>
</section>"""


def _street_html(cv):
    if not getattr(cv, "is_street", False):
        return ""
    bits = []
    if cv.street_target is not None:
        rng = ""
        if cv.street_target_low is not None and cv.street_target_high is not None:
            rng = f" (range {cv.street_target_low:,.0f}–{cv.street_target_high:,.0f})"
        rated = f" · rated <b>{escape(cv.street_rating)}</b>" if cv.street_rating else ""
        n = f" · {cv.street_num_analysts} analysts" if cv.street_num_analysts else ""
        gap = ""
        if cv.target_gap_pct is not None:
            cls = "up" if cv.target_gap_pct >= 0 else "down"
            gap = f" · our target <span class='{cls}'>{cv.target_gap_pct:+.0f}%</span> vs Street"
        bits.append(f"<div class='street'>Street: mean target <b>{cv.street_target:,.0f}</b>"
                    f"{rng}{rated}{n}{gap}</div>")
    if cv.street_estimates:
        srows = "".join(
            f"<tr><td>{escape(e.metric)}</td><td class='num'>{_fmt(e.fy1, 1)}</td>"
            f"<td class='num'>{_fmt(e.fy2, 1)}</td></tr>" for e in cv.street_estimates)
        bits.append("<div class='tablewrap'><table class='est'><thead><tr>"
                    "<th>Street estimate</th><th class='num'>FY1 (curr)</th>"
                    f"<th class='num'>FY2 (next)</th></tr></thead><tbody>{srows}</tbody></table></div>")
    return "".join(bits)


def _living_coverage(out):
    if not (out.review or out.revisions or out.tracker):
        return ""
    blocks = []
    if out.review:
        lines = "".join(f"<li>{escape(ln)}</li>" for ln in out.review.lines)
        blocks.append(f"<div class='lc-block'><h3>Results review — {escape(out.review.period)}</h3>"
                      f"<ul class='rev'>{lines}</ul></div>")
    if out.revisions:
        rows = "".join(
            f"<tr><td>{escape(r.metric)}</td><td class='num'>{_fmt(r.old)}</td>"
            f"<td class='num'>{_fmt(r.new)}</td>"
            f"<td class='num {'up' if (r.delta_pct or 0)>=0 else 'down'}'>{_fmt(r.delta_pct,1,'%')}</td></tr>"
            for r in out.revisions)
        blocks.append("<div class='lc-block'><h3>Estimate revisions</h3>"
                      "<div class='tablewrap'><table class='est'><thead><tr><th>Metric</th>"
                      "<th class='num'>Prev</th><th class='num'>New</th><th class='num'>Δ</th></tr></thead>"
                      f"<tbody>{rows}</tbody></table></div></div>")
    if out.tracker:
        t = out.tracker
        traj = " → ".join(f"{escape(d)}: {escape(r)}" for d, r in t.rating_trajectory[-4:])
        chips = "".join(f"<span class='chip new'>+ {escape(x)[:60]}</span>" for x in t.new_monitorables[:4])
        chips += "".join(f"<span class='chip res'>✓ {escape(x)[:60]}</span>" for x in t.resolved_monitorables[:4])
        blocks.append(f"<div class='lc-block'><h3>Thesis tracking</h3>"
                      f"<div class='traj'>Rating trajectory: {traj}</div>"
                      f"<div class='chips'>{chips or '<span class=muted>no change</span>'}</div></div>")
    return f"<section class='card'><h2>Living coverage</h2>{''.join(blocks)}</section>"


def _scorecard(out):
    cards = []
    for name, lens in out.lenses.items():
        if lens.score is not None:
            cls = "good" if lens.score >= 60 else "warn" if lens.score >= 45 else "bad"
            bar = (f"<div class='scorebar'><div class='fill {cls}' style='width:{lens.score}%'></div></div>"
                   f"<div class='scorenum'>{lens.score:.0f}<span>/100</span></div>")
        else:
            bar = "<div class='scorenum muted'>n/a</div>"
        sigs = "".join(
            f"<div class='sig'><span class='signame'>{escape(str(s.name))}</span>"
            f"<span class='sigval'>{escape(str(s.value))}</span></div>"
            for s in lens.signals[:4])
        cards.append(f"<div class='card lens'><div class='lens-head'><h3>{escape(name)}</h3>{bar}</div>"
                     f"<p class='lens-sum'>{escape(lens.summary)}</p>"
                     f"<div class='siglist'>{sigs}</div></div>")
    return f"<h2 class='sec-title'>Lens scorecard</h2><section class='grid scorecards'>{''.join(cards)}</section>"


def _thesis(out):
    def col(title, items, cls):
        lis = "".join(f"<li>{escape(i)}</li>" for i in items[:5]) or "<li class='muted'>—</li>"
        return f"<div class='card thesis-col {cls}'><h3>{title}</h3><ul>{lis}</ul></div>"
    return (f"<section class='grid thesis'>"
            f"{col('Bull case', out.bull_thesis, 't-bull')}"
            f"{col('Bear case', out.bear_thesis, 't-bear')}"
            f"{col('Monitorables', out.monitorables, 't-mon')}</section>")


def _catalysts(out):
    if not out.catalysts:
        return ""
    rows = "".join(
        f"<tr><td>{escape(c.date)}</td><td><span class='kind'>{escape(c.kind)}</span></td>"
        f"<td>{escape(c.label)}</td></tr>" for c in out.catalysts)
    return f"""
<section class="card">
  <h2>Catalyst calendar</h2>
  <div class="tablewrap"><table class="cats"><tbody>{rows}</tbody></table></div>
  <div class="note">Past events shown; next scheduled results are the live monitorable.</div>
</section>"""


def _footer(out):
    srcs = " · ".join(f"{escape(k)}: {escape(v)}" for k, v in out.data_sources.items())
    return f"""
<footer>
  <div class="sources">Data — {srcs}</div>
  <div class="gen">Generated {escape(out.generated_at)} · stockanalyser research agent · {escape(out.mandate.headline)}</div>
  <div class="disc">Decision-support only — not investment advice. Verify against primary filings before acting.
    Bundled/offline figures are illustrative.</div>
</footer>"""


def _conv_class(c: float) -> str:
    return "r-pos" if c > 0 else "r-neu" if c > -20 else "r-neg"


def render_universe_html(rows, side, depth: str = "L3", market: str = "",
                         nav_html: str = "", extra_css: str = "") -> str:
    """A conviction / best-ideas screen: names ranked by conviction, each row a
    link into its full research report."""
    from .mandate import Side
    side_obj = side if isinstance(side, Side) else Side(side)
    label = "Best ideas" if side_obj is Side.BUY_SIDE else "Conviction list"
    call_col = "Stance" if side_obj is Side.BUY_SIDE else "Rating"

    body_rows = ""
    for i, r in enumerate(rows, 1):
        if r.error:
            body_rows += (f"<tr class='err'><td class='rank'>{i}</td>"
                          f"<td class='name'>{escape(r.query)}</td>"
                          f"<td colspan='5' class='muted'>{escape(r.error)}</td></tr>")
            continue
        href = (f"/research?q={quote(r.query)}&side={quote(side_obj.value)}"
                f"&depth={quote(depth)}" + (f"&market={quote(market)}" if market else ""))
        comp = f"{r.composite:.0f}" if r.composite is not None else "—"
        up = (f"<span class='{'up' if r.target_upside >= 0 else 'down'}'>{r.target_upside:+.0f}%</span>"
              if r.target_upside is not None else "—")
        gate_cls = {"pass": "g-ok", "fail": "g-bad"}.get(r.gate, "g-na")
        body_rows += (
            f"<tr>"
            f"<td class='rank'>{i}</td>"
            f"<td class='name'><a href='{escape(href)}'>{escape(r.ticker)}</a>"
            f"<span class='co'>{escape(r.name)}</span></td>"
            f"<td class='num conv {_conv_class(r.conviction)}'>{r.conviction:.0f}</td>"
            f"<td class='num'>{comp}</td>"
            f"<td class='num'>{up}</td>"
            f"<td><span class='gate {gate_cls}'>{escape(r.gate)}</span></td>"
            f"<td><span class='pill {_rating_class(r.rating)}'>{escape(r.rating)}</span></td>"
            f"</tr>")

    depth_name = {"L0": "Snapshot", "L1": "Screen", "L2": "Brief", "L3": "Deep dive",
                  "L4": "Initiation", "L5": "Coverage"}.get(depth, depth)
    body = f"""
<header class="uni-hero">
  <div class="uni-kicker">{escape(side_obj.label.upper())} · {escape(depth)} {escape(depth_name).upper()}
    {('· ' + escape(market)) if market else ''}</div>
  <h1>{label}</h1>
  <p class="uni-sub">{len(rows)} names ranked by conviction — return-to-target with a quality
    tilt; forensic red flags sink to the bottom. Click a ticker for the full report.</p>
</header>
<section class="card uni-card">
  <div class="tablewrap"><table class="uni">
    <thead><tr><th class="rank">#</th><th>Name</th><th class="num">Conviction</th>
      <th class="num">Composite</th><th class="num">Target ↑</th><th>Gate</th>
      <th>{call_col}</th></tr></thead>
    <tbody>{body_rows}</tbody>
  </table></div>
</section>
<footer>
  <div class="disc">Conviction = composite + return-to-target (capped ±60); a forensic red flag
    subtracts 100. Decision-support only — not investment advice.</div>
</footer>"""
    return (_PAGE
            .replace("{{TITLE}}", escape(f"{label} — {side_obj.label}"))
            .replace("{{STYLE}}", _CSS + _UNI_CSS + extra_css)
            .replace("{{NAV}}", nav_html)
            .replace("{{BODY}}", body))


_UNI_CSS = """
.uni-hero{padding:26px 4px 8px}
.uni-kicker{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.16em;color:var(--muted)}
.uni-hero h1{font-size:28px;letter-spacing:-.02em;margin:8px 0 6px}
.uni-sub{color:var(--muted);font-size:14px;max-width:70ch;margin:0}
.uni-card{padding:6px 8px}
table.uni{font-size:13.5px}
table.uni th{padding:10px 12px}
table.uni td{padding:10px 12px;vertical-align:middle}
table.uni tr:hover td{background:color-mix(in srgb,var(--accent) 5%,transparent)}
table.uni .rank{width:34px;color:var(--muted);font-variant-numeric:tabular-nums}
table.uni .name a{font-weight:700;text-decoration:none;color:var(--accent)}
table.uni .name a:hover{text-decoration:underline}
table.uni .name .co{display:block;color:var(--muted);font-size:11.5px;margin-top:1px}
table.uni .conv{font-weight:800}
.conv.r-pos{color:var(--good)} .conv.r-neu{color:var(--warn)} .conv.r-neg{color:var(--bad)}
.gate{font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:2px 8px;border-radius:6px}
.gate.g-ok{background:color-mix(in srgb,var(--good) 15%,transparent);color:var(--good)}
.gate.g-bad{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)}
.gate.g-na{background:color-mix(in srgb,var(--muted) 15%,transparent);color:var(--muted)}
.pill{padding:3px 11px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.pill.r-pos{background:color-mix(in srgb,var(--good) 15%,transparent);color:var(--good)}
.pill.r-neg{background:color-mix(in srgb,var(--bad) 15%,transparent);color:var(--bad)}
.pill.r-neu{background:color-mix(in srgb,var(--warn) 15%,transparent);color:var(--warn)}
tr.err td{color:var(--muted)}
"""


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>{{STYLE}}</style>
</head>
<body>
{{NAV}}
<main class="wrap">
{{BODY}}
</main>
</body>
</html>"""

_CSS = """
:root{
  --bg:#f5f6f8; --panel:#ffffff; --ink:#101823; --muted:#6b7480; --line:#e2e6ec;
  --accent:#12566b; --brass:#8f6a1e; --good:#1c7a57; --warn:#a9761a; --bad:#b0402c;
  --track:#e6e9ee; --shadow:0 1px 3px rgba(16,24,35,.06),0 8px 24px rgba(16,24,35,.05);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0b1017; --panel:#121a23; --ink:#e7ecf2; --muted:#8b97a6; --line:#26313d;
    --accent:#4fa8bf; --brass:#c79a3e; --good:#3fa37b; --warn:#d2a24a; --bad:#d0654e;
    --track:#26313d; --shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --bg:#0b1017; --panel:#121a23; --ink:#e7ecf2; --muted:#8b97a6; --line:#26313d;
  --accent:#4fa8bf; --brass:#c79a3e; --good:#3fa37b; --warn:#d2a24a; --bad:#d0654e;
  --track:#26313d; --shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:1060px;margin:0 auto;padding:26px 20px 60px;}
h1{font-size:27px;margin:.1em 0;letter-spacing:-.02em}
h2{font-size:18px;margin:0 0 14px;letter-spacing:-.01em}
h3{font-size:14px;margin:0}
.sec-title{margin:22px 0 2px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin:16px 0;box-shadow:var(--shadow);}
.muted{color:var(--muted)} .num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:var(--good)} .down{color:var(--bad)}
.star{font-weight:400;font-size:12px;color:var(--muted);margin-left:8px}
/* hero */
.hero{display:flex;gap:24px;justify-content:space-between;align-items:flex-start;
  background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:22px 24px;box-shadow:var(--shadow);flex-wrap:wrap}
.hero-main{flex:1;min-width:280px}
.ticker-line{display:flex;gap:8px;font-size:12px}
.exch{color:var(--muted)} .tkr{font-weight:700;letter-spacing:.04em}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
.mchips{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}
.mchip{background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent);
  border-radius:999px;padding:3px 11px;font-size:12px;font-weight:600}
.callbox{display:inline-flex;flex-direction:column;gap:1px;border-radius:12px;padding:10px 16px;margin-top:6px;
  border:1px solid var(--line)}
.callbox.r-pos{background:color-mix(in srgb,var(--good) 12%,transparent);border-color:color-mix(in srgb,var(--good) 40%,transparent)}
.callbox.r-neg{background:color-mix(in srgb,var(--bad) 12%,transparent);border-color:color-mix(in srgb,var(--bad) 40%,transparent)}
.callbox.r-neu{background:color-mix(in srgb,var(--warn) 12%,transparent);border-color:color-mix(in srgb,var(--warn) 40%,transparent)}
.call-word{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.call-head{font-size:20px;font-weight:800}
.r-pos .call-head{color:var(--good)} .r-neg .call-head{color:var(--bad)} .r-neu .call-head{color:var(--warn)}
.call-conv{font-size:12px;color:var(--muted)}
.target{margin-top:10px;font-size:14px}
.target b{font-size:16px}
.hero-verdict{text-align:center;min-width:150px}
.verdict-badge{display:inline-block;padding:5px 14px;border-radius:999px;font-weight:700;font-size:13px;margin-top:2px}
.verdict-badge.r-pos{background:color-mix(in srgb,var(--good) 16%,transparent);color:var(--good)}
.verdict-badge.r-neg{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)}
.verdict-badge.r-neu{background:color-mix(in srgb,var(--warn) 16%,transparent);color:var(--warn)}
.composite-cap{color:var(--muted);font-size:11px;margin-top:4px}
.gauge{width:130px;height:94px}.gauge-num{font-size:30px;font-weight:800;fill:var(--ink)}.gauge-cap{font-size:11px;fill:var(--muted)}
/* market strip */
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:16px 0}
.strip>div{background:var(--panel);padding:11px 14px;display:flex;flex-direction:column;gap:2px}
.strip .k{font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.strip .v{font-size:13.5px;font-weight:600}
/* banners */
.banners{display:flex;flex-direction:column;gap:8px;margin:14px 0}
.cov{background:color-mix(in srgb,var(--accent) 10%,transparent);border:1px solid color-mix(in srgb,var(--accent) 30%,transparent);
  border-radius:10px;padding:8px 14px;font-size:13px}
.gatefail{background:color-mix(in srgb,var(--bad) 12%,transparent);border:1px solid color-mix(in srgb,var(--bad) 35%,transparent);
  border-radius:10px;padding:8px 14px;font-size:13px;color:var(--bad);font-weight:600}
.warn-banner{background:color-mix(in srgb,var(--warn) 12%,transparent);border:1px solid color-mix(in srgb,var(--warn) 32%,transparent);
  border-radius:10px;padding:8px 14px;font-size:12.5px}
/* grids */
.grid{display:grid;gap:16px}
.two{grid-template-columns:1fr 1fr}
.scorecards{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.thesis{grid-template-columns:repeat(3,1fr)}
@media(max-width:760px){.two,.thesis{grid-template-columns:1fr}}
/* tables */
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--line)}
.scen .scn{text-transform:capitalize;font-weight:600}
.wtgt{margin-top:12px;font-size:14px} .wtgt b{font-size:15px}
.vx{font-size:12.5px;color:var(--muted);margin-top:4px}
.analyst p{font-size:14.5px;line-height:1.65;margin:0}
.street{margin:10px 0 6px;font-size:13px;padding:8px 12px;border-radius:8px;
  background:color-mix(in srgb,var(--accent) 8%,transparent)}
.street b{color:var(--ink)}
.variant{margin-top:10px;font-size:13.5px;padding:8px 12px;border-left:3px solid var(--brass);
  background:color-mix(in srgb,var(--brass) 8%,transparent);border-radius:0 8px 8px 0}
.note{font-size:12px;color:var(--muted);margin-top:8px;font-style:italic}
.chart{width:100%;height:auto;display:block}.axis{font-size:9px;fill:var(--muted)}
.chart-cap{font-size:12px;color:var(--muted);margin:0 0 4px}
/* lens cards */
.lens-head{display:flex;align-items:center;gap:10px;justify-content:space-between}
.scorebar{flex:1;height:7px;background:var(--track);border-radius:6px;overflow:hidden;margin:0 8px}
.scorebar .fill{height:100%;border-radius:6px}
.fill.good{background:var(--good)}.fill.warn{background:var(--warn)}.fill.bad{background:var(--bad)}
.scorenum{font-weight:700;font-size:15px;white-space:nowrap}.scorenum span{color:var(--muted);font-weight:400;font-size:11px}
.lens-sum{font-size:12.5px;color:var(--muted);margin:10px 0}
.siglist{display:flex;flex-direction:column;gap:4px}
.sig{display:flex;justify-content:space-between;gap:8px;font-size:12px;padding:3px 8px;border-radius:7px;
  background:color-mix(in srgb,var(--ink) 3%,transparent)}
.signame{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sigval{font-weight:600;white-space:nowrap}
/* thesis */
.thesis-col ul{margin:8px 0 0;padding-left:18px;font-size:12.5px}.thesis-col li{margin:5px 0}
.t-bull h3{color:var(--good)}.t-bear h3{color:var(--bad)}.t-mon h3{color:var(--warn)}
/* living coverage */
.lc-block{margin:0 0 16px}.lc-block h3{margin-bottom:6px}
.rev{margin:4px 0 0;padding-left:18px;font-size:13px}.rev li{margin:3px 0}
.traj{font-size:13px;margin:4px 0}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
.chip{border-radius:999px;padding:3px 10px;font-size:11.5px;border:1px solid var(--line)}
.chip.new{color:var(--good);border-color:color-mix(in srgb,var(--good) 40%,transparent)}
.chip.res{color:var(--muted)}
.kind{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
/* footer */
footer{margin-top:26px;color:var(--muted);font-size:12px;text-align:center;line-height:1.7}
.disc{margin-top:6px;font-style:italic}
"""
