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
SX, SY, OX, OY = 1.995, 2.045, 50.0, 124.0


def cad_to_screen(x, y):
    return OX + SX * x, OY + SY * y


def load_manifest():
    return json.loads((DS / "manifest.json").read_text())["casos"]


def main(argv):
    casos = load_manifest()
    if "--detect" in argv:
        sys.path.insert(0, str(ROOT / "tools"))
        import detect_symbols as D
        from collections import Counter
        tc = td = tv = 0
        for caso in casos:
            png = DS / (caso["arq"].replace(".cad", ".png"))
            if not png.exists():
                print(f"falta {png.name}"); continue
            verdade = Counter(s["classe"] for s in caso["simbolos"])
            det = Counter(m["classe"] for m in D.detect(png))
            pc = sum(min(det.get(k, 0), v) for k, v in verdade.items())
            pv, pd = sum(verdade.values()), sum(det.values())
            tc += pc; td += pd; tv += pv
            print(f"{caso['arq']}: det={dict(det)} verdade={dict(verdade)} "
                  f"P={pc/max(pd,1):.2f} R={pc/max(pv,1):.2f}")
        print(f"TOTAL: P={tc/max(td,1):.2f} R={tc/max(tv,1):.2f}")
        return
    for cls in ["2001", "1000", "6007", "9008", "8000", "8001", "8017", "8016"]:
        (OUT / cls).mkdir(parents=True, exist_ok=True)
    n = 0
    for caso in casos:
        png = DS / (caso["arq"].replace(".cad", ".png"))
        if not png.exists():
            continue
        img = Image.open(png).convert("RGB")
        for i, s in enumerate(caso["simbolos"]):
            cx, cy = cad_to_screen(s["x"] + 9, s["y"] + 7)   # ~centro do símbolo
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
