#!/usr/bin/env python3
"""Checagem de conectividade por GEOMETRIA, independente dos nets gravados no arquivo.

Segue as regras decompiladas do app (docs/re-engenharia.md §9.2):
  - fio-fio une so por EXTREMO coincidente; 4001 (juncao) une ao fio cujo segmento a contem;
  - pino de simbolo liga a fio so se coincide com um EXTREMO do fio;
  - fontes estampam "char de fase" por pino (L1->1, L2->2, L3->3, N->N, PE->P);
    duas estampas diferentes na mesma net = CURTO (o app tambem acusa).
Pinos: docs/pinos-binario.json (verdade do binario), com nomes de tools/symbol_pins.json.
Tambem lista PINOS SOLTOS (nenhum fio no ponto) — erro grave de autoria.

Uso: python3 tools/geo_check.py out/x.cad     (exit 1 se curto ou pino solto)
"""
import json
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
from dissect import parse_ent, split_entities  # noqa: E402

WIRE = {"4000", "4009", "4010", "4018", "4019"}
SKIP = WIRE | {"4001", "4002", "4003", "4004", "4012", "8", "20000"}
FONTE = {"3000", "3001", "3002", "3003", "3004", "3005", "3006", "3007", "3011"}
CHAR = {"L1": "1", "L2": "2", "L3": "3", "L": "1", "N": "N", "PE": "P"}
BIN = json.loads((T.parent / "docs" / "pinos-binario.json").read_text())["classes"]
PINS = json.loads((T / "symbol_pins.json").read_text())


def _rot(dx, dy, o):
    return {0: (dx, dy), 1: (-dy, dx), 2: (-dx, -dy), 3: (dy, -dx), 4: (-dx, dy)}.get(o, (dx, dy))


def pinos_da_classe(cid):
    """{nome: (dx,dy)} — binario primeiro; cai no symbol_pins (pins nomeados, depois A/B)."""
    if cid in BIN:
        return {k: tuple(v) for k, v in BIN[cid]["pins"].items()}
    e = PINS.get(cid, {})
    out = {k: tuple(v) for k, v in (e.get("pins") or {}).items()}
    for k in ("A", "B"):
        if k in e and k not in out:
            out[k] = tuple(e[k])
    return out


def analisar(path, redes=None):
    d = Path(path).read_bytes().decode("latin1")
    _, ents, _ = split_entities(d)
    ps = [p for p in map(parse_ent, ents) if p and len(p["nums"]) > 17]
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    fios = []
    for p in ps:
        if p["id"] in WIRE:
            a = (int(p["nums"][8]), int(p["nums"][9]))
            b = (int(p["nums"][10]), int(p["nums"][11]))
            fios.append((a, b))
            union(a, b)
    for p in ps:                                   # juncao 4001 / 4012
        if p["id"] in ("4001", "4012"):
            pt = (int(p["nums"][8]), int(p["nums"][9]))
            find(pt)
            for a, b in fios:
                (x1, y1), (x2, y2) = (min(a[0], b[0]), min(a[1], b[1])), (max(a[0], b[0]), max(a[1], b[1]))
                if (y1 == y2 == pt[1] and x1 <= pt[0] <= x2) or (x1 == x2 == pt[0] and y1 <= pt[1] <= y2):
                    union(pt, a)
    extremos = {pt for a, b in fios for pt in (a, b)}
    pinos = []                                     # (rotulo, classe, nome, ponto)
    for p in ps:
        if p["id"] in SKIP:
            continue
        x, y, o = int(p["nums"][8]), int(p["nums"][9]), int(p["nums"][17] or 0)
        rot = (p["labels"] or [""])[0] or p["id"]
        for nome, (dx, dy) in pinos_da_classe(p["id"]).items():
            rx, ry = _rot(dx, dy, o)
            pinos.append((rot, p["id"], nome, (x + rx, y + ry)))
    if redes is not None:                          # {(rotulo, classe, pino): raiz da net}
        for rot, cid, nome, pt in pinos:
            if pt in extremos:
                redes[(rot, cid, nome)] = find(pt)
    estampas = {}                                  # raiz -> {char: [origens]}
    soltos = []
    for rot, cid, nome, pt in pinos:
        if pt not in extremos:
            soltos.append(f"{rot}({cid}).{nome}@{pt}")
            continue
        if cid in FONTE and nome in CHAR:
            estampas.setdefault(find(pt), {}).setdefault(CHAR[nome], []).append(f"{rot}.{nome}")
    curtos = [f"{'+'.join(sorted(m))} na mesma net: " + ", ".join(sum(m.values(), []))
              for m in estampas.values() if len(m) > 1]
    return curtos, soltos


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    curtos, soltos = analisar(argv[0])
    for c in curtos:
        print("CURTO:", c)
    for s in soltos:
        print("SOLTO:", s)
    ok = not curtos and not soltos
    print("GEO: ok (sem curto de fases, sem pino solto)" if ok
          else f"GEO: REPROVADO ({len(curtos)} curto(s), {len(soltos)} pino(s) solto(s))")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
