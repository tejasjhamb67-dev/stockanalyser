# stockanalyser

**Name in → framework + dashboard out.** A multi-lens equity analysis engine that
takes a company (`"Hitachi Energy"`) and builds a full analytical picture — technical,
fundamental, forensic, valuation, sectoral and qualitative — then scores it and renders
a self-contained HTML dashboard.

It answers the question most tools skip: **why did the stock move?** — detecting
abnormal price/volume spikes and attributing each one to a concrete cause (results,
news, a block deal, or a sector-wide move) with an evidence trail and a confidence.

> Built on the analytical vocabulary of the Zerodha Varsity **Technical** and
> **Fundamental Analysis** modules, extended into forensic, qualitative and
> top-down/bottom-up lenses. See [`docs/FRAMEWORK.md`](docs/FRAMEWORK.md) for the
> full model.

---

## Quickstart

```bash
pip install -e .

# terminal summary
python -m stockanalyser analyse "Hitachi Energy" --provider offline

# + a shareable HTML dashboard
python -m stockanalyser analyse POWERINDIA --provider offline --html hitachi.html --open

# machine-readable report
python -m stockanalyser analyse RELIANCE --provider offline --json reliance.json

# what ships offline
python -m stockanalyser list
```

### Research agent (mandate: side × market × depth)

On top of the lenses sits an **equity-research agent** that behaves like an analyst:
it fixes a *mandate* before pulling data — **sell-side vs buy-side**, the **market**
(any geography), and a **depth tier** (L0 snapshot → L5 living coverage) — then plans,
runs the lenses, and renders a tier-appropriate product framed for that mandate.

```bash
# a sell-side company brief (market auto-inferred from the NSE listing)
python -m stockanalyser research "Hitachi Energy" --side sell-side --depth L2

# an L3 deep dive: driver model + triangulated DCF + scenario-weighted target
python -m stockanalyser research "RELIANCE" --side sell-side --depth L3

# an L4 initiation: full report + estimates + catalysts + coverage memory
python -m stockanalyser research "RELIANCE" --side sell-side --depth L4

# an L5 living-coverage note: results review, estimate revisions, thesis tracking
python -m stockanalyser research "RELIANCE" --side sell-side --depth L5

# a conviction / best-ideas list ranked across several names
python -m stockanalyser conviction "RELIANCE" "Hitachi Energy" "REDFLAG" --side buy-side

# the same name as a buy-side snapshot — different call, different framing
python -m stockanalyser research "Hitachi Energy" --side buy-side --depth L0

# side/depth/market are inferred from the request when not given
python -m stockanalyser research "should I buy RELIANCE for my book?"
```

At **L3** the agent builds a driver-based forecast (revenue → margins → unlevered FCF,
with capex normalising toward maintenance in the terminal year), values it three ways —
**two-stage DCF at a market-anchored WACC, an exit-multiple cross-check, and a reverse-DCF**
that reads the growth the price already implies (the variant-perception view) — across
**bull / base / bear**, and reconciles the rating to the resulting price target (a strong
business at an indefensible price is capped to Sell/Avoid, and vice-versa).

At **L4** it assembles a full **initiation report** — industry primer, thesis, forward
**estimates** with a variant-vs-market read (price-implied until a live consensus provider
is connected), the triangulated valuation, risks, and a **catalyst calendar** — and writes
to **coverage memory**: the first run initiates coverage, later runs become updates that
say exactly what changed (rating moves, target revisions, thesis drift). The store is a
plain JSON directory (`--coverage-store`, default `~/.stockanalyser/coverage`).

At **L5** it maintains the name: a **results review** of the latest period, **estimate
revisions** versus the last note, **thesis tracking** (which monitorables resolved, which
are new, the rating's trajectory), and a **preview** of what to watch next. The
`conviction` command runs the agent across several names and returns a **best-ideas list**
ranked by return-to-target with a quality tilt — forensic red flags sink to the bottom.

All six depth tiers (L0–L5) run today on bundled data; connecting a live provider
lifts every tier onto real filings:

```bash
pip install -e ".[live]"

# a full L4 initiation on live yfinance data — market/WACC inferred from the listing
python -m stockanalyser research AAPL --provider yfinance --depth L4        # US
python -m stockanalyser research RELIANCE.NS --provider yfinance --depth L3  # India
python -m stockanalyser research 7203.T --provider yfinance --depth L3       # Japan (Toyota)
python -m stockanalyser research BP.L --provider yfinance --depth L2         # UK
```

The `yfinance` adapter pulls prices + the full statement set (revenue, EBITDA,
depreciation, working-capital lines, tax — everything the driver model needs) and
maps each listing's exchange to its **market profile** (accounting regime, WACC,
benchmark). Pass a global ticker with its Yahoo suffix (`.NS`, `.L`, `.T`, `.HK`,
`.AX`, `.DE`, …); a bare symbol is tried as US, then NSE, then BSE. `--provider auto`
uses yfinance when reachable and **falls back to the bundled snapshots** when it
isn't, so a run never dead-ends. (Note: some sandboxed/CI networks block Yahoo's
hosts — that's an egress policy, not a code issue; the adapter runs wherever Yahoo
Finance is reachable.)

