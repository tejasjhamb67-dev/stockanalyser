# Analyser agent — a separate agent, wired in over MCP

The **Analyser agent** is
[`modelforge-finance`](https://pypi.org/project/modelforge-finance/) wired into
this repo as its own agent over MCP — a **bulge-tier Excel financial-model
factory**: every cell live-formulated, every number traceable, MCP-native. It's a
standalone toolset that runs alongside the stockanalyser analysis engine, not
inside it. stockanalyser turns a name into a framework + dashboard; the Analyser
agent turns a spec into a fully-formulated, audited Excel model (and PPTX/DOCX
decks). Use whichever the job calls for — or both.

> Powered by the third-party package `modelforge-finance` (author:
> *Whatsonyourmind*), pinned at the version tested here (`0.12.0`). It is not
> maintained by this project. Review its behaviour and the API keys you give it
> before relying on it for real work.

---

## Wiring (default: self-provisioning)

The repo ships a project-scoped [`.mcp.json`](../.mcp.json) that registers the
`analyser-agent` server through a launcher:

```json
{
  "mcpServers": {
    "analyser-agent": {
      "command": "bash",
      "args": ["tools/analyser-agent/launch.sh"]
    }
  }
}
```

Open this repo in an MCP client that reads project `.mcp.json` (e.g. Claude Code)
and the **Analyser agent** appears as an agent. On first launch,
[`tools/analyser-agent/launch.sh`](../tools/analyser-agent/launch.sh) builds an
isolated virtualenv, installs `modelforge-finance[mcp,export]` with the correct
`mcp` pin, and execs the stdio server. Subsequent launches reuse the venv and
start instantly. The venv (`tools/analyser-agent/.venv/`) is git-ignored.

Nothing about stockanalyser's own code, dependencies, or CLI changes.

## Wiring (manual)

If you'd rather install it into your own environment and point your client at the
console script directly — this is the snippet from upstream, **plus the pin**:

```bash
pip install "modelforge-finance[mcp,export]" "mcp>=1.12,<2"
```

```json
{
  "mcpServers": {
    "analyser-agent": { "command": "modelforge-mcp" }
  }
}
```

### The `mcp<2` pin matters

A bare `pip install "modelforge-finance[mcp,export]"` resolves `mcp` **2.x**.
modelforge 0.12.0 imports the **v1** API (`mcp.server.fastmcp.FastMCP`), which
2.x renamed, so the server dies on import with:

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

Capping `mcp>=1.12,<2` fixes it. The self-provisioning launcher does this for you.

---

## What the agent exposes (25 tools)

| Group | Tools |
|---|---|
| **Spec & build** | `list_templates`, `spec_guide`, `get_spec_schema`, `validate_spec`, `build_model`, `certify` |
| **QC & audit** | `qc_workbook`, `audit_schedule`, `audit_conservation`, `perturb_replay` |
| **Lineage & sources** | `list_sources`, `lineage_walk`, `ingest_dataroom` |
| **Export** | `export_pptx`, `export_deck`, `export_docx` |
| **Deals & tax** | `screen_deals`, `compute_tax` |
| **Market data** | `data_providers_status`, `quote`, `history`, `fundamentals`, `search_filings`, `entity_lookup`, `search_securities` |

A typical flow: `spec_guide` / `get_spec_schema` → `validate_spec` → `build_model`
→ `qc_workbook` / `audit_*` → `export_deck`. The market-data tools can pull the
inputs (`fundamentals`, `history`, `quote`) before you build.

## API keys (all optional)

The Analyser agent runs in a demo mode with no keys. To pull real data, set any
of the provider keys it reads from the environment — they're inherited by the
launcher, so set them in your MCP client. The ones that overlap with what
stockanalyser already uses:

- `FMP_API_KEY` — Financial Modeling Prep (also stockanalyser's recommended provider)
- `ALPHAVANTAGE_API_KEY`
- `ANTHROPIC_API_KEY`

Others it recognises: `FINNHUB_API_KEY`, `POLYGON_API_KEY`, `TIINGO_API_KEY`,
`FRED_API_KEY`, `OPENFIGI_API_KEY`, and enterprise feeds (FactSet, S&P Global,
Refinitiv/Eikon, Bloomberg). `data_providers_status` reports which are live.

## Verifying / troubleshooting

```bash
# force a clean re-provision of the agent's venv
rm -rf tools/analyser-agent/.venv
bash tools/analyser-agent/launch.sh </dev/null   # provisions, then waits on stdio (Ctrl-C to exit)
```

If the server won't start after a manual install, confirm the pin took:
`python -c "import mcp.server.fastmcp"` must succeed (it fails on `mcp` 2.x).
