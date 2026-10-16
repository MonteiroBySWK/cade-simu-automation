#!/usr/bin/env python3
"""Mescla docs/pinos-binario.json (verdade do binario) em tools/symbol_pins.json.

Regra: classes AUSENTES entram com os pinos do binario (nomes reais ou pN; A/B = 1o/2o pino).
Classes presentes so ganham pinos nomeados que faltam (nunca sobrescreve offsets ja medidos).
Divergencias de A/B (estatistica x binario) sao listadas; --override-ab aplica o binario.

Uso: python3 tools/apply_bin_pins.py [--dry] [--override-ab]
"""
import json
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
BIN = json.loads((T.parent / "docs" / "pinos-binario.json").read_text())["classes"]
PINS = json.loads((T / "symbol_pins.json").read_text())


def main(dry):
    novas, completadas, diverg = [], [], []
    for cid, v in BIN.items():
        bp = v["pins"]
        nomes = list(bp)
        if cid not in PINS:
            e = {"fonte": "binario (docs/pinos-binario.json)", "pins": {k: list(p) for k, p in bp.items()}}
            if nomes:
                e["A"] = list(bp[nomes[0]])
            if len(nomes) > 1:
                e["B"] = list(bp[nomes[1]])
            PINS[cid] = e
            novas.append(cid)
            continue
        e = PINS[cid]
        have = e.setdefault("pins", {})
        add = {k: list(p) for k, p in bp.items() if k not in have and not k.startswith("p")}
        if add:
            have.update(add)
            completadas.append(cid)
        if nomes and "A" in e and e["A"] != list(bp[nomes[0]]):
            diverg.append((cid, e["A"], list(bp[nomes[0]])))
            if "--override-ab" in sys.argv:       # binario e a verdade (estatistica = ruido)
                e["A"] = list(bp[nomes[0]])
                if len(nomes) > 1:
                    e["B"] = list(bp[nomes[1]])
                e["fonte"] = "binario (A/B sobrescritos)"
    print(f"novas={len(novas)} completadas={completadas} diverg_A={len(diverg)}")
    for c, a, b in diverg[:40]:
        print(f"  {c}: estatistico A={a} binario p1={b}")
    if not dry:
        (T / "symbol_pins.json").write_text(json.dumps(PINS, indent=1, sort_keys=True))


if __name__ == "__main__":
    main("--dry" in sys.argv)
