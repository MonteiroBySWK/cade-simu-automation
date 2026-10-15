#!/usr/bin/env python3
"""Detector de símbolos: componentes conexos no canal preto + regras de forma.

Fios são vermelhos no CADe_SIMU: máscara fora o vermelho e classifica cada
componente preto por geometria (área, aspecto, buracos/Euler, simetria).

Uso:
  python3 tools/detect_symbols.py exemplo.png [-o out/det.json]
  python3 tools/detect_symbols.py --eval
"""
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "out" / "tpl"
VERIFY_MIN = 0.0

NOMES = {"2001": "contator", "1000": "motor", "8000": "botoeira-NA", "8001": "botoeira-NF",
         "6007": "termico", "9008": "piloto", "8017": "aux-NF", "8016": "aux-NA"}

VERDADE = {
    "exemplo01": {"2001": 1, "1000": 1, "8000": 1, "8001": 1, "6007": 1, "9008": 2, "8017": 1, "8016": 0},
    "exemplo02": {"2001": 2, "1000": 1, "8000": 1, "8001": 1, "6007": 1, "9008": 3, "8017": 1, "8016": 0},
    "exemplo03": {"2001": 3, "1000": 1, "8000": 1, "8001": 1, "6007": 1, "9008": 2, "8017": 1, "8016": 0},
}

def components(mask, minpx=12):
    H, W = mask.shape
    seen = np.zeros((H, W), bool)
    out = []
    for y in range(H):
        row = mask[y]
        xs = np.where(row & ~seen[y])[0]
        for x in xs:
            if seen[y, x]:
                continue
            q = deque([(y, x)]); seen[y, x] = True
            n = 0; x0 = y0 = 10**9; x1 = y1 = -1
            while q:
                cy, cx = q.popleft(); n += 1
                if cx < x0: x0 = cx
                if cx > x1: x1 = cx
                if cy < y0: y0 = cy
                if cy > y1: y1 = cy
                for dy in (-1, 0, 1):
                    ny = cy + dy
                    if 0 <= ny < H:
                        for dx in (-1, 0, 1):
                            nx = cx + dx
                            if 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True; q.append((ny, nx))
            if n >= minpx:
                out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "n": n})
    return out

