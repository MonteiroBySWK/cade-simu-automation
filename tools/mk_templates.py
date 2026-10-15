#!/usr/bin/env python3
"""Gera biblioteca de templates: 1 .cad com 8 símbolos (labels vazios) p/ render no Wine.

Uso: python3 tools/mk_templates.py  ->  out/tpl/livro.cad (+out/tpl/base usado)
Depois: abrir no Wine maximizado + Zoom Todo, screenshot -> tools/crop_templates.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "tpl"

SYMS = [
    # (id, sub, labels[9], flags8, x, y, w, h)
    ("2001", "", ["", "", "1", "3", "5", "2", "4", "6", ""], "11111100", 60, 30, 18, 15),
    ("1000", "", ["", "", "U1", "V1", "W1", "PE", "", "", ""], "11110000", 60, 58, 24, 24),
    ("8000", "", ["", "", "3", "4", "", "", "", "", ""], "11000000", 60, 84, 6, 15),
    ("8001", "", ["", "", "1", "2", "", "", "", "", ""], "11000000", 60, 104, 6, 15),
    ("6007", "", ["", "", "1", "3", "5", "2", "4", "6", ""], "11111100", 60, 124, 21, 15),
    ("9008", "", ["", "", "X1", "X2", "", "", "", "", ""], "11000000", 60, 144, 9, 15),
    ("8017", "", ["", "", "95", "96", "", "", "", "", ""], "11000000", 60, 164, 6, 15),
    ("8016", "", ["", "", "97", "98", "", "", "", "", ""], "11000000", 60, 184, 6, 15),
]

def ent(seq, sid, sub, labels, flags, x, y, w, h):
    fl = "*".join(flags)
    lab = "#".join([sub] + labels)
    return f"*{seq}*{sid}#{lab}#*{fl}*{x}*{y}*0*0*-15*-3*{w}*{h}*0*0*0*1*0*0*0"

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = (ROOT / "corpus" / "Arranque_1.cad").read_bytes().decode("latin1")
    i = base.find("$$$")
    # header = tudo até a 1a entidade; footer = do $$$ em diante (metadados+legenda exigidos pelo app)
    m = __import__("re").search(r"#(?=\*\d+\*\d+#)", base)
    header, footer = base[:m.start() + 1], base[i:]
    parts = [ent(1 + i, *s) for i, s in enumerate(SYMS)]
    (OUT / "livro.cad").write_bytes((header + "#".join(parts) + "#" + footer).encode("latin1"))
    print("livro.cad OK", [s[0] for s in SYMS])

if __name__ == "__main__":
    main()
