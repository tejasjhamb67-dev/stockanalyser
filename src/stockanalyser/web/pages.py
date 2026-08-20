"""HTML for the website chrome: the landing page and the search nav bar that
wraps every result. Reuses the dashboard's CSS tokens so the whole site is one
visual system, light/dark aware."""
from __future__ import annotations

from html import escape

from ..models import Company
from ..report.dashboard import _CSS

BRAND = "stockanalyser"


def nav_bar(query: str = "") -> str:
    """Sticky top search bar shown on result pages."""
    return f"""
<nav class="topnav">
  <a href="/" class="brand">◧ {BRAND}</a>
  <form class="navsearch" action="/analyse" method="get" role="search">
    <input name="q" value="{escape(query)}" placeholder="Search a company…"
           autocomplete="off" list="samples" aria-label="Company">
    <button type="submit">Analyse</button>
  </form>
  <a href="/framework" class="navlink">Framework</a>
</nav>
{_datalist()}"""


_DEPTHS = [("L0", "L0 · Snapshot"), ("L1", "L1 · Screen"), ("L2", "L2 · Brief"),
           ("L3", "L3 · Deep dive"), ("L4", "L4 · Initiation"), ("L5", "L5 · Coverage")]
_MARKETS = ["US", "IN", "GB", "EU", "JP", "HK", "CN", "AU", "SG"]


def research_nav(query: str = "", side: str = "sell-side", depth: str = "L4",
                 market: str = "") -> str:
    """Sticky nav for the research agent — search + mandate controls (side/depth/market)."""
    def opt(val, label, cur):
        sel = " selected" if val == cur else ""
        return f"<option value='{escape(val)}'{sel}>{escape(label)}</option>"

    sides = opt("sell-side", "Sell-side", side) + opt("buy-side", "Buy-side", side)
    depths = "".join(opt(v, lbl, depth) for v, lbl in _DEPTHS)
    markets = opt("", "Auto-market", market) + "".join(opt(k, k, market) for k in _MARKETS)
    return f"""
<nav class="topnav">
  <a href="/" class="brand">◧ {BRAND}</a>
  <form class="navsearch navctrls" action="/research" method="get" role="search">
    <input name="q" value="{escape(query)}" placeholder="Company…" list="samples"
           autocomplete="off" aria-label="Company">
    <select name="side" aria-label="Side">{sides}</select>
    <select name="depth" aria-label="Depth">{depths}</select>
    <select name="market" aria-label="Market">{markets}</select>
    <button type="submit">Research</button>
  </form>
  <a href="/analyse?q={escape(query)}" class="navlink">Quick view</a>
</nav>
{_datalist()}"""


def conviction_nav(query: str = "", side: str = "sell-side", depth: str = "L3",
                   market: str = "") -> str:
    """Sticky nav for the conviction screen — a multi-name (comma-separated) search."""
    def opt(val, label, cur):
        sel = " selected" if val == cur else ""
        return f"<option value='{escape(val)}'{sel}>{escape(label)}</option>"
    sides = opt("sell-side", "Sell-side", side) + opt("buy-side", "Buy-side", side)
    depths = "".join(opt(v, lbl, depth) for v, lbl in _DEPTHS)
    markets = opt("", "Auto-market", market) + "".join(opt(k, k, market) for k in _MARKETS)
    return f"""
<nav class="topnav">
  <a href="/" class="brand">◧ {BRAND}</a>
  <form class="navsearch navctrls" action="/conviction" method="get" role="search">
    <input name="q" value="{escape(query)}" placeholder="RELIANCE, TCS, INFY…"
           autocomplete="off" aria-label="Companies (comma-separated)">
    <select name="side" aria-label="Side">{sides}</select>
    <select name="depth" aria-label="Depth">{depths}</select>
    <select name="market" aria-label="Market">{markets}</select>
    <button type="submit">Rank</button>
  </form>
  <a href="/" class="navlink">Home</a>
</nav>
{_datalist()}"""


def _datalist(samples: list[Company] | None = None) -> str:
    opts = ""
    if samples:
        for c in samples:
            opts += f"<option value='{escape(c.name)}'>{escape(c.symbol)}</option>"
    return f"<datalist id='samples'>{opts}</datalist>"


