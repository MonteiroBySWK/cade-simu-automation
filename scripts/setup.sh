#!/usr/bin/env bash
# Setup idempotente do NUCLEO (sem Wine, sem o app CADe_SIMU): cargo build + venv + deps + doctor.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v cargo >/dev/null || { echo "Falta Rust/cargo: https://rustup.rs" >&2; exit 1; }
cargo build --quiet --manifest-path src/cade_cli/Cargo.toml

if [ ! -x tools/.venv-mcp/bin/python ]; then
  if command -v uv >/dev/null; then uv venv -q tools/.venv-mcp
  else python3 -m venv tools/.venv-mcp; fi
fi
if command -v uv >/dev/null; then
  uv pip install -q --python tools/.venv-mcp/bin/python -r requirements.txt
else
  tools/.venv-mcp/bin/python -m pip install -q -r requirements.txt
fi
mkdir -p out
tools/.venv-mcp/bin/python tools/doctor.py
