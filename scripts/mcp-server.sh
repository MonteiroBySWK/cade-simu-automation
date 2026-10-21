#!/usr/bin/env bash
# Sobe o servidor MCP `cade-simu` (stdio). Funciona de qualquer diretorio; so escreve no stderr.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/tools/.venv-mcp/bin/python"
[ -x "$PY" ] || { echo "[cade-simu] rode 'make setup' em $ROOT primeiro" >&2; exit 1; }
[ -x "$ROOT/src/cade_cli/target/debug/cade_cli" ] || cargo build --quiet --manifest-path "$ROOT/src/cade_cli/Cargo.toml" >&2
exec "$PY" "$ROOT/tools/cade_mcp.py"