def landing_page(samples: list[Company]) -> str:
    chips = "".join(
        f"<a class='samplechip' href='/analyse?q={escape(c.symbol)}'>"
        f"<b>{escape(c.symbol)}</b><span>{escape(c.name)}</span></a>"
        for c in samples
    )
    lenses = [
        ("Technical", "What is price doing?", "SMA/EMA · RSI · MACD · Bollinger · candlesticks"),
        ("Spike attribution", "Why did it move?", "abnormal-move detection → market/sector/alpha → ranked cause + confidence"),
        ("Fundamental", "Is the business good?", "margins · ROE/ROCE · leverage · DuPont · CAGR"),
        ("Quality / forensic", "Are the numbers real?", "Piotroski F · Altman Z · Beneish M · cash-vs-profit"),
        ("Valuation", "Is it cheap?", "P/E · P/B · EV/EBITDA · two-stage DCF"),
        ("Earnings call", "What is management saying?", "tone · themes · guidance · red-flag phrases · drift"),
        ("Governance", "Can you trust them?", "pledging · capital allocation · earnings honesty"),
        ("Sector / top-down", "Is the tide rising?", "relative strength vs index & sector · peers"),
        ("Ownership & flows", "Who's buying?", "promoter/FII/DII trend · bulk/block deals"),
    ]
    lens_cards = "".join(
        f"<div class='lp-lens'><h3>{escape(t)}</h3>"
        f"<div class='lp-q'>{escape(q)}</div><p>{escape(d)}</p></div>"
        for t, q, d in lenses
    )
    return _WRAP.format(
        title=f"{BRAND} — multi-lens equity analysis",
        css=_CSS + _SITE_CSS,
        nav="",
        body=f"""
<main class="landing">
  <section class="lp-hero">
    <div class="lp-kicker">TECHNICAL · FUNDAMENTAL · FORENSIC · QUALITATIVE</div>
    <h1>Type a company.<br>Get the whole picture.</h1>
    <p class="lp-lede">A multi-lens equity analysis engine that resolves a name to a ticker,
      pulls the data, and answers the question most tools skip —
      <b>why did the stock move?</b> — then scores nine lenses into one verdict.</p>
    <form class="lp-search" action="/analyse" method="get" role="search">
      <input name="q" placeholder="e.g. Hitachi Energy, Reliance, POWERINDIA…"
             autocomplete="off" list="samples" autofocus aria-label="Company">
      <button type="submit">Analyse →</button>
    </form>
    <div class="lp-samples">{chips}</div>
    <div class="lp-note">Offline demo data is illustrative — connect a live provider for real figures.</div>
  </section>

  <section class="lp-lenses">
    <h2>Nine lenses, one scorecard</h2>
    <div class="lp-lensgrid">{lens_cards}</div>
  </section>

  <section class="lp-agent">
    <div class="lp-kicker">RESEARCH AGENT</div>
    <h2>Or run a full research report</h2>
    <p class="lp-lede">The analyst layer: pick a <b>mandate</b> — sell-side or buy-side, any market,
      and a depth from L0 snapshot to L5 living coverage — and get a driver model, a triangulated
      price target, an initiation report, and a coverage note.</p>
    <form class="lp-search lp-rsearch" action="/research" method="get" role="search">
      <input name="q" placeholder="e.g. RELIANCE, AAPL, 7203.T…" list="samples"
             autocomplete="off" aria-label="Company">
      <select name="side" aria-label="Side"><option value="sell-side">Sell-side</option>
        <option value="buy-side">Buy-side</option></select>
      <select name="depth" aria-label="Depth"><option value="L4" selected>L4 · Initiation</option>
        <option value="L0">L0 · Snapshot</option><option value="L1">L1 · Screen</option>
        <option value="L2">L2 · Brief</option><option value="L3">L3 · Deep dive</option>
        <option value="L5">L5 · Coverage</option></select>
      <button type="submit">Research →</button>
    </form>
  </section>

  <section class="lp-agent">
    <div class="lp-kicker">CONVICTION SCREEN</div>
    <h2>Or rank a whole watchlist</h2>
    <p class="lp-lede">Drop in several names and get a <b>best-ideas list</b> — ranked by
      return-to-target with a quality tilt, forensic red flags sunk to the bottom. Click any row
      for its full report.</p>
    <form class="lp-search lp-rsearch" action="/conviction" method="get" role="search">
      <input name="q" placeholder="RELIANCE, Hitachi Energy, REDFLAG…"
             autocomplete="off" aria-label="Companies (comma-separated)">
      <select name="side" aria-label="Side"><option value="sell-side">Sell-side</option>
        <option value="buy-side">Buy-side</option></select>
      <button type="submit">Rank →</button>
    </form>
  </section>

  <section class="lp-cta">
    <a class="lp-btn" href="/research?q=POWERINDIA&side=sell-side&depth=L4">See an initiation report →</a>
    <a class="lp-link" href="/conviction?q=RELIANCE,Hitachi%20Energy,REDFLAG&side=buy-side">Conviction list</a>
    <a class="lp-link" href="/analyse?q=POWERINDIA">Quick dashboard</a>
    <a class="lp-link" href="/framework">Framework</a>
    <a class="lp-link" href="/docs">API</a>
  </section>
  <footer class="lp-foot">Decision-support tool, not investment advice. · {BRAND}</footer>
</main>
{_datalist(samples)}""",
    )


