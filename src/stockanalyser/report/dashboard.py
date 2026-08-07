"""Render a Report into a single self-contained, theme-aware HTML dashboard.

No external assets: all CSS inline, all charts inline SVG. Opens anywhere,
adapts to the viewer's light/dark preference.
"""
from __future__ import annotations

from html import escape

from ..models import Report, Verdict
from . import charts

_VERDICT_CLASS = {
    Verdict.STRONG_BUY: "v-strongbuy", Verdict.BUY: "v-buy", Verdict.HOLD: "v-hold",
    Verdict.AVOID: "v-avoid", Verdict.STRONG_AVOID: "v-avoid",
    Verdict.INSUFFICIENT: "v-hold",
}

_STANCE_CLASS = {"bullish": "s-bull", "bearish": "s-bear", "warning": "s-warn", "neutral": "s-neu"}


def render(report: Report) -> str:
    c = report.company
    tech = report.lenses.get("Technical")
    price = (tech.data.get("last_price") if tech else None) or "—"
    chg = (tech.data.get("change_1d_pct") if tech else None)

    body = [
        _header(report, price, chg),
        _warnings(report),
        _scorecard(report),
        _narrative(report),
        _thesis(report),
        _price_and_spikes(report),
        _fundamentals(report),
        _ownership(report),
        _qualitative(report),
        _footer(report),
    ]
    return _PAGE.replace("{{TITLE}}", escape(f"{c.name} — Stock Analysis")) \
               .replace("{{STYLE}}", _CSS) \
               .replace("{{BODY}}", "\n".join(body))


# ── sections ────────────────────────────────────────────────────────────────
def _header(report, price, chg):
    c = report.company
    chg_html = ""
    if chg is not None:
        cls = "up" if chg >= 0 else "down"
        chg_html = f"<span class='chg {cls}'>{chg:+.2f}%</span>"
    vcls = _VERDICT_CLASS.get(report.verdict, "v-hold")
    mcap = f"{c.currency} {c.market_cap:,.0f} cr" if c.market_cap else "—"
    return f"""
<header class="hero">
  <div class="hero-main">
    <div class="ticker-line"><span class="exch">{escape(c.exchange)}</span>
      <span class="tkr">{escape(c.symbol)}</span></div>
    <h1>{escape(c.name)}</h1>
    <div class="sub">{escape(c.sector or 'Sector n/a')} · {escape(c.industry or '')}</div>
    <div class="pricebar"><span class="price">{price if isinstance(price,str) else f'{c.currency} {price:,.1f}'}</span>{chg_html}
      <span class="mcap">Mkt cap {mcap}</span></div>
    <p class="desc">{escape(c.description or '')}</p>
  </div>
  <div class="hero-verdict">
    {charts.gauge(report.composite_score)}
    <div class="verdict-badge {vcls}">{escape(report.verdict.value)}</div>
    <div class="composite-cap">Composite score</div>
  </div>
</header>"""


def _warnings(report):
    if not report.warnings:
        return ""
    items = "".join(f"<li>{escape(w)}</li>" for w in report.warnings)
    return f"<div class='banner'>⚠ <ul>{items}</ul></div>"


def _scorecard(report):
    cards = []
    for name, lens in report.lenses.items():
        score = lens.score
        bar = ""
        if score is not None:
            cls = "good" if score >= 60 else "warn" if score >= 45 else "bad"
            bar = (f"<div class='scorebar'><div class='fill {cls}' style='width:{score}%'></div></div>"
                   f"<div class='scorenum'>{score:.0f}<span>/100</span></div>")
        else:
            bar = "<div class='scorenum muted'>n/a</div>"
        sig_html = "".join(
            f"<div class='sig {_STANCE_CLASS.get(s.stance,'s-neu')}'>"
            f"<span class='signame'>{escape(str(s.name))}</span>"
            f"<span class='sigval'>{escape(str(s.value))}</span></div>"
            for s in lens.signals[:5]
        )
        cards.append(f"""
<div class="card lens">
  <div class="lens-head"><h3>{escape(name)}</h3>{bar}</div>
  <p class="lens-sum">{escape(lens.summary)}</p>
  <div class="siglist">{sig_html}</div>
</div>""")
    return f"<section class='grid scorecards'>{''.join(cards)}</section>"


