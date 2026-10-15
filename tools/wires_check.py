#!/usr/bin/env python3
"""Verifica a estética/segurança dos fios: trechos que passam por DENTRO de símbolos.

Uso: python3 tools/wires_check.py out/intercalada.cad
Saída: relatório por trecho; exit 1 se houver travessia por dentro (exclui a
aproximação legítima ao pino, que toca a borda mas não o interior).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

WIRE = {"4000", "4018", "4009", "4001", "4010"}
PAD = 2  # margem: tocar a borda é ok (pino); atravessar o interior não


def main(argv):
    d = Path(argv[0]).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    syms, fios = [], []
    for e in ents:
        p = parse_ent(e)
        if not p:
            continue
        n = p["nums"]
        if p["id"] in WIRE:
            fios.append((int(n[8]), int(n[9]), int(n[10]), int(n[11])))
        elif p["id"] != "8":
            x, y, w, h = int(n[8]), int(n[9]), int(n[14]), int(n[15])
            syms.append(((p["labels"] + [""])[0] or p["id"], x, y, x + w, y + h))
    ruins = []
    for (x1, y1, x2, y2) in fios:
        L = max(abs(x2 - x1), abs(y2 - y1)) or 1
        dono = None
        for i in range(L + 1):
            px, py = x1 + (x2 - x1) * i // L, y1 + (y2 - y1) * i // L
            for (nome, a, b, c, e2) in syms:
                if a + PAD < px < c - PAD and b + PAD < py < e2 - PAD:
                    if dono != (nome, (x1, y1, x2, y2)):
                        dono = (nome, (x1, y1, x2, y2))
                        ruins.append((nome, (x1, y1), (x2, y2)))
                    break
    if ruins:
        print(f"FIOS: {len(ruins)} trecho(s) atravessam símbolo:")
        for nome, a, b in ruins:
            print(f"  - passa por {nome}: {a} -> {b}")
        return 1
    print(f"FIOS: ok ({len(fios)} trechos, nenhum atravessa símbolo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