def framework_page(markdown_html: str, samples: list[Company]) -> str:
    return _WRAP.format(
        title=f"Framework — {BRAND}",
        css=_CSS + _SITE_CSS,
        nav=nav_bar(),
        body=f"<main class='wrap prose'>{markdown_html}</main>",
    )


def error_page(query: str, message: str, samples: list[Company]) -> str:
    return _WRAP.format(
        title=f"Not found — {BRAND}",
        css=_CSS + _SITE_CSS,
        nav=nav_bar(query),
        body=f"""
<main class="wrap">
  <section class="card errcard">
    <h2>Couldn't analyse “{escape(query)}”</h2>
    <p class="muted">{escape(message)}</p>
    <p>Try a ticker like <a href="/analyse?q=POWERINDIA">POWERINDIA</a>,
       <a href="/analyse?q=RELIANCE">RELIANCE</a>, or a known name.</p>
  </section>
</main>
{_datalist(samples)}""",
    )


_WRAP = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
{nav}
{body}
</body>
</html>"""


_SITE_CSS = """
/* top nav — terminal command bar */
.topnav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;
  padding:9px 18px;background:color-mix(in srgb,var(--panel) 92%,transparent);
  backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.brand{font-weight:600;letter-spacing:.04em;text-decoration:none;color:var(--accent);white-space:nowrap;
  text-transform:uppercase;font-size:13px}
.navsearch{flex:1;display:flex;gap:8px;max-width:560px;margin:0 auto}
.navsearch input{flex:1;padding:8px 12px;border-radius:3px;border:1px solid var(--line);
  background:var(--bg);color:var(--ink);font-size:13px;font-family:var(--mono)}
.navsearch input:focus,.lp-search input:focus,.navctrls select:focus,.lp-rsearch select:focus{
  outline:none;border-color:var(--accent)}
.navsearch button,.lp-search button{border:1px solid var(--accent);background:var(--accent);color:#06080b;font-weight:600;
  padding:8px 16px;border-radius:3px;cursor:pointer;font-size:13px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.04em}
