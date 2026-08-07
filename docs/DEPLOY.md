# Running & deploying the website

## Run locally

```bash
pip install -e ".[web]"           # + ".[live]" for yfinance/news, ".[llm]" for Claude narrative
python -m stockanalyser.web        # http://localhost:8000   (honours $PORT / $HOST)
# or:  stockanalyser-web           # (console script)
# or:  uvicorn stockanalyser.web.app:app --reload
```

Then open <http://localhost:8000> and search a company. Interactive API docs live at `/docs`.

### Routes
| Route | What |
|---|---|
| `GET /` | landing page + search |
| `GET /analyse?q=&provider=` | full HTML dashboard |
| `GET /framework` | the analytical model |
| `GET /api/analyse?q=&provider=` | JSON report |
| `GET /api/suggest?q=` | name/ticker autocomplete |
| `GET /healthz` | liveness probe |

`provider` is one of `auto` (default), `offline`, `yfinance`, `alphavantage`, `screener`.

## Docker

```bash
docker build -t stockanalyser .
docker run -p 8000:8000 \
  -e ALPHAVANTAGE_API_KEY=... \   # optional (live prices)
  -e ANTHROPIC_API_KEY=...   \    # optional (LLM narrative)
  stockanalyser
```

## Deploy

- **Render** — push the repo, *New → Blueprint*, select `render.yaml`. Health check `/healthz`.
- **Railway / Fly.io / Heroku** — the `Procfile` + `Dockerfile` work out of the box; set
  `PORT` (most platforms inject it automatically) and any optional keys.
- **Any container host** — `docker build` / `docker run` above.

### Environment variables
| Var | Effect |
|---|---|
| `PORT`, `HOST` | bind address (defaults `8000`, `0.0.0.0`) |
| `ALPHAVANTAGE_API_KEY` | enables the Alpha Vantage price provider |
| `ANTHROPIC_API_KEY` | LLM-written analyst narrative (else deterministic) |

With no keys set the site runs fully on the bundled illustrative snapshots — good for a
demo, clearly labelled as not-live in every report.

## Notes for production
- Put a real fundamentals source behind the `screener` (or a broker) adapter before using
  this for anything but exploration — the bundled data is illustrative.
- The dashboard cache (`lru_cache`) is per-process; front it with a CDN or add Redis if you
  expect traffic.
- Nothing here is investment advice; keep the disclaimer visible.