def _narrative(report):
    return f"""
<section class="card narrative">
  <h2>Analyst read</h2>
  <p>{escape(report.narrative)}</p>
</section>"""


def _thesis(report):
    def col(title, items, cls):
        lis = "".join(f"<li>{escape(_strip_tag(i))}</li>" for i in items) or "<li class='muted'>—</li>"
        return f"<div class='card thesis-col {cls}'><h3>{title}</h3><ul>{lis}</ul></div>"
    return f"""
<section class="grid thesis">
  {col('Bull case', report.bull_thesis, 't-bull')}
  {col('Bear case', report.bear_thesis, 't-bear')}
  {col('Monitorables', report.monitorables, 't-mon')}
</section>"""


def _price_and_spikes(report):
    tech = report.lenses.get("Technical")
    spike = report.lenses.get("Spike")
    if not tech or not tech.data.get("series_close"):
        return ""
    close = tech.data["series_close"]
    dates = tech.data["series_dates"]
    date_index = {d: i for i, d in enumerate(dates)}

    markers = []
    rows = ""
    spikes = (spike.data.get("spikes") if spike else []) or []
    for sp in spikes:
        idx = date_index.get(sp["date"])
        if idx is not None:
            markers.append((idx, "var(--good)" if sp["ret_pct"] > 0 else "var(--bad)"))
    for sp in reversed(spikes[-14:]):
        conf = sp["confidence"]
        badge = "high" if conf >= 0.6 else "med" if conf >= 0.35 else "low"
        move_cls = "up" if sp["ret_pct"] > 0 else "down"
        rows += f"""<tr>
  <td>{escape(sp['date'])}</td>
  <td class="{move_cls}">{sp['ret_pct']:+.1f}%</td>
  <td>{sp['alpha_pct']:+.1f}%</td>
  <td>{escape(sp['kind'])}</td>
  <td>{escape(sp['primary_cause'])}</td>
  <td><span class="conf {badge}">{conf:.2f}</span></td>
  <td class="evi">{escape(sp['evidence'])}</td>
</tr>"""

    chart = charts.line_chart(close, markers=markers)
    sr = tech.data.get("support"), tech.data.get("resistance")
    sr_html = ""
    if tech.data.get("support") or tech.data.get("resistance"):
        sr_html = (f"<div class='srrow'><span>Support: "
                   f"{', '.join(map(str, tech.data.get('support', []))) or '—'}</span>"
                   f"<span>Resistance: {', '.join(map(str, tech.data.get('resistance', []))) or '—'}</span></div>")
    return f"""
<section class="card">
  <h2>Price action & spike attribution <span class="star">why did it move?</span></h2>
  <div class="pricewrap">{chart}</div>
  {sr_html}
  <div class="tablewrap"><table class="spikes">
    <thead><tr><th>Date</th><th>Move</th><th>α (stock-specific)</th><th>Type</th>
      <th>Most likely cause</th><th>Conf.</th><th>Evidence</th></tr></thead>
    <tbody>{rows or "<tr><td colspan=7 class='muted'>No abnormal spikes detected.</td></tr>"}</tbody>
  </table></div>
</section>"""


