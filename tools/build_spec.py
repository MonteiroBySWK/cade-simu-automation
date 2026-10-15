#!/usr/bin/env python3
"""Gera um .cad a partir de uma especificação JSON, via MCP (cad_build).

Uso: python3 tools/build_spec.py tools/examples/intercalada.spec.json out/x.cad
     python3 tools/build_spec.py tools/examples/intercalada.layout.json out/x.cad  # DSL topologica
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
    if "layout" in spec or argv[0].endswith(".layout.json"):
        import layout  # motor de layout: spec topologica -> spec baixa
        spec = layout.compilar(spec.get("layout", spec))
    out = argv[1]
    res = mcp_call.call("cad_build", {
        "titulo": spec.get("titulo", "NOVO"),
        "simbolos_json": json.dumps(spec["simbolos"]),
        "conexoes_json": json.dumps(spec.get("conexoes", [])),
        "fios_json": json.dumps(spec.get("fios", [])),
        "rails_json": json.dumps(spec.get("rails", [])),
        "out_path": out,
    })
    print(res)
    print(mcp_call.call("cad_test", {"path": out}))
    # GATE: falha se houver aviso (curto/cruzamento) ou teste reprovado
    problema = ("AVISO" in res) or ("FALHOU" in res) or ("OK" not in res)
    if problema:
        print("GATE: REPROVADO (corrija antes de seguir)")
        return 1
    print("GATE: OK (validado, sem curto, testes passando)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
