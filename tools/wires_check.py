#!/usr/bin/env python3
"""Verifica a estética dos fios: trechos que atravessam o CORPO de um símbolo.

Pin-aware: ignora a vizinhança de qualquer pino (o fio SAI do pino, mesmo que o
pino esteja dentro do corpo — ex.: disjuntor 6009 tem pino em (0,21) num corpo de 24).

Uso: python3 tools/wires_check.py out/intercalada.cad   (exit 1 se houver travessia)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

WIRE = {"4000", "4018", "4009", "4001", "4010"}
PINS = json.loads((Path(__file__).resolve().parent / "symbol_pins.json").read_text())
PAD = 2      # insets do corpo
TOL = 4      # raio em volta do pino que é permitido (o fio encosta/sai dele)


def coordenadas_de_pino(sid, x, y):
    pts = []
    info = PINS.get(sid, {})
    for nome, off in (info.get("pins") or {}).items():
        pts.append((x + off[0], y + off[1]))
    for k in ("A", "B"):
        if k in info:
            pts.append((x + info[k][0], y + info[k][1]))
    return pts


def analisar(path):
    """-> (n_fios, ruins): ruins = [(simbolo, (x1,y1), (x2,y2))] de trechos que atravessam corpo."""
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    syms, fios, pinos = [], [], []
    for e in ents:
        p = parse_ent(e)
        if not p:
            continue
        n = p["nums"]
        if p["id"] in WIRE:
            fios.append((int(n[8]), int(n[9]), int(n[10]), int(n[11])))
        elif p["id"] != "8":
            x, y, w, h = int(n[8]), int(n[9]), int(n[14]), int(n[15])
            syms.append((((p["labels"] + [""])[0] or p["id"]), x, y, x + w, y + h))
            pinos += coordenadas_de_pino(p["id"], x, y)

    def perto_de_pino(px, py):
        return any(abs(px - a) <= TOL and abs(py - b) <= TOL for a, b in pinos)

    ruins = []
    for (x1, y1, x2, y2) in fios:
        L = max(abs(x2 - x1), abs(y2 - y1)) or 1
        achou = None
        for i in range(L + 1):
            px, py = x1 + (x2 - x1) * i // L, y1 + (y2 - y1) * i // L
            if perto_de_pino(px, py):
                continue
            for (nome, a, b, c, e2) in syms:
                if a + PAD < px < c - PAD and b + PAD < py < e2 - PAD:
                    achou = nome
                    break
            if achou:
                break
        if achou:
            ruins.append((achou, (x1, y1), (x2, y2)))
    return len(fios), ruins


def main(argv):
    n_fios, ruins = analisar(argv[0])
    if ruins:
        print(f"FIOS: {len(ruins)} trecho(s) atravessam símbolo:")
        for nome, a, b in ruins:
            print(f"  - passa por {nome}: {a} -> {b}")
        return 1
    print(f"FIOS: ok ({n_fios} trechos, nenhum atravessa símbolo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