def _fundamentals(report):
    f = report.lenses.get("Fundamental")
    if not f or not f.data.get("series"):
        return ""
    s = f.data["series"]
    periods = f.data.get("periods", [])
    ratios = f.data.get("ratios", {})
    du = f.data.get("dupont", {})
    growth = f.data.get("growth", {})

    rev_chart = charts.bar_chart(s.get("revenue", []), labels=periods)
    pat_chart = charts.bar_chart(s.get("net_income", []), labels=periods, color="var(--good)")

    ratio_items = [
        ("ROE", ratios.get("roe"), "%"), ("ROCE", ratios.get("roce"), "%"),
        ("Net margin", ratios.get("net_margin"), "%"), ("EBITDA margin", ratios.get("ebitda_margin"), "%"),
        ("Debt / Equity", ratios.get("debt_equity"), ""), ("Interest cover", ratios.get("interest_coverage"), "x"),
        ("Current ratio", ratios.get("current_ratio"), ""), ("CFO / PAT", ratios.get("cfo_to_pat"), ""),
        ("Receivable days", ratios.get("receivable_days"), ""), ("Cash conv. days", ratios.get("cash_conversion_days"), ""),
    ]
    grid = "".join(
        f"<div class='metric'><div class='mk'>{escape(k)}</div>"
        f"<div class='mv'>{'—' if v is None else f'{v}{u}'}</div></div>"
        for k, v, u in ratio_items
    )
    du_html = ""
    if du.get("roe") is not None:
        du_html = (f"<div class='dupont'>DuPont: ROE <b>{du['roe']}%</b> = "
                   f"{du['net_margin']}% margin × {du['asset_turnover']} turnover × "
                   f"{du['equity_multiplier']} leverage</div>")
    g = (f"<div class='growthline'>Revenue CAGR <b>{growth.get('revenue_cagr')}%</b> · "
         f"PAT CAGR <b>{growth.get('pat_cagr')}%</b> · "
         f"EBITDA CAGR <b>{growth.get('ebitda_cagr')}%</b></div>")

    return f"""
<section class="card">
  <h2>Fundamentals</h2>
  {g}
  <div class="grid two">
    <div><div class="chart-cap">Revenue ({' → '.join([periods[0], periods[-1]]) if periods else ''})</div>{rev_chart}</div>
    <div><div class="chart-cap">Net profit</div>{pat_chart}</div>
  </div>
  {du_html}
  <div class="metrics">{grid}</div>
</section>"""


def _ownership(report):
    o = report.lenses.get("Ownership")
    if not o or not o.data.get("series"):
        return ""
    s = o.data["series"]
    periods = s.get("periods", [])
    series = {}
    for key, label in (("promoter", "Promoter"), ("fii", "FII"), ("dii", "DII"), ("pledged", "Pledged")):
        if any(v is not None for v in s.get(key, [])):
            series[label] = s[key]
    chart = charts.stacked_area(series) if series else ""
    latest = o.data.get("latest", {})
    chips = "".join(
        f"<span class='chip'>{escape(k)}: <b>{v}%</b></span>"
        for k, v in [("Promoter", latest.get("promoter")), ("Pledged", latest.get("pledged")),
                     ("FII", latest.get("fii")), ("DII", latest.get("dii"))]
        if v is not None
    )
    return f"""
<section class="card">
  <h2>Ownership & flows</h2>
  <div class="chips">{chips}</div>
  <div class="chart-cap">Shareholding trend ({' → '.join([periods[0], periods[-1]]) if periods else ''})</div>
  {chart}
  <p class="lens-sum">{escape(o.summary)}</p>
</section>"""


def _qualitative(report):
    q = report.lenses.get("Qualitative")
    if not q or not q.data.get("themes") and not q.data.get("guidance"):
        return ""
    themes = q.data.get("themes", [])
    theme_chips = "".join(f"<span class='chip'>{escape(t)} <b>{n}</b></span>" for t, n in themes)
    guidance = "".join(f"<li>{escape(g)}</li>" for g in q.data.get("guidance", []))
    flags = q.data.get("red_flags", [])
    flag_html = ("<div class='flags'>" + "".join(f"<span class='flag'>⚠ {escape(fl)}</span>" for fl in flags) + "</div>") if flags else ""
    sent = q.data.get("sentiment")
    drift = q.data.get("theme_drift", "")
    return f"""
<section class="card">
  <h2>Earnings call & filings <span class="star">what management is saying</span></h2>
  <div class="sentline">Tone/sentiment: <b>{sent}</b> ({q.data.get('latest_period','')})</div>
  <div class="chips">{theme_chips}</div>
  {flag_html}
  {f"<div class='drift'>Theme drift: {escape(drift)}</div>" if drift else ""}
  {f"<div class='chart-cap'>Guidance extracted</div><ul class='guidance'>{guidance}</ul>" if guidance else ""}
</section>"""


