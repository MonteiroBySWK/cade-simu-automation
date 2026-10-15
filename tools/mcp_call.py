#!/usr/bin/env python3
"""Cliente MCP (stdio) para chamar as ferramentas do cade-simu de scripts/agentes.

Uso:
  python3 tools/mcp_call.py cad_symbols
  python3 tools/mcp_call.py cad_build '{"titulo":"X","simbolos_json":"[...]","out_path":"/tmp/x.cad"}'
  python3 tools/mcp_call.py cad_validate '{"path":"/tmp/x.cad"}'
"""
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
VENV = TOOLS / ".venv-mcp" / "bin" / "python"
PY = str(VENV) if VENV.exists() else sys.executable
SERVER = [PY, str(TOOLS / "cade_mcp.py")]


def call(tool, args):
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cli", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}},
    ]
    inp = "\n".join(json.dumps(m) for m in msgs) + "\n"
    r = subprocess.run(SERVER, input=inp, capture_output=True, text=True, timeout=300)
    for line in r.stdout.splitlines():
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        if m.get("id") == 2:
            if "error" in m:
                return f"ERRO MCP: {m['error']}"
            c = m.get("result", {}).get("content", [])
            return c[0].get("text", "") if c else ""
    return (r.stderr or "sem resposta")[:800]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(2)
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(call(sys.argv[1], args))
