#!/usr/bin/env bash
# Setup idempotente: build do CLI Rust, venv do MCP, gate de exemplo.
set -euo pipefail
cd "$(dirname "$0")/.."
cargo build --manifest-path src/cade_cli/Cargo.toml
[ -d tools/.venv-mcp ] || uv venv tools/.venv-mcp
uv pip install --python tools/.venv-mcp/bin/python "mcp<2" pillow numpy
mkdir -p out
python3 tools/build_spec.py tools/examples/intercalada.spec.json out/intercalada.cad
