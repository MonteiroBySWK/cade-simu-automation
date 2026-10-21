#!/usr/bin/env python3
import os
"""Aprende os pinos A/B por classe olhando onde os FIOS ENCOSTAM na caixa do símbolo.

Mais confiável que correlação por net (funciona p/ símbolos multi-pino, como o
motor). Para cada símbolo de cada .cad do acervo: coleta offsets dos endpoints de
fio que tocam a borda da caixa; agrega por classe e escolhe os 2 mais frequentes
(A = topo/esquerda, B = o seguinte).

Saída: tools/symbol_pins.json (mescla; preserva entradas com "nota" manual).
Uso: python3 tools/learn_pins2.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dissect import parse_ent, split_entities  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
import sys as _s
from pathlib import Path as _P
_s.path.insert(0, str(_P(__file__).resolve().parent))
import cade_config  # noqa: E402
ACERVO = cade_config.acervo()
WIRE = {"4000", "4018", "4009"}
TOL = 2


def main():
    acc = {}
    for f in sorted(list((ROOT / "corpus").glob("*.cad")) + (sorted(ACERVO.glob("*.cad")) if ACERVO.is_dir() else [])):
        try:
            d = f.read_bytes().decode("latin1")
            _, ents, _ = split_entities(d)
        except Exception:
            continue
        syms, pts = [], []
        for e in ents:
            p = parse_ent(e)
            if not p:
                continue
            n = p["nums"]
            try:
                x, y = int(n[8]), int(n[9])
            except (ValueError, IndexError):
                continue
            if p["id"] in WIRE:
                pts += [(int(n[8]), int(n[9])), (int(n[10]), int(n[11]))]
            elif p["id"] != "8":
                try:
                    w, h = int(n[14]), int(n[15])
                except (ValueError, IndexError):
                    continue
                if w > 0 and h > 0:
                    syms.append((p["id"], x, y, w, h))
        for (cid, x, y, w, h) in syms:
            for (px, py) in pts:
                dx, dy = px - x, py - y
                # toca a borda (dentro da caixa, sobre a borda, ou a <=2px dela)
                if -TOL <= dx <= w + TOL and -TOL <= dy <= h + TOL:
                    na_borda = (abs(dx) <= TOL or abs(dx - w) <= TOL or abs(dy) <= TOL or abs(dy - h) <= TOL)
                    if na_borda:
                        acc.setdefault(cid, Counter())[(dx, dy)] += 1
    p = ROOT / "tools" / "symbol_pins.json"
    atual = json.loads(p.read_text())
    novos = 0
    for cid, cnt in sorted(acc.items()):
        if atual.get(cid, {}).get("nota"):
            continue                      # preserva entradas manuais/evidenciadas
        top = cnt.most_common(4)
        if not top or top[0][1] < 3:
            continue
        top = sorted([o for o, k in top if k >= max(2, top[0][1] // 6)], key=lambda o: (o[1], o[0]))
        e = {"A": list(top[0]), "n": int(top[0][1]), "fonte": "learn_pins2"}
        if len(top) > 1:
            e["B"] = list(top[1])
        atual[cid] = e
        novos += 1
    json.dump(atual, p.open("w"), indent=1, sort_keys=True)
    print(f"classes atualizadas: {novos} | total: {len(atual)}")
    for cid in ("1000", "6009", "2001", "6007", "8017", "8000", "8001", "7000", "9000", "9008"):
        print(" ", cid, atual.get(cid))


if __name__ == "__main__":
    main()
