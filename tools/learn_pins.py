#!/usr/bin/env python3
"""Aprende a geometria dos pinos (nets A/B) a partir do acervo de .cad.

Modelo: a conectividade do CADe_SIMU é dada por NETs (inteiros). Cada símbolo
tem pinos A (nums[21]) e B (nums[22]); fios/plugs (4000/4018/4009/4001) também
carregam um net em nums[21]. Correlacionando endpoints de fio com símbolos do
mesmo net, derivamos o OFFSET de cada pino relativo a (X,Y) do símbolo.

Saída: out/pin_map.json  {ID: {"A":[dx,dy], "B":[dx,dy], "n": <amostras>}}
Uso: python3 tools/learn_pins.py [dir_do_acervo]
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = Path("/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/Atividades para Simular/115 arquivos CADe_SIMU/Arquivos .cad")
WIRE = {"4000", "4018", "4009", "4001"}


def pins_of(d):
    """(símbolos com net->XY, fios com net->endpoints)."""
    _, ents, _ = split_entities(d)
    syms = []      # (id, x, y, A, B)
    wires = []     # (net, (x1,y1), (x2,y2))
    for e in ents:
        p = parse_ent(e)
        if not p:
            continue
        n = p["nums"]
        if len(n) < 23:
            continue
        try:
            x, y = int(n[8]), int(n[9])
            a, b = int(n[21]), int(n[22])
        except ValueError:
            continue
        if p["id"] in WIRE:
            if p["id"] == "4001":
                continue
            x2, y2 = int(n[10]), int(n[11])
            wires.append((a, (x, y), (x2, y2)))
        else:
            syms.append((p["id"], x, y, a, b))
    return syms, wires


def main(argv):
    acervo = Path(argv[0]) if argv else DEFAULT
    files = sorted(acervo.glob("*.cad")) if acervo.is_dir() else [acervo]
    acc = defaultdict(lambda: {"A": [], "B": []})
    for f in files:
        try:
            d = f.read_bytes().decode("latin1")
            syms, wires = pins_of(d)
        except Exception:
            continue
        for net, p1, p2 in wires:
            if net == 0:
                continue
            for sid, x, y, a, b in syms:
                for pin, pv in (("A", a), ("B", b)):
                    if pv == net:
                        for (wx, wy) in (p1, p2):
                            # offset plausível (pino perto do símbolo)
                            if abs(wx - x) <= 40 and abs(wy - y) <= 40:
                                acc[sid][pin].append((wx - x, wy - y))
    # passagem GEOMÉTRICA: pinos de símbolos sem net (bobina 9000, piloto, motor…)
    # vêm dos endpoints de fio vizinhos (offsets mais frequentes).
    geo = defaultdict(lambda: defaultdict(int))
    for f in files:
        try:
            syms, wires = pins_of(f.read_bytes().decode("latin1"))
        except Exception:
            continue
        pts = [p for _, p1, p2 in wires for p in ((p1[0], p1[1]), (p2[0], p2[1]))]
        for sid, x, y, a, b in syms:
            for (wx, wy) in pts:
                dx, dy = wx - x, wy - y
                if abs(dx) <= 30 and abs(dy) <= 30:
                    geo[sid][(dx, dy)] += 1
    out = {}
    for sid in set(list(acc.keys()) + list(geo.keys())):
        e = {}
        for pin in ("A", "B"):
            v = acc.get(sid, {}).get(pin, [])
            if v:
                e[pin] = [int(round(st.median(p[0] for p in v))), int(round(st.median(p[1] for p in v)))]
                e[pin + "_n"] = len(v)
        if ("A" not in e or "B" not in e) and geo.get(sid):
            # complementa com geométricos (ordenados: topo->base)
            cand = sorted(geo[sid].items(), key=lambda kv: (-kv[1], kv[0][1], kv[0][0]))
            cand = [c for c, _ in cand[:4]]
            if "A" not in e and cand:
                e["A"] = list(cand[0]); e["A_g"] = geo[sid][cand[0]]
            if "B" not in e and len(cand) > 1:
                e["B"] = list(cand[1]); e["B_g"] = geo[sid][cand[1]]
        e["n"] = max(e.get("A_n", 0), e.get("B_n", 0), e.get("A_g", 0), e.get("B_g", 0))
        out[sid] = e
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "pin_map.json").write_text(json.dumps(out, indent=1, sort_keys=True))
    for sid in sorted(out, key=lambda s: -out[s]["n"])[:25]:
        print(sid, out[sid])
    print("arquivos:", len(files), "| classes com pino:", len(out), "-> out/pin_map.json")


if __name__ == "__main__":
    main(sys.argv[1:])