def _footer(report):
    srcs = " · ".join(f"{escape(k)}: {escape(v)}" for k, v in report.data_sources.items())
    return f"""
<footer>
  <div class="sources">Data sources — {srcs}</div>
  <div class="gen">Generated {escape(report.generated_at)} · stockanalyser</div>
  <div class="disc">Decision-support tool, not investment advice. Verify all figures against
  primary filings before acting. Bundled/offline figures are illustrative.</div>
</footer>"""


def _strip_tag(s: str) -> str:
    # bull/bear items are prefixed with "[Lens] " — keep it readable
    return s


# ── page shell + CSS ─────────────────────────────────────────────────────────
_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>{{STYLE}}</style>
</head>
<body>
<main class="wrap">
{{BODY}}
</main>
</body>
</html>"""

_CSS = """
:root{
  --bg:#f6f7f9; --panel:#ffffff; --ink:#141821; --muted:#6b7480; --line:#e6e9ee;
  --accent:#2f6df6; --good:#12a150; --warn:#d98a00; --bad:#e5484d;
  --track:#e6e9ee; --shadow:0 1px 3px rgba(20,24,33,.06),0 8px 24px rgba(20,24,33,.05);
}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0e1116; --panel:#161b22; --ink:#e7ecf3; --muted:#8b97a6; --line:#232a34;
    --accent:#4c8bff; --good:#2ec46b; --warn:#e2a53a; --bad:#ff6169;
    --track:#232a34; --shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --bg:#0e1116; --panel:#161b22; --ink:#e7ecf3; --muted:#8b97a6; --line:#232a34;
  --accent:#4c8bff; --good:#2ec46b; --warn:#e2a53a; --bad:#ff6169;
  --track:#232a34; --shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px;}
h1{font-size:28px;margin:.1em 0 .1em;letter-spacing:-.02em}
h2{font-size:18px;margin:0 0 14px;letter-spacing:-.01em}
h3{font-size:14px;margin:0;letter-spacing:.01em}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin:16px 0;box-shadow:var(--shadow);}
.muted{color:var(--muted)}
.star{font-weight:400;font-size:12px;color:var(--muted);margin-left:8px}
/* hero */
.hero{display:flex;gap:24px;justify-content:space-between;align-items:flex-start;
  background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:24px 26px;box-shadow:var(--shadow);flex-wrap:wrap}
.hero-main{flex:1;min-width:260px}
.ticker-line{display:flex;gap:8px;align-items:center;font-size:12px}
.exch{color:var(--muted)} .tkr{font-weight:700;letter-spacing:.04em}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
.pricebar{display:flex;gap:12px;align-items:baseline;margin-top:10px;flex-wrap:wrap}
.price{font-size:22px;font-weight:700}
.chg{font-weight:600;font-size:14px}
.chg.up,.up{color:var(--good)} .chg.down,.down{color:var(--bad)}
.mcap{color:var(--muted);font-size:13px}
.desc{color:var(--muted);font-size:13px;margin:12px 0 0;max-width:60ch}
.hero-verdict{text-align:center;min-width:150px}
.verdict-badge{display:inline-block;padding:6px 14px;border-radius:999px;font-weight:700;
  font-size:14px;margin-top:2px}
.v-strongbuy{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.v-buy{background:color-mix(in srgb,var(--good) 14%,transparent);color:var(--good)}
.v-hold{background:color-mix(in srgb,var(--warn) 16%,transparent);color:var(--warn)}
.v-avoid{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)}
.composite-cap{color:var(--muted);font-size:11px;margin-top:4px}
.gauge{width:132px;height:95px}
.gauge-num{font-size:30px;font-weight:800;fill:var(--ink)}
.gauge-cap{font-size:11px;fill:var(--muted)}
/* banner */
.banner{background:color-mix(in srgb,var(--warn) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--warn) 35%,transparent);border-radius:12px;
  padding:8px 16px;margin:14px 0;font-size:13px;color:var(--ink);display:flex;gap:8px}
