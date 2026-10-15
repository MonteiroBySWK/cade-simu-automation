#!/usr/bin/env python3
"""Gera um .cad a partir de uma especificação JSON, via MCP (cad_build).

Uso: python3 tools/build_spec.py tools/examples/intercalada.spec.json out/x.cad
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_call  # noqa: E402


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    spec = json.loads(Path(argv[0]).read_text())
    out = argv[1]
    res = mcp_call.call("cad_build", {
        "titulo": spec.get("titulo", "NOVO"),
        "simbolos_json": json.dumps(spec["simbolos"]),
        "conexoes_json": json.dumps(spec.get("conexoes", [])),
        "fios_json": json.dumps(spec.get("fios", [])),
        "out_path": out,
    })
    print(res)
    if "OK" not in res:
        return 1
    print(mcp_call.call("cad_test", {"path": out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
