#!/usr/bin/env python3
"""Gera .cad sintéticos com símbolos em posições CONHECIDAS (ground-truth).

Clona entidades doadoras do corpus (mesmo render do app) e as reposiciona numa
grade. O manifesto JSON diz (classe, x, y) em coords do .cad — vira rótulo após
calibrar o mapa cad->tela.

Uso:
  python3 tools/mk_dataset.py probe      # out/ds/probe.cad  (2 motores p/ calibrar)
  python3 tools/mk_dataset.py gen N      # out/ds/case-XX.cad + out/ds/manifest.json
"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "out" / "ds"
DONOR = ROOT / "corpus" / "Arranque_1.cad"
CLASSES = ["2001", "1000", "6007", "9008", "8000", "8001", "8017", "8016"]


def load_donor():
    d = DONOR.read_bytes().decode("latin1")
    header, ents, footer = split_entities(d)
    protos = {}
    wire = None
    for e in ents:
        p = parse_ent(e)
        if not p:
            continue
        if p["id"] in CLASSES and p["id"] not in protos:
            protos[p["id"]] = p
        if p["id"] == "4000" and wire is None:
            wire = p
    return header, protos, footer, wire


def wire_at(proto, seq, x0, y0, x1, y1):
    nums = list(proto["nums"])
    nums[8], nums[9], nums[10], nums[11] = str(x0), str(y0), str(x1), str(y1)
    return f"*{seq}*{proto['id']}#" + "#".join(proto["labels"]) + "#*" + "*".join(nums)


def ent_at(proto, seq, x, y):
    nums = list(proto["nums"])
    nums[0] = nums[1] = "1"
    nums[8], nums[9] = str(x), str(y)
    return f"*{seq}*{proto['id']}#" + "#".join(proto["labels"]) + "#*" + "*".join(nums)


def build(placements, header, protos, footer, wire):
    # âncoras de extensão (fios) p/ o Zoom Todo ter SEMPRE o mesmo enquadramento
    anchors = [wire_at(wire, 1, 10, 10, 300, 10), wire_at(wire, 2, 10, 10, 10, 190)]
    body = "#".join(anchors + [ent_at(protos[c], i + 3, x, y) for i, (c, x, y) in enumerate(placements)])
    return header + body + "#" + footer


def main(argv):
    header, protos, footer, wire = load_donor()
    DS.mkdir(parents=True, exist_ok=True)
    mode = argv[0] if argv else "gen"
    if mode == "probe":
        # 2 motores (1000) em cantos conhecidos da faixa visível p/ resolver escala+offset
        pl = [("1000", 50, 40), ("1000", 260, 150)]
        (DS / "probe.cad").write_bytes(build(pl, header, protos, footer, wire).encode("latin1"))
        (DS / "probe.json").write_text(json.dumps({"casos": [{"arq": "probe.cad",
            "simbolos": [{"classe": c, "x": x, "y": y} for c, x, y in pl]}]}, indent=1), encoding="utf-8")
        print("probe.cad OK", pl)
        return
    n = int(argv[1]) if len(argv) > 1 else 8
    rng = random.Random(7)
    gx = [50, 120, 190, 260]
    gy = [40, 90, 140]
    casos = []
    for k in range(n):
        spots = [(x, y) for y in gy for x in gx]
        rng.shuffle(spots)
        picked = spots[:rng.randint(6, 9)]
        pl = [(rng.choice(CLASSES), x + rng.randint(-8, 8), y + rng.randint(-8, 8)) for x, y in picked]
        arq = f"case-{k:02d}.cad"
        (DS / arq).write_bytes(build(pl, header, protos, footer, wire).encode("latin1"))
        casos.append({"arq": arq, "simbolos": [{"classe": c, "x": x, "y": y} for c, x, y in pl]})
    (DS / "manifest.json").write_text(json.dumps({"casos": casos}, indent=1), encoding="utf-8")
    tot = sum(len(c["simbolos"]) for c in casos)
    print(f"{n} arquivos, {tot} símbolos rotulados em out/ds/")


if __name__ == "__main__":
    main(sys.argv[1:])