.banner ul{margin:4px 0;padding-left:16px}
/* grids */
.grid{display:grid;gap:16px}
.scorecards{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.two{grid-template-columns:1fr 1fr}
.thesis{grid-template-columns:repeat(3,1fr)}
@media(max-width:760px){.two,.thesis{grid-template-columns:1fr}}
/* lens cards */
.lens-head{display:flex;align-items:center;gap:10px;justify-content:space-between}
.scorebar{flex:1;height:7px;background:var(--track);border-radius:6px;overflow:hidden;margin:0 8px}
.scorebar .fill{height:100%;border-radius:6px}
.fill.good{background:var(--good)} .fill.warn{background:var(--warn)} .fill.bad{background:var(--bad)}
.scorenum{font-weight:700;font-size:15px;white-space:nowrap}
.scorenum span{color:var(--muted);font-weight:400;font-size:11px}
.lens-sum{font-size:13px;color:var(--muted);margin:10px 0}
.siglist{display:flex;flex-direction:column;gap:4px}
.sig{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;
  padding:3px 8px;border-radius:7px;background:color-mix(in srgb,var(--ink) 3%,transparent)}
.signame{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sigval{font-weight:600;white-space:nowrap}
.s-bull .sigval{color:var(--good)} .s-bear .sigval{color:var(--bad)}
.s-warn{background:color-mix(in srgb,var(--bad) 8%,transparent)} .s-warn .sigval{color:var(--bad)}
/* narrative */
.narrative p{font-size:15px;line-height:1.65;margin:0}
/* thesis */
.thesis-col ul{margin:8px 0 0;padding-left:18px;font-size:13px}
.thesis-col li{margin:5px 0}
.t-bull h3{color:var(--good)} .t-bear h3{color:var(--bad)} .t-mon h3{color:var(--warn)}
/* charts */
.chart{width:100%;height:auto;display:block}
.pricewrap{border:1px solid var(--line);border-radius:10px;padding:8px;background:color-mix(in srgb,var(--ink) 2%,transparent)}
.chart-cap{font-size:12px;color:var(--muted);margin:10px 0 4px}
.axis{font-size:9px;fill:var(--muted)}
.overlay{position:relative} .overlay svg{position:absolute;top:0;left:0}
.overlay svg:first-child{position:relative}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;margin-bottom:6px}
.legend .chip i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
.srrow{display:flex;gap:20px;font-size:12px;color:var(--muted);margin-top:8px}
/* tables */
.tablewrap{overflow-x:auto;margin-top:12px}
table{width:100%;border-collapse:collapse;font-size:12.5px;min-width:640px}
th{text-align:left;color:var(--muted);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.evi{color:var(--muted);max-width:260px}
.conf{padding:1px 7px;border-radius:999px;font-weight:600}
.conf.high{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.conf.med{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
.conf.low{background:color-mix(in srgb,var(--muted) 18%,transparent);color:var(--muted)}
/* metrics */
.metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-top:14px}
.metric{background:color-mix(in srgb,var(--ink) 3%,transparent);border-radius:10px;padding:10px 12px}
.mk{font-size:11px;color:var(--muted)} .mv{font-size:17px;font-weight:700;margin-top:2px}
.dupont,.growthline{font-size:13px;color:var(--muted);margin:12px 0 0}
.dupont b,.growthline b{color:var(--ink)}
/* chips */
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
.chip{background:color-mix(in srgb,var(--ink) 4%,transparent);border:1px solid var(--line);
  border-radius:999px;padding:3px 11px;font-size:12px}
.chip b{color:var(--accent)}
.flags{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.flag{background:color-mix(in srgb,var(--bad) 12%,transparent);color:var(--bad);
  border-radius:8px;padding:3px 10px;font-size:12px;font-weight:600}
.sentline,.drift{font-size:13px;margin:4px 0}
.guidance{font-size:13px;color:var(--muted);margin:6px 0 0;padding-left:18px}
/* footer */
footer{margin-top:26px;color:var(--muted);font-size:12px;text-align:center;line-height:1.7}
.disc{margin-top:6px;font-style:italic}
"""
