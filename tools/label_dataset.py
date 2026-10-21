#!/usr/bin/env python3
"""Rotula renders do dataset: aplica o transform cad->tela e recorta cada símbolo.

Transform calibrado (janela maximizada + Ver>Zoom Todo, Xvfb 1280x1024):
    screen_x = 50  + 1.995 * cad_x_center
    screen_y = 124 + 2.045 * cad_y_center

Uso:
  python3 tools/label_dataset.py            # rotula out/ds/*.png -> out/dataset/<classe>/
  python3 tools/label_dataset.py --detect   # só roda o detector e mede P/R vs manifesto
  python3 tools/label_dataset.py --sheet    # contact sheet p/ revisão visual
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "out" / "ds"
OUT = ROOT / "out" / "dataset"
SHEET = ROOT / "out" / "ds" / "sheet"
SX, SY, OX, OY = 1.995, 2.045, 50.0, 124.0
# recorte fixo da folha nos renders do dataset (janela maximizada + Zoom Todo)
SHEET_BOX = (35, 95, 730, 545)


def sheet_img(png):
    SHEET.mkdir(parents=True, exist_ok=True)
    out = SHEET / Path(png).name
    if not out.exists():
        Image.open(png).convert("RGB").crop(SHEET_BOX).save(out)
    return out


def cad_to_screen(x, y):
    return OX + SX * x, OY + SY * y


def load_manifest():
    return json.loads((DS / "manifest.json").read_text(encoding="utf-8"))["casos"]


def harvest_negatives():
    """Componentes de tinta LONGE de qualquer símbolo rotulado viram classe '0' (rejeição)."""
    casos = load_manifest()
    sys.path.insert(0, str(ROOT / "tools"))
    import numpy as np
    import detect_symbols as D
    (OUT / "0").mkdir(parents=True, exist_ok=True)
    n = 0
    for caso in casos:
        png = DS / (caso["arq"].replace(".cad", ".png"))
        if not png.exists():
            continue
        img = Image.open(png).convert("RGB")
        a = np.asarray(img)
        gx0, gy0, gx1, gy1 = D.drawing_box(a)
        a2 = a[gy0:gy1 + 1, gx0:gx1 + 1]
        R, G, B = a2[:, :, 0].astype(int), a2[:, :, 1].astype(int), a2[:, :, 2].astype(int)
        tinta = (np.min(a2, axis=-1) < 160) & ~((R > 120) & (R - G > 50) & (R - B > 50)) & ~((R > 150) & (B > 150))
        gt = [cad_to_screen(s["x"] + 9, s["y"] + 7) for s in caso["simbolos"]]
        for c in D.components(tinta, minpx=30):
            cx, cy = gx0 + (c["x0"] + c["x1"]) / 2, gy0 + (c["y0"] + c["y1"]) / 2
            if min((abs(cx - x) + abs(cy - y)) for x, y in gt) < 60:
                continue
            box = (int(cx - 45), int(cy - 40), int(cx + 45), int(cy + 40))
            img.crop(box).save(OUT / "0" / f"{caso['arq'][:-4]}_n{n}.png")
            n += 1
    print(f"{n} negativos colhidos em out/dataset/0/")


def main(argv):
    casos = load_manifest()
    if "--negatives" in argv:
        harvest_negatives()
        return
    if "--detect" in argv:
        sys.path.insert(0, str(ROOT / "tools"))
        import detect_symbols as D
        from collections import Counter
        func = D.detect_knn if "--knn" in argv else D.detect
        tc = td = tv = 0
        for caso in casos:
            png = DS / (caso["arq"].replace(".cad", ".png"))
            if not png.exists():
                print(f"falta {png.name}"); continue
            verdade = Counter(s["classe"] for s in caso["simbolos"])
            det = Counter(m["classe"] for m in func(sheet_img(png)))
            pc = sum(min(det.get(k, 0), v) for k, v in verdade.items())
            pv, pd = sum(verdade.values()), sum(det.values())
            tc += pc; td += pd; tv += pv
            print(f"{caso['arq']}: det={dict(det)} verdade={dict(verdade)} "
                  f"P={pc/max(pd,1):.2f} R={pc/max(pv,1):.2f}")
        print(f"TOTAL: P={tc/max(td,1):.2f} R={tc/max(tv,1):.2f}")
        return
    for cls in ["0", "2001", "1000", "6007", "9008", "8000", "8001", "8017", "8016"]:
        (OUT / cls).mkdir(parents=True, exist_ok=True)
    n = 0
    for caso in casos:
        png = DS / (caso["arq"].replace(".cad", ".png"))
        if not png.exists():
            continue
        img = Image.open(sheet_img(png)).convert("RGB")
        for i, s in enumerate(caso["simbolos"]):
            cx, cy = cad_to_screen(s["x"] + 9, s["y"] + 7)   # ~centro do símbolo
            cx -= SHEET_BOX[0]; cy -= SHEET_BOX[1]
            half_w, half_h = 55, 45
            box = (int(cx - half_w), int(cy - half_h), int(cx + half_w), int(cy + half_h))
            img.crop(box).save(OUT / s["classe"] / f"{caso['arq'][:-4]}_{i}.png")
            n += 1
    print(f"{n} crops rotulados em out/dataset/")
    if "--sheet" in argv:
        cls_list = [p for p in ["2001", "1000", "6007", "9008", "8000", "8001", "8017", "8016"]]
        cols = 6; cell = (110, 90)
        sheet = Image.new("RGB", (cell[0] * cols, cell[1] * len(cls_list)), "white")
        dr = ImageDraw.Draw(sheet)
        for r, cls in enumerate(cls_list):
            dr.text((4, r * cell[1] + 2), cls, fill="black")
            files = sorted((OUT / cls).glob("*.png"))[:cols]
            for c, f in enumerate(files):
                im = Image.open(f); sheet.paste(im, (c * cell[0], r * cell[1] + 14))
        sheet.save(OUT / "_sheet.png")
        print("sheet:", OUT / "_sheet.png")


if __name__ == "__main__":
    main(sys.argv[1:])
