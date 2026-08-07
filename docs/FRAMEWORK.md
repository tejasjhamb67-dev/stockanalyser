# The Stock Analysis Framework

> "The market is a device for transferring money from the impatient to the patient."
> This engine exists to make the analysis behind that patience *systematic* instead of vibes.

A single number — the share price — is the compressed output of thousands of decisions.
Proper analysis is the act of **decompressing** it: separating *what* the price is doing
(technical), *why* it moved (attribution), *what the business is worth* (fundamental +
valuation), *whether the numbers are honest* (forensic), *what management is signalling*
(qualitative), and *whether the tide is with you* (sector/macro/flows).

The engine is built around **nine lenses**. No single lens is trusted alone — a stock that
looks cheap (valuation) but is bleeding cash (fundamentals), run by a pledging promoter
(governance), in a dying sector (top-down), with distribution volume spikes (technical) is a
value trap, and only the *combination* reveals it.

---

## The nine lenses

### 1. Technical — *what is price/volume doing?*
Grounded in the Zerodha Varsity **Technical Analysis** module.

- **Trend:** SMA/EMA (short vs long), golden/death cross, ADX strength.
- **Momentum:** RSI (14), MACD (12/26/9), rate-of-change, stochastic.
- **Volatility:** Bollinger Bands (20, 2σ), ATR, historical vol.
- **Volume:** OBV, VWAP, volume z-score, delivery %.
- **Structure:** support/resistance from swing pivots, Fibonacci retracements.
- **Candlesticks:** single (marubozu, doji, hammer, shooting-star, hanging-man) and
  multi-bar (bullish/bearish engulfing, harami, morning/evening star) — each with the
  Zerodha "prior trend + confirmation" gating so a hammer in an uptrend is not mislabelled.

The technical lens never asserts *value*. It answers "is this the right moment / structure?"

### 2. Spike attribution ⭐ — *why did it move?*
The differentiating lens. Most tools *show* a spike; this one *explains* it.

1. **Detect** abnormal days: z-score of daily log-returns, volume surges, opening gaps,
   and streaks. Flag events beyond a configurable sigma.
2. **Characterise:** gap-up/gap-down, breakout vs mean-reversion, blow-off, capitulation.
3. **Decompose the move** into (a) market beta, (b) sector, (c) **stock-specific alpha** —
   because a 6% pop on a day the whole sector rose 5% is *not* a stock story.
4. **Attribute** the residual alpha to ranked candidate causes, each with evidence + a
   confidence weight:
   - proximity to a **results/earnings** date,
   - **corporate actions** (dividend, bonus, split, buyback, demerger),
   - **news flow** in the window (headline clustering / sentiment),
   - **management guidance** or concall commentary,
   - **ownership events** — bulk/block deals, insider trades, index inclusion, FII/DII flow.
5. **Narrate:** synthesise the ranked evidence into a plain-English "most likely reason,
   because…" with an explicit confidence and the caveats.

The attribution is deliberately *humble*: it reports "insufficient evidence" rather than
inventing a reason, and it distinguishes correlation-in-time from cause.

### 3. Fundamentals — *is the business good?*
Grounded in the Zerodha Varsity **Fundamental Analysis** module.

- **Statements** (multi-year): P&L, Balance Sheet, Cash Flow.
- **Profitability:** gross/operating/net margins, ROE, ROA, ROCE.
- **Leverage & liquidity:** debt/equity, interest coverage, current & quick ratios.
- **Efficiency:** asset turnover, inventory/receivable/payable days, cash conversion cycle.
- **Growth:** revenue / EBITDA / PAT CAGR.
- **DuPont:** ROE decomposed into margin × turnover × leverage, so you know *where* the
  return comes from (real operating quality vs balance-sheet leverage).

### 4. Quality & forensics — *are the numbers real?*
Fundamentals assume the reported numbers are honest. This lens stress-tests that.

- **Piotroski F-score** (0–9): nine binary tests of profitability, leverage, efficiency.
- **Altman Z-score:** distance-to-bankruptcy.
- **Beneish M-score:** probability the earnings are being manipulated.
- **Accruals / cash-vs-profit:** is PAT backed by operating cash flow, or by receivables?

### 5. Valuation — *is it cheap?*
- **Relative:** P/E, P/B, EV/EBITDA, PEG, dividend yield — vs its own history and vs peers.
- **Intrinsic:** a transparent two-stage **DCF** on free cash flow, plus an earnings-power
  value cross-check. Always shown with the assumptions exposed, never a single black-box
  "fair value."

### 6. Earnings calls & filings — *what is management saying?*
The qualitative core. Numbers are lagging; the concall is where the future leaks out.

- Extract **guidance**, **management tone/sentiment**, **recurring themes**, and
  **forward-looking statements** from concall transcripts and annual-report MD&A.
- Track **theme drift across quarters** — what management keeps repeating (real priority)
  vs what they quietly stopped mentioning (a buried problem).
- Flag **red-flag language**: auditor qualifications, "challenging environment", hockey-stick
  guidance without a mechanism.
- LLM-backed when an API key is present; deterministic keyword/heuristic pipeline otherwise.

### 7. Management & governance — *can you trust them?*
- Promoter holding **trend** and **pledging** (rising pledge = red flag).
- Related-party transactions, auditor changes, contingent liabilities.
- **Capital-allocation track record:** ROIC vs cost of capital, buyback/dividend discipline,
  history of value-destructive M&A.

### 8. Sector / top-down / macro — *is the tide rising?*
- Classify the stock, build a **peer set**, compute **relative strength** vs sector & index.
- Locate the **sector-cycle** position and the macro drivers (rates, commodities, FX).
- Reconcile **top-down** (macro → sector → stock) with **bottom-up** (stock fundamentals up):
  a great company in a bad sector, and a mediocre company in a booming one, are different bets.
- Peer comparison table on valuation **and** quality.

### 9. Ownership & flows — *who is actually buying?*
- Shareholding-pattern trend: promoter / FII / DII / public.
- Bulk & block deals, insider trades, mutual-fund activity.
- Smart-money accumulation/distribution as an independent read on the price move.

---

## Synthesis: the scorecard

Each lens emits a normalised **0–100 sub-score** with a rationale. A weighted composite
produces a headline read (Strong Buy → Avoid), but the composite is *never* shown without
its components — the disagreements between lenses are the most valuable output. From the
components the engine drafts a **bull thesis**, a **bear thesis**, and the **key monitorables**
(the two or three things that would change the verdict).

## Architecture

```
name ──► resolver ──► DataProvider ──►  9 analysis modules  ──► scorecard ──► Report
"Hitachi Energy"   NSE:POWERINDIA   (offline | yfinance |         │              │
                                     alphavantage | screener)     │              ▼
                                                                  ▼         HTML dashboard
                                                            narrative (LLM
                                                            or deterministic)
```

- **Pluggable data layer.** Every provider implements one `DataProvider` interface. The
  `offline` provider ships illustrative snapshots so the whole pipeline runs with no network;
  swap in `yfinance` / `alphavantage` / `screener` (or your broker API) for live data.
- **Every module is independent** and degrades gracefully: missing data yields "insufficient
  evidence," never a crash and never a fabricated number.
- **Honest provenance.** Every figure carries its source. Bundled snapshots are labelled
  *illustrative* and must be replaced with a live provider before any real decision.

## Deliberate non-goals (v1)
- Not a trading bot — it analyses, it does not place orders.
- Not a live tick engine — it works on daily bars and periodic fundamentals.
- Not financial advice — it is a decision-support instrument, and it says so.
