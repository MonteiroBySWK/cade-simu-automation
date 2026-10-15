#!/usr/bin/env python3
"""Reconstrói os pinos por classe a partir da saída de pins_dump.java.

Uso: python3 tools/ghidra/pins_from_dump.py <pins_dump.txt> [saida.json]

Fórmula (FUN_008462f0, comando NUME, ver docs/re-engenharia.md §10):
  NUME,<lx>,<ly>,...  (unidades de desenho = 1/5 px, relativas a (X,Y) da entidade)
  - classes 3000..3011 (bornes): lx += 9 se o 2º caractere do rótulo for ' ' senão +13;
    ly += 35  (antes da rotação)
  - classes "ponto" (conjunto C1AC abaixo): pino = (lx-5, ly)
  - demais: pino = (lx-5, ly+15 se ly>0 senão ly)
  - px = unidades/5; depois aplica a orientação n17 (tabela ROT).
Um NUME só vira ponto-pino quando seguido da varredura de fios (CMP id,4000..4019).
"""
import json
import re
import sys
from collections import OrderedDict

# conjunto local_1ac==1 em FUN_008462f0 (@0x84b9ac..): sem o ajuste +15
def is_c1ac(i):
    rngs = [(0x1d4f, 0x1d51), (0x1d55, 0x1d57), (0x1d5b, 0x1d5d), (0x1d63, 0x1d65),
            (0x1d69, 0x1d6b), (0x1d6f, 0x1d71), (0x1d95, 0x1d97), (0x1d9b, 0x1d9d),
            (0x1dad, 0x1daf), (0x1da1, 0x1da3), (0x1da7, 0x1da9), (0x1db3, 0x1db5),
            (0x1d84, 0x1d86), (0x1d8a, 0x1d8c), (10000, 10041), (0x274f, 0x2755)]
    if any(a <= i <= b for a, b in rngs):
        return True
    return i in (0x1d80, 0x275b, 0x275d, 0x275e, 0x275f, 0x2760, 0x2761, 0x2762, 0x2763,
                 0x3f3, 0x3f4, 0x2777)

# orientação n17 (bloco PUNT de FUN_008462f0): (x,y) -> ...
ROT = {0: lambda x, y: (x, y), 1: lambda x, y: (-y, x), 2: lambda x, y: (-x, -y),
       3: lambda x, y: (y, -x), 4: lambda x, y: (-x, y), 5: lambda x, y: (-y, -x),
       6: lambda x, y: (x, -y), 7: lambda x, y: (y, x)}

GENERIC = {0x854ae0, 0x8571b0}  # rotinas comuns chamadas p/ várias classes (não são o desenho)


def parse(path):
    classes = OrderedDict()
    funcs = {}
    cur = None
    for ln in open(path, encoding="latin-1"):
        ln = ln.rstrip("\n")
        if ln.startswith("CLASS "):
            _, c, f = ln.split()
            classes.setdefault(int(c), []).append(int(f, 16))
        elif ln.startswith("FUNC "):
            cur = int(ln.split()[1], 16)
            funcs[cur] = []
        elif cur is not None and ln.startswith("  "):
            p = ln.split(None, 2)
            funcs[cur].append((int(p[0], 16), p[1], p[2] if len(p) > 2 else ""))
    return classes, funcs


def root_of(cands, spam):
    for f in cands:
        if f not in GENERIC and f not in spam:
            return f
    for f in cands:
        if f not in GENERIC:
            return f
    return cands[0]


def walk(funcs, f, depth=0, seen=None):
    """sequência linear (inline de chamadas) de eventos (tipo, valor)."""
    seen = seen or set()
    out = []
    if f in seen or depth > 3:
        return out
    seen = seen | {f}
    for a, t, v in funcs.get(f, []):
        if t == "C":
            out += walk(funcs, int(v, 16), depth + 1, seen)
        else:
            out.append((t, v))
    return out


NUME = re.compile(r"NUME,([+-]\d{3}),([+-]\d{3}),?(.*)")


def pins_for(cid, events):
    res = []  # (lx, ly, hit)
    pend = None
    for t, v in events:
        if t == "S":
            m = NUME.match(v)
            if m:
                if pend:
                    res.append(pend)
                pend = [int(m.group(1)), int(m.group(2)), False, m.group(3)]
        elif t == "K" and pend and v.startswith("0x2024 ") and v.split()[1] in ("4000", "4009", "4010", "4018", "4019"):
            pend[2] = True
    if pend:
        res.append(pend)
    uniq = OrderedDict()
    lab = {}
    for lx, ly, hit, label in res:
        k = (lx, ly)
        uniq[k] = uniq.get(k, False) or hit
        lab.setdefault(k, label)
    return [(lx, ly, hit, lab[(lx, ly)]) for (lx, ly), hit in uniq.items()]


def to_px(cid, lx, ly, borne_space=True):
    if 3000 <= cid <= 3011:
        lx += 9 if borne_space else 13
        ly += 35
    x = lx - 5
    y = ly if (is_c1ac(cid) or ly <= 0) else ly + 15
    return x / 5, y / 5


def main():
    classes, funcs = parse(sys.argv[1])
    # a classe 9008 aparece "colada" a centenas de chamadas (fim do despacho): spam = todas menos a 1ª
    spam = set(classes.get(9008, [])[1:])
    out = OrderedDict()
    for cid in sorted(classes):
        root = root_of(classes[cid], spam)
        pins = pins_for(cid, walk(funcs, root))
        ent = {"func": "%06x" % root, "pins": []}
        for lx, ly, hit, label in pins:
            # bornes: 2º caractere do rótulo ' ' (rótulo de 1 char; "%c%c%c%c" = rótulo do usuário,
            # assumido de 1 char) -> +9, senão +13. Ghidra apara espaços finais da string.
            space = label.startswith("%c") or len(label) < 2 or label[1] == " "
            px = to_px(cid, lx, ly, space)
            ent["pins"].append({"nume": [lx, ly], "label": label, "px": [px[0], px[1]], "hit": hit})
        out[str(cid)] = ent
    s = json.dumps(out, indent=1)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(s)
    else:
        print(s)


if __name__ == "__main__":
    main()