.navsearch button:hover,.lp-search button:hover{background:color-mix(in srgb,var(--accent) 85%,#fff)}
.navlink{color:var(--muted);text-decoration:none;font-size:13px;white-space:nowrap;text-transform:uppercase;letter-spacing:.04em}
.navlink:hover{color:var(--accent)}
.navctrls{max-width:760px;flex-wrap:wrap}
.navctrls select,.lp-rsearch select{padding:8px 10px;border-radius:3px;border:1px solid var(--line);
  background:var(--bg);color:var(--ink);font-size:12.5px;cursor:pointer;font-family:var(--mono)}
/* landing: research agent section */
.lp-agent{max-width:720px;margin:10px auto 0;text-align:center;padding:36px 16px 8px;
  border-top:1px solid var(--line)}
.lp-agent h2{font-size:22px;letter-spacing:.01em;margin:10px 0 12px}
.lp-rsearch{max-width:640px}
.lp-rsearch select{background:var(--panel);font-size:14px;box-shadow:var(--shadow)}
/* landing */
.landing{max-width:1000px;margin:0 auto;padding:20px}
.lp-hero{text-align:center;padding:60px 16px 40px}
.lp-kicker{font-size:11px;letter-spacing:.24em;color:var(--accent);font-weight:500;
  font-family:var(--mono);text-transform:uppercase}
.lp-hero h1{font-family:var(--mono);font-weight:600;
  font-size:clamp(32px,5.5vw,52px);line-height:1.06;letter-spacing:-.01em;margin:18px 0;text-transform:uppercase}
.lp-agent h2,.lp-lenses h2{font-family:var(--mono);font-weight:600;letter-spacing:.02em;text-transform:uppercase}
.lp-lede{color:var(--muted);font-size:15px;max-width:62ch;margin:0 auto 28px;line-height:1.65}
.lp-lede b{color:var(--ink)}
.lp-search{display:flex;gap:10px;max-width:560px;margin:0 auto;flex-wrap:wrap}
.lp-search input{flex:1;min-width:240px;padding:13px 15px;border-radius:3px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);font-size:15px;box-shadow:var(--shadow);font-family:var(--mono)}
.lp-search button{padding:13px 22px;border-radius:3px;font-size:15px}
.lp-samples{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:22px auto 0;max-width:640px}
.samplechip{display:flex;flex-direction:column;text-decoration:none;padding:8px 14px;border-radius:3px;
  border:1px solid var(--line);background:var(--panel);min-width:120px}
.samplechip:hover{border-color:var(--accent)}
.samplechip b{color:var(--accent);font-size:12.5px} .samplechip span{color:var(--muted);font-size:11px}
.lp-note{color:var(--muted);font-size:11.5px;margin-top:20px}
.lp-lenses{padding:20px 0 10px} .lp-lenses h2{text-align:center;font-size:18px;margin-bottom:22px}
.lp-lensgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.lp-lens{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:15px 16px;box-shadow:var(--shadow)}
.lp-lens:hover{border-color:color-mix(in srgb,var(--accent) 50%,var(--line))}
.lp-lens h3{font-size:13.5px;margin-bottom:4px} .lp-q{color:var(--accent);font-size:12.5px;font-weight:600}
.lp-lens p{color:var(--muted);font-size:12px;margin:6px 0 0;line-height:1.55}
.lp-cta{display:flex;gap:14px;align-items:center;justify-content:center;padding:40px 0 10px;flex-wrap:wrap}
.lp-btn{background:var(--accent);color:#06080b;text-decoration:none;font-weight:600;padding:11px 22px;border-radius:3px;
  text-transform:uppercase;letter-spacing:.04em;font-size:13px}
.lp-btn:hover{background:color-mix(in srgb,var(--accent) 85%,#fff)}
.lp-link{color:var(--muted);text-decoration:none;text-transform:uppercase;letter-spacing:.04em;font-size:12.5px} .lp-link:hover{color:var(--accent)}
.lp-foot{text-align:center;color:var(--muted);font-size:11.5px;padding:40px 0 20px;font-style:italic}
/* prose (framework page) */
.prose{max-width:820px}
.prose h1{font-size:26px;margin-top:0} .prose h2{font-size:16px;margin-top:28px;border:0;padding:0}
.prose h2::before{content:none}
.prose h3{font-size:14px;margin-top:20px}
.prose table{width:100%;border-collapse:collapse;margin:14px 0;font-size:12.5px}
.prose th,.prose td{border:1px solid var(--line);padding:7px 10px;text-align:left}
.prose code{background:var(--panel2);padding:1px 5px;border-radius:3px;font-size:.9em}
.prose pre{background:var(--panel2);border:1px solid var(--line);padding:14px;border-radius:3px;overflow-x:auto}
.prose blockquote{border-left:3px solid var(--accent);margin:14px 0;padding:2px 16px;color:var(--muted)}
.prose a{color:var(--accent)}
.errcard a{color:var(--accent)}
"""
