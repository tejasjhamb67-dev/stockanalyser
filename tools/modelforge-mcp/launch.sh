#!/usr/bin/env bash
#
# Self-provisioning launcher for the modelforge-finance MCP server.
#
# modelforge is wired in as a *separate agent* (its own toolset), independent of
# the stockanalyser analysis engine. This script gives it an isolated virtualenv
# so its dependencies never collide with the project's, provisions it on first
# run, and then hands control to the stdio MCP server.
#
# Why the pin: modelforge-finance 0.12.0 imports the mcp v1 API
# (`mcp.server.fastmcp.FastMCP`). A bare `pip install modelforge-finance[mcp]`
# resolves `mcp` 2.x, where FastMCP was renamed and the server fails to import.
# We cap `mcp<2` so the server launches reliably.
#
# The environment (including any *_API_KEY for data providers) is inherited by
# the exec below, so keys set in your MCP client flow straight through.
#
# Overrides:
#   MODELFORGE_VENV  — where to build/keep the venv (default: ./.venv next to this script)
#   MODELFORGE_SPEC  — the pip requirement (default: modelforge-finance[mcp,export])
#   MODELFORGE_MCP_PIN — the mcp pin (default: mcp>=1.12,<2)
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${MODELFORGE_VENV:-$HERE/.venv}"
SPEC="${MODELFORGE_SPEC:-modelforge-finance[mcp,export]}"
MCP_PIN="${MODELFORGE_MCP_PIN:-mcp>=1.12,<2}"

PYTHON_BIN="${MODELFORGE_PYTHON:-python3}"

if [ ! -x "$VENV/bin/modelforge-mcp" ]; then
  # Provision on first run. Log to stderr so we never corrupt the stdio
  # JSON-RPC stream the MCP client reads on stdout.
  {
    echo "[modelforge-mcp] provisioning virtualenv at $VENV ..."
    "$PYTHON_BIN" -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet "$SPEC" "$MCP_PIN"
    echo "[modelforge-mcp] ready."
  } 1>&2
fi

exec "$VENV/bin/modelforge-mcp" "$@"