def ncc(img, tpl):
    """Correlação cruzada normalizada exata (FFT + imagens integrais)."""
    ih, iw = img.shape
    th, tw = tpl.shape
    if th > ih or tw > iw or th < 4 or tw < 4:
        return np.zeros((1, 1)), 0, 0
    t = tpl - tpl.mean()
    if (t ** 2).sum() < 1e-9:
        return np.zeros((ih - th + 1, iw - tw + 1)), 0, 0
    n = th * tw
    F1 = np.fft.rfft2(img, s=(ih, iw))
    F2 = np.conj(np.fft.rfft2(t, s=(ih, iw)))
    full = np.fft.irfft2(F1 * F2, s=(ih, iw))
    corr = full[:ih - th + 1, :iw - tw + 1]
    ii = np.zeros((ih + 1, iw + 1)); ii[1:, 1:] = img
    ii = ii.cumsum(0).cumsum(1)
    ii2 = np.zeros((ih + 1, iw + 1)); ii2[1:, 1:] = img ** 2
    ii2 = ii2.cumsum(0).cumsum(1)
    S = ii[th:, tw:] - ii[:-th, tw:] - ii[th:, :-tw] + ii[:-th, :-tw]
    S2 = ii2[th:, tw:] - ii2[:-th, tw:] - ii2[th:, :-tw] + ii2[:-th, :-tw]
    num = corr
    den = np.sqrt(np.maximum(S2 - S * S / n, 0) * (t ** 2).sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(den > 1e-9, num / den, 0)
    return r, th, tw

def drawing_box(a):
    """Área de desenho = maior região branca (folha; exclui chrome do app)."""
    white = (np.min(a.astype(int), axis=-1) > 240)
    comps = components(white, minpx=1000)
    if not comps:
        return 0, 90, a.shape[1], a.shape[0]
    c = max(comps, key=lambda c: (c["x1"] - c["x0"]) * (c["y1"] - c["y0"]))
    return c["x0"], c["y0"], c["x1"], c["y1"]

def merge(dets, raio=45):
    dets = sorted(dets, key=lambda d: -d["escore"])
    out = []
    for d in dets:
        r = 60 if d["classe"] == "1000" else raio
        for q in out:
            if q["classe"] == d["classe"] and abs(q["x"] - d["x"]) < r and abs(q["y"] - d["y"]) < r:
                break
            # mesma fileira de polos: contator/termico fragmentado pelo fio vermelho
            if q["classe"] == d["classe"] and q["classe"] in ("2001", "6007") \
                    and abs(q["y"] - d["y"]) < 18 and abs(q["x"] - d["x"]) < 110:
                break
        else:
            out.append(d)
    return out

def holes(sub):
    """Nº de buracos (regiões de fundo não ligadas à borda)."""
    H, W = sub.shape
    bg = ~sub
    seen = np.zeros((H, W), bool)
    q = deque()
    for x in range(W):
        q += [(0, x), (H - 1, x)]
    for y in range(H):
        q += [(y, 0), (y, W - 1)]
    while q:
        cy, cx = q.popleft()
        if not (0 <= cy < H and 0 <= cx < W) or seen[cy, cx] or not bg[cy, cx]:
            continue
        seen[cy, cx] = True
        q += [(cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)]
    # buracos = componentes de fundo não visitadas (4-conexo p/ não vazar na diagonal)
    n = 0
    seen2 = np.zeros((H, W), bool)
    for y in range(H):
        for x in range(W):
            if bg[y, x] and not seen[y, x] and not seen2[y, x]:
                n += 1
                q = deque([(y, x)]); seen2[y, x] = True
                while q:
                    cy, cx = q.popleft()
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < H and 0 <= nx < W and bg[ny, nx] and not seen[ny, nx] and not seen2[ny, nx]:
                            seen2[ny, nx] = True; q.append((ny, nx))
    return n

def maxhole(sub):
    """Fração do maior buraco sobre a área (círculo do motor >> furo de dígito)."""
    H, W = sub.shape
    if H * W == 0:
        return 0
    bg = ~sub
    seen = np.zeros((H, W), bool)
    q = deque()
    for x in range(W):
        q += [(0, x), (H - 1, x)]
    for y in range(H):
        q += [(y, 0), (y, W - 1)]
    while q:
        cy, cx = q.popleft()
        if not (0 <= cy < H and 0 <= cx < W) or seen[cy, cx] or not bg[cy, cx]:
            continue
        seen[cy, cx] = True
        q += [(cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)]
    best = 0
    seen2 = np.zeros((H, W), bool)
    for y in range(H):
        for x in range(W):
            if bg[y, x] and not seen[y, x] and not seen2[y, x]:
                n = 0
                qq = deque([(y, x)]); seen2[y, x] = True
                while qq:
                    cy, cx = qq.popleft(); n += 1
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < H and 0 <= nx < W and bg[ny, nx] and not seen[ny, nx] and not seen2[ny, nx]:
                            seen2[ny, nx] = True; qq.append((ny, nx))
                best = max(best, n)
    return best / (H * W)

def classify(mask, c, so_grandes=False):
    x0, y0, x1, y1, n = c["x0"], c["y0"], c["x1"], c["y1"], c["n"]
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if w <= 0 or h <= 0:
        return None
    area = w * h
    dens = n / area
    sub = mask[y0:y1 + 1, x0:x1 + 1]
    nh = holes(sub) if area < 20000 else 0
    cx, cy = x0 + w / 2, y0 + h / 2
    if so_grandes:
        # motor: grande, ~quadrado, com buraco GRANDE (círculo; furos de dígito são miúdos)
        if w > 40 and h > 40 and 0.75 < w / h < 1.35 and dens < 0.5 and maxhole(sub) > 0.18:
            return ("1000", cx, cy, 0.9)
        # contator/termico: 3+ traços verticais longos (polos) + trilhos.
        # fileira de dígitos e linha de texto não têm colunas cheias.
        if w > 45 and h < 45 and w / h > 1.8 and area > 1200 and dens > 0.08:
            col = sub.sum(axis=0)
            cheias = int((col > h * 0.7).sum())
            if 3 <= cheias <= 8 and cheias / w < 0.3:
                return ("2001", cx, cy, 0.8)
            if 2 <= cheias <= 8 and cheias / w < 0.35:
                return ("6007", cx, cy, 0.6)
        return None
    # piloto: anel com X, ~quadrado (botão NF é alto; disjuntor tem stubs).
    # O X interno distingue de dígitos (0/8/6/9 têm buraco mas sem diagonais).
    if 18 <= w <= 34 and 18 <= h <= 34 and 1 <= nh <= 5 and 0.8 < w / h < 1.25:
        # lâmpada de painel é isolada; disjuntor tem fio/stub vertical grudado
        if y0 > 10 and mask[y0 - 10:y0, x0:x1 + 1].sum() > 3:
            return None
        if y1 + 11 < mask.shape[0] and mask[y1 + 1:y1 + 11, x0:x1 + 1].sum() > 3:
            return None
        m = min(h, w)
        cut = sub[max(0, (h - m) // 2):max(0, (h - m) // 2) + m, max(0, (w - m) // 2):max(0, (w - m) // 2) + m]
        d1 = np.diag(cut).mean() if m > 4 else 0
        d2 = np.diag(np.fliplr(cut)).mean() if m > 4 else 0
        if d1 > 0.08 and d2 > 0.08:
            return ("9008", cx, cy, 0.8)
        return None
    # piloto de painel ACESO: disco sólido vermelho ou verde (ponto de fio é menor)
    if 18 <= w <= 44 and 18 <= h <= 44 and 0.7 < w / h < 1.4 and dens > 0.55:
        return ("9008", cx, cy, 0.85)
    # botoeiras/aux: miúdos e altos, com stubs de terminal em cima/embaixo
    # (fio vertical + dígito não tem stubs nos cantos). NF tem ponte no terço médio.
    if 8 <= w <= 26 and h >= 18 and h / max(w, 1) > 1.2:
        topo = sub[:max(2, h // 7), :]
        base = sub[-max(2, h // 7):, :]
        def stubs(faixa):
            t = faixa.shape[1] // 3
            L = faixa[:, :t].sum() > 0
            R = faixa[:, -t:].sum() > 0
            M = faixa[:, t:-t].sum() if faixa.shape[1] > 2 else 0
            return L and R and M < (L + R)
        if not (stubs(topo) or stubs(base)):
            return None
        meio = sub[:, w // 3:2 * w // 3 + 1].mean() if w >= 9 else 0
        return ("8001", cx, cy, 0.6) if meio > 0.12 else ("8000", cx, cy, 0.6)
    return None

def detect(imagem):
    img = Image.open(imagem).convert("RGB")
    a = np.asarray(img)
    gx0, gy0, gx1, gy1 = drawing_box(a)
    a = a[gy0:gy1 + 1, gx0:gx1 + 1]
    R, G, B = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
    gray_crop = np.asarray(Image.open(imagem).convert("L"))[gy0:gy1 + 1, gx0:gx1 + 1].astype(float)
    vermelho = (R > 120) & (R - G > 50) & (R - B > 50)  # fio + halo antialiased
    marca = (R > 150) & (B > 150)  # marca-d'água lilás do blog (letras com furo/diagonal!)
    tinta = (np.min(a, axis=-1) < 160) & ~vermelho & ~marca
    # agrupa fragmentos (fio vermelho removido corta os símbolos): dilata e reagrupa
    dil = np.asarray(Image.fromarray(tinta).filter(ImageFilter.MaxFilter(7)))
    dets = []
    # passe 1 (pequenos, sem dilatar): botoeiras/aux/pilotos intactos
    for c in components(tinta, minpx=30):
        if c["x1"] - c["x0"] + 1 < 7:
            continue  # dígitos de pinagem são mais finos que qualquer símbolo
        r = classify(tinta, c, so_grandes=False)
        if r and r[0] not in ("1000", "2001", "6007"):
            cls, cx, cy, conf = r
            dets.append({"classe": cls, "nome": NOMES[cls], "x": int(gx0 + cx), "y": int(gy0 + cy),
                         "escore": conf, "w": c["x1"] - c["x0"] + 1, "h": c["y1"] - c["y0"] + 1})
    # passe 2 (grandes, com dilatação): contator/motor/termico fragmentados
    for g in components(dil > 0, minpx=60):
        sub = tinta[g["y0"]:g["y1"] + 1, g["x0"]:g["x1"] + 1]
        c = dict(g, n=int(sub.sum()))
        r = classify(tinta, c, so_grandes=True)
        if r:
            cls, cx, cy, conf = r
            dets.append({"classe": cls, "nome": NOMES[cls], "x": int(gx0 + cx), "y": int(gy0 + cy),
                         "escore": conf, "w": c["x1"] - c["x0"] + 1, "h": c["y1"] - c["y0"] + 1})
    # fileiras de polos: contator fatiado pelo fio vermelho vira traços
    # verticais alinhados (>=3 na mesma banda, abrangendo >45px)
    strokes = []
    for c in components(tinta, minpx=15):
        w, h = c["x1"] - c["x0"] + 1, c["y1"] - c["y0"] + 1
        if w <= 13 and h >= 18:
            strokes.append(c)
    usados = set()
    for s in strokes:
        cy = (s["y0"] + s["y1"]) / 2
        fila = [t for t in strokes
                if abs((t["y0"] + t["y1"]) / 2 - cy) < 14 and abs(t["x0"] - s["x0"]) < 130]
        if len(fila) >= 3:
            xs = sorted(t["x0"] for t in fila)
            if xs[-1] - xs[0] > 45 and all(id(t) not in usados for t in fila):
                for t in fila:
                    usados.add(id(t))
                dets.append({"classe": "2001", "nome": NOMES["2001"],
                             "x": int(gx0 + sum(t["x0"] + t["x1"] for t in fila) / (2 * len(fila))),
                             "y": int(gy0 + sum(t["y0"] + t["y1"] for t in fila) / (2 * len(fila))),
                             "escore": 0.75,
                             "w": xs[-1] - xs[0] + 12,
                             "h": max(t["y1"] - t["y0"] for t in fila) + 10})
    # lâmpadas de painel ACESAS em vermelho: disco sólido (fora da tinta).
    for c in components(vermelho[gy0:gy1 + 1, gx0:gx1 + 1], minpx=60):
        w, h = c["x1"] - c["x0"] + 1, c["y1"] - c["y0"] + 1
        if 12 <= w <= 44 and 12 <= h <= 44 and 0.7 < w / h < 1.4 and c["n"] / (w * h) > 0.5:
            dets.append({"classe": "9008", "nome": NOMES["9008"],
                         "x": int(gx0 + (c["x0"] + c["x1"]) / 2),
                         "y": int(gy0 + (c["y0"] + c["y1"]) / 2), "escore": 0.9, "w": w, "h": h})
    return merge(dets)

def verify(gray, dets, gx0, gy0):
    """Confirma cada proposta via NCC contra o template da classe (corta FP)."""
    from PIL import Image as I
    ok = []
    for d in dets:
        if d["classe"] == "9008" and d["escore"] >= 0.85:
            ok.append(d)  # disco sólido já é evidência forte
            continue
        tpath = TPL / f"{d['classe']}.png"
        if not tpath.exists():
            ok.append(d)
            continue
        t = np.asarray(I.open(tpath).convert("L")).astype(float)
        x0 = max(0, int(d["x"] - gx0 - d["w"] / 2))
        y0 = max(0, int(d["y"] - gy0 - d["h"] / 2))
        prop = gray[y0:y0 + d["h"], x0:x0 + d["w"]]
        if prop.size == 0 or prop.shape[0] < 6 or prop.shape[1] < 6:
            continue
        tr = np.asarray(I.fromarray(t.astype("uint8")).resize((prop.shape[1], prop.shape[0]))).astype(float)
        r, _, _ = ncc(prop, tr)
        if float(r.max()) >= VERIFY_MIN:
            d["escore"] = round(float(r.max()), 3)
            ok.append(d)
    return ok

def main(argv):
    if "--eval" in argv:
        base = Path("/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]/Exemplos (diagramas)/Comandos Elétricos")
        tc = td = tv = 0
        for ex, verdade in VERDADE.items():
            f = next(p for p in base.iterdir() if p.stem == ex)
            dets = detect(f)
            from collections import Counter
            c = Counter(d["classe"] for d in dets)
            pc = sum(min(c.get(k, 0), v) for k, v in verdade.items())
            pv, pd = sum(verdade.values()), sum(c.values())
            tc += pc; td += pd; tv += pv
            print(f"{ex}: det={dict(c)} verdade={verdade} P={pc/max(pd,1):.2f} R={pc/max(pv,1):.2f}", flush=True)
            for d in dets:
                print(f"   {d['classe']} {d['nome']} @{d['x']},{d['y']} {d['escore']}")
        print(f"TOTAL: P={tc/max(td,1):.2f} R={tc/max(tv,1):.2f}")
        return
    src = Path(argv[0])
    dets = detect(src)
    print(f"{len(dets)} detecções em {src.name}")
    for d in dets:
        print(f"  {d['classe']} {d['nome']} @{d['x']},{d['y']} escore={d['escore']}")
    if "-o" in argv:
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps({"fonte": str(src), "deteccoes": dets}, indent=1))

if __name__ == "__main__":
    main(sys.argv[1:])