```python
from stockanalyser.agent import research
out = research("Hitachi Energy", side="buy-side", depth="L2")
print(out.headline)      # Buy-side · L2 · India → Own (composite 65.9/100)
print(out.product)       # the rendered tearsheet
```

The same evidence produces a **sell-side rating** (Buy/Hold/Sell, vs benchmark) or a
**buy-side position stance** (Own/Pass/Avoid, absolute) — and a forensic gate can veto
a constructive call on either side. Phase 1 ships L0–L2; L3 modelling, L4 initiation and
L5 living coverage slot in behind the same mandate. Full design:
[`docs/equity-research-agent-blueprint.html`](docs/equity-research-agent-blueprint.html).

### Web app / site

```bash
pip install -e ".[web]"
python -m stockanalyser.web          # → http://localhost:8000  (search box + dashboards)
```

A FastAPI site: landing page with search, live-rendered dashboards at `/analyse?q=…`, the
framework at `/framework`, a JSON API at `/api/analyse`, autocomplete at `/api/suggest`,
and interactive API docs at `/docs`. Containerised (`Dockerfile`) with one-click
`render.yaml` — see [`docs/DEPLOY.md`](docs/DEPLOY.md). Runs on bundled data with no keys;
set `ALPHAVANTAGE_API_KEY` / `ANTHROPIC_API_KEY` to go live.

### From Python:

```python
from stockanalyser import analyse
from stockanalyser.config import Config

report = analyse("Hitachi Energy", Config(provider="offline"))
print(report.verdict.value, report.composite_score)
for name, lens in report.lenses.items():
    print(name, lens.score, lens.summary)
```

## The nine lenses

| Lens | Question | Highlights |
|---|---|---|
| Technical | What is price doing? | SMA/EMA, RSI, MACD, Bollinger, ATR, OBV, S/R, candlesticks |
| **Spike attribution** | **Why did it move?** | abnormal-move detection → market/sector/alpha split → ranked cause + confidence |
| Fundamental | Is the business good? | margins, ROE/ROCE, leverage, efficiency, DuPont, CAGR |
| Quality/forensic | Are the numbers real? | Piotroski F, Altman Z, Beneish M, cash-vs-profit |
| Valuation | Is it cheap? | P/E, P/B, EV/EBITDA, two-stage DCF |
| Earnings call | What is management saying? | tone, themes, guidance, red-flag phrases, theme drift |
| Governance | Can you trust them? | promoter pledging, capital allocation, earnings honesty |
| Sector / top-down | Is the tide rising? | relative strength vs index & sector, peers, reconciliation |
| Ownership & flows | Who's buying? | promoter/FII/DII trend, bulk/block deals |

All nine feed a weighted **composite score → verdict** (Strong Buy … Strong Avoid),
an auto-drafted **bull/bear thesis**, the **monitorables** (what would change the call),
and a plain-English analyst read.

## Data providers (pluggable)

The engine only talks to a `DataProvider`; swap the source, keep the analytics.

| Provider | Status | Needs |
|---|---|---|
| `offline` | ✅ bundled *illustrative* snapshots + simulated price history | nothing — runs anywhere |
| `yfinance` | ✅ prices + **full fundamentals** (feeds the L3+ driver model), **global exchanges** | `pip install stockanalyser[live]` + network |
| `alphavantage` | ✅ daily prices | `ALPHAVANTAGE_API_KEY` |
| `screener` | 🧩 documented stub | implement `fetch/parse` |

`--provider auto` uses a live provider when one is available and **falls back to the
bundled snapshots** when it isn't — so a demo never dead-ends. The offline snapshots are
clearly labelled *illustrative*; connect a live provider before making real decisions.

### Optional: LLM narrative
With `anthropic` installed and `ANTHROPIC_API_KEY` set, the analyst write-up is generated
by Claude from the lens evidence. Without it, a deterministic synthesiser writes the note.
Either way the numbers come only from the analysis engine.

## Design notes

- **Pluggable & defensive** — every lens degrades to "insufficient data" instead of
  crashing or fabricating.
- **Honest provenance** — every figure carries its source; offline data is flagged.
- **Self-contained dashboard** — one HTML file, inline SVG charts, light/dark aware,
  no external assets.
- **Not a bot, not advice** — a decision-support instrument. Verify against primary
  filings before acting.

## Layout

```
src/stockanalyser/
  data/         providers (offline, yfinance, alphavantage, screener) + resolver
  analysis/     the nine lenses + indicators, patterns, scoring
  narrative/    LLM + deterministic thesis synthesis
  report/       orchestrator, HTML dashboard, JSON export
  cli.py        command-line interface
docs/FRAMEWORK.md   the analytical model in full
tests/              deterministic offline test suite
```

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

## Roadmap

Live NSE/BSE fundamentals adapter · real concall-transcript ingestion · news API +
headline clustering · peer-relative valuation tables · chart-pattern (H&S, triangles)
detection · portfolio-level rollups · alerting on fresh spikes.

---

*Not investment advice.*
