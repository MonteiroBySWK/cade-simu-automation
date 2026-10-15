#!/usr/bin/env python3
"""Recorta templates de símbolos do screenshot do livro (1 símbolo por classe).

Uso: python3 tools/crop_templates.py livro.png  ->  out/tpl/<id>.png (8 arquivos)
Método: pixels escuros (<100) -> componentes conexos (BFS) -> 8 maiores na
metade esquerda, ordenados por X (mesma ordem do livro.cad).
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

IDS = ["2001", "1000", "8000", "8001", "6007", "9008", "8017", "8016"]

def components(mask):
    H, W = mask.shape
    seen = np.zeros_like(mask, bool)
    boxes = []
    for y in range(H):
        for x in range(W):
            if mask[y, x] and not seen[y, x]:
                q = deque([(y, x)]); seen[y, x] = True
                xs, ys = [], []
                while q:
                    cy, cx = q.popleft(); xs.append(cx); ys.append(cy)
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True; q.append((ny, nx))
                if len(xs) > 30:
                    boxes.append((min(xs), min(ys), max(xs), max(ys), len(xs)))
    return boxes

def main():
    src = Path(sys.argv[1])
    box = None
    if "--box" in sys.argv:
        box = tuple(map(int, sys.argv[sys.argv.index("--box") + 1].split(",")))
    outd = Path("out/tpl")
    outd.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    if box:
        img = img.crop(box)
    a = np.asarray(img.convert("L"))
    dark = a < 150
    boxes = []
    for b in components(dark):
        x0, y0, x1, y1, n = b
        if x0 > 10 and n > 20 and (y1 - y0) > 5:
            boxes.append(b)
    boxes.sort(key=lambda b: b[4], reverse=True)
    top = sorted(boxes[:8], key=lambda b: b[0])
    assert len(top) == 8, f"só {len(boxes)} componentes: {boxes}"
    for (x0, y0, x1, y1, _), sid in zip(top, IDS):
        m = 6
        img.crop((max(0, x0 - m), max(0, y0 - m), x1 + m, y1 + m)).save(outd / f"{sid}.png")
        print(sid, (x1 - x0, y1 - y0))

if __name__ == "__main__":
    main()
