#!/usr/bin/env python3
"""Render de conferencia de um .cad: pinos nomeados, cor por FASE estampada, pinos soltos/curtos.

Conectividade por GEOMETRIA (mesmas regras de tools/geo_check.py, docs/re-engenharia.md 9.2),
para o agente VER o que o simulador vai ver:
  - fio colorido pela fase da rede (L1 laranja, L2 roxo, L3 azul, N ciano, PE verde);
  - rede com 2 fases = CURTO (vermelho grosso + X);
  - pino SEM fio no ponto = SOLTO (circulo vermelho cheio);
  - pino ligado = ponto cinza; nome do pino ao lado; rotulo do simbolo e classe no corpo.

Uso: python3 tools/cad_render.py in.cad -o out.png [--scale 3]
"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import geo_check as G  # noqa: E402
from dissect import parse_ent, split_entities  # noqa: E402

FASE_COR = {"1": (230, 120, 0), "2": (140, 60, 190), "3": (30, 90, 220), "N": (0, 150, 170), "P": (40, 150, 60)}
FASE_NOME = {"1": "L1", "2": "L2", "3": "L3", "N": "N", "P": "PE"}
PASSA = {"6009", "6010", "6007", "2001"}      # dispositivos 1->2, 3->4, 5->6 (propagacao visual da fase)
PAR = {"1", "2", "3", "4", "5", "6"}
CINZA = (90, 90, 90)
VERMELHO = (220, 0, 0)


def _folha():
    """Area segura da folha (tools/sheet.json, medida no app); fallback conservador."""
    try:
        d = json.loads((TOOLS / "sheet.json").read_text())
        return int(d["x_seguro_max"]), int(d["y_seguro_max"])
    except Exception:
        return 455, 295


FOLHA = _folha()


def _nome_amigavel(cid, off, nome_bin):
    """Nome de pino do binario (p1..pN) -> nome nomeado de tools/symbol_pins.json (1,3,5 / U1...) se houver."""
    e = G.PINS.get(cid, {})
    for nome, o in (e.get("pins") or {}).items():
        if tuple(o) == tuple(off):
            return nome
    for nome in ("A", "B"):
        if nome in e and tuple(e[nome]) == tuple(off):
            return nome
    return nome_bin


def analisar_geometria(path):
    """Estrutura para render/relatorio: fios com fase, pinos (ligado/solto), curtos, simbolos."""
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
        if p["id"] in G.WIRE:
            a = (int(p["nums"][8]), int(p["nums"][9]))
            b = (int(p["nums"][10]), int(p["nums"][11]))
            fios.append((a, b))
            union(a, b)
    juncoes = []
    for p in ps:
        if p["id"] in ("4001", "4012"):
            pt = (int(p["nums"][8]), int(p["nums"][9]))
            juncoes.append(pt)
            find(pt)
            for a, b in fios:
                x1, y1, x2, y2 = min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
                if (y1 == y2 == pt[1] and x1 <= pt[0] <= x2) or (x1 == x2 == pt[0] and y1 <= pt[1] <= y2):
                    union(pt, a)
    extremos = {pt for a, b in fios for pt in (a, b)}
    simbolos, pinos, textos = [], [], []
    estampas = {}                                   # raiz -> {char: [origens]}
    for p in ps:
        x, y = int(p["nums"][8]), int(p["nums"][9])
        if p["id"] == "8":
            textos.append((x, y, p["raw"].split("#")[-1][:30]))
            continue
        if p["id"] in G.SKIP:
            continue
        o = int(p["nums"][17] or 0)
        rot = (p["labels"] or [""])[0] or p["id"]
        w, h = int(p["nums"][14]), int(p["nums"][15])
        simbolos.append({"rotulo": rot, "classe": p["id"], "x": x, "y": y, "w": w, "h": h})
        for nome, (dx, dy) in G.pinos_da_classe(p["id"]).items():
            rx, ry = G._rot(dx, dy, o)
            pt = (x + rx, y + ry)
            ligado = pt in extremos
            pinos.append({"rotulo": rot, "classe": p["id"], "nome": _nome_amigavel(p["id"], (dx, dy), nome),
                          "pt": pt, "ligado": ligado, "topo": dy <= 3, "sx": x, "sy": y})
            if ligado and p["id"] in G.FONTE and nome in G.CHAR:
                estampas.setdefault(find(pt), {}).setdefault(G.CHAR[nome], []).append(f"{rot}.{nome}")
    curto_raiz = {r for r, m in estampas.items() if len(m) > 1}
    fase_raiz = {r: next(iter(m)) for r, m in estampas.items() if len(m) == 1}
    # propagacao APENAS visual: fase atravessa disjuntor/termico/contator (1->2, 3->4, 5->6) como se
    # fechados; rede com 2 fases propagadas (ex.: reversao no motor) fica cinza — nao e curto.
    arestas = []
    fase_prop = dict(fase_raiz)
    pares = {}
    for p in pinos:
        if p["ligado"] and p["classe"] in PASSA and p["nome"] in PAR:
            pares.setdefault((p["rotulo"], p["classe"], p["sx"], p["sy"]), {})[p["nome"]] = find(p["pt"])
    for m in pares.values():
        for a, b in (("1", "2"), ("3", "4"), ("5", "6")):
            if a in m and b in m:
                arestas.append((m[a], m[b]))
    conflito = set()
    for _ in range(8):
        mudou = False
        for a, b in arestas:
            for x, y in ((a, b), (b, a)):
                if x in fase_prop and fase_prop[x] and x not in conflito:
                    ch = fase_prop[x]
                    if y not in fase_prop:
                        fase_prop[y] = ch
                        mudou = True
                    elif fase_prop[y] != ch and y not in curto_raiz:
                        if y not in conflito:
                            conflito.add(y)
                            fase_prop[y] = None
                            mudou = True
        if not mudou:
            break
    fios_c = [{"a": a, "b": b, "fase": fase_prop.get(find(a)), "curto": find(a) in curto_raiz} for a, b in fios]
    return {"fios": fios_c, "pinos": pinos, "simbolos": simbolos, "textos": textos,
            "juncoes": juncoes, "n_curtos": len(curto_raiz),
            "soltos": [p for p in pinos if not p["ligado"]]}


def _fonte(tam):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:           # Pillow antigo: sem parametro de tamanho
        return ImageFont.load_default()


def renderizar(path, scale=3):
    """-> PIL.Image. Canvas = conteudo + margem (a folha segura, de tools/sheet.json, e so informada na legenda)."""
    from PIL import Image, ImageDraw
    g = analisar_geometria(path)
    xs = [200] + [s["x"] + max(s["w"], 0) for s in g["simbolos"]] + \
         [c for f in g["fios"] for c in (f["a"][0], f["b"][0])]
    ys = [140] + [s["y"] + max(s["h"], 0) for s in g["simbolos"]] + \
         [c for f in g["fios"] for c in (f["a"][1], f["b"][1])]
    W, H = max(xs) + 20, max(ys) + 24          # + legenda
    S = lambda v: int(v) * scale                   # noqa: E731
    img = Image.new("RGB", (W * scale, H * scale), "white")
    dr = ImageDraw.Draw(img)
    f_pino, f_rot, f_leg = _fonte(max(8, 3 * scale)), _fonte(max(9, 4 * scale)), _fonte(max(10, 4 * scale))
    for s in g["simbolos"]:
        dr.rectangle([S(s["x"]), S(s["y"]), S(s["x"] + s["w"]), S(s["y"] + s["h"])], outline=(60, 60, 60))
        dr.text((S(s["x"]), S(s["y"]) - 2 * scale), f"{s['rotulo']} [{s['classe']}]", fill=(120, 0, 120),
                font=f_rot, anchor="ls")
    for t in g["textos"]:
        dr.text((S(t[0]), S(t[1])), t[2], fill=(0, 0, 0), font=f_rot)
    lw = max(2, scale)
    for f in g["fios"]:
        a, b = f["a"], f["b"]
        cor = VERMELHO if f["curto"] else FASE_COR.get(f["fase"], CINZA)
        w = lw + 2 if f["curto"] else (lw if f["fase"] else max(1, scale // 2 + 1))
        if a == b:
            dr.ellipse([S(a[0]) - 3, S(a[1]) - 3, S(a[0]) + 3, S(a[1]) + 3], fill=cor)
        else:
            dr.line([S(a[0]), S(a[1]), S(b[0]), S(b[1])], fill=cor, width=w)
        if f["curto"]:
            mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
            dr.line([S(mx) - 5, S(my) - 5, S(mx) + 5, S(my) + 5], fill=VERMELHO, width=2)
            dr.line([S(mx) - 5, S(my) + 5, S(mx) + 5, S(my) - 5], fill=VERMELHO, width=2)
    for j in g["juncoes"]:
        dr.ellipse([S(j[0]) - 3, S(j[1]) - 3, S(j[0]) + 3, S(j[1]) + 3], fill=(0, 0, 0))
    for p in g["pinos"]:
        x, y = S(p["pt"][0]), S(p["pt"][1])
        if p["ligado"]:
            dr.ellipse([x - 2, y - 2, x + 2, y + 2], fill=CINZA)
            dr.text((x + 4, y + 1 if p["topo"] else y - 4 * scale), p["nome"], fill=(70, 70, 70), font=f_pino)
        else:
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=VERMELHO, outline=(120, 0, 0))
            dr.text((x + 7, y + 1 if p["topo"] else y - 4 * scale), f"{p['nome']}?", fill=VERMELHO, font=f_pino)
    # legenda
    ly = S(max(ys) + 4)
    lx = S(4)
    for ch in ("1", "2", "3", "N", "P"):
        dr.line([lx, ly + 6, lx + 22, ly + 6], fill=FASE_COR[ch], width=lw + 1)
        dr.text((lx + 26, ly), FASE_NOME[ch], fill=(0, 0, 0), font=f_leg)
        lx += 70
    dr.ellipse([lx, ly, lx + 10, ly + 10], fill=VERMELHO)
    dr.text((lx + 14, ly), f"solto ({len(g['soltos'])})", fill=VERMELHO, font=f_leg)
    lx += 150
    dr.line([lx, ly + 6, lx + 22, ly + 6], fill=VERMELHO, width=lw + 2)
    dr.text((lx + 26, ly), f"curto ({g['n_curtos']})", fill=VERMELHO, font=f_leg)
    fora = max(xs) > FOLHA[0] or max(ys) > FOLHA[1]
    dr.text((lx + 130, ly), f"extensao {max(xs)}x{max(ys)} / folha segura {FOLHA[0]}x{FOLHA[1]}"
            + ("  FORA DA FOLHA" if fora else ""), fill=VERMELHO if fora else (90, 90, 90), font=f_leg)
    return img


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    out, scale, src = "out/preview.png", 3, argv[0]
    i = 1
    while i < len(argv):
        if argv[i] == "-o":
            out, i = argv[i + 1], i + 2
        elif argv[i] == "--scale":
            scale, i = int(argv[i + 1]), i + 2
        else:
            i += 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    renderizar(src, scale).save(out)
    print(f"preview -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
