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

Or from Python:

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
| `yfinance` | ✅ prices + basic fundamentals | `pip install stockanalyser[live]` + network |
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
