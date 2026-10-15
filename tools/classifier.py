#!/usr/bin/env python3
"""Classificador kNN leve (numpy puro) sobre crops rotulados.

Feature: máscara binária 20x20 do recorte justo da tinta + aspecto.
Treina de out/dataset/<classe>/*.png, salva out/model.npz, e serve para
classificar o componente de um screenshot (usado por detect_symbols --knn).

Uso:
  python3 tools/classifier.py train
  python3 tools/classifier.py predict <img.png>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "out" / "dataset"
MODEL = ROOT / "out" / "model.npz"
GRID = 20
CLASSES = ["0", "2001", "1000", "6007", "9008", "8000", "8001", "8017", "8016"]


def features(img_rgb, box=None):
    a = np.asarray(img_rgb.convert("L")).astype(int)
    if box:
        a = a[box[1]:box[3], box[0]:box[2]]
    m = a < 160
    ys, xs = np.where(m)
    if len(xs) == 0:
        return None
    sub = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape
    g = np.asarray(Image.fromarray((sub * 255).astype("uint8")).resize((GRID, GRID))) > 127
    v = g.astype(np.float32).ravel()
    v = np.append(v, [w / max(h, 1)])   # aspecto como feature extra
    return v


def train():
    X, y = [], []
    for ci, cls in enumerate(CLASSES):
        for f in sorted((DATA / cls).glob("*.png")):
            v = features(Image.open(f))
            if v is not None:
                X.append(v); y.append(ci)
    if not X:
        print("sem dados em out/dataset — rode mk_dataset + render_cad + label_dataset")
        return
    np.savez(MODEL, X=np.array(X), y=np.array(y), grid=GRID, classes=np.array(CLASSES))
    print(f"modelo: {len(X)} amostras, {len(CLASSES)} classes -> {MODEL}")


def load():
    d = np.load(MODEL, allow_pickle=False)
    return d["X"], d["y"], list(d["classes"])


def predict(img_rgb):
    X, y, classes = load()
    v = features(img_rgb)
    if v is None:
        return None, 0.0
    d = np.linalg.norm(X[:, :-1] - v[:-1], axis=1) + 0.5 * np.abs(X[:, -1] - v[-1])
    idx = np.argsort(d)[:5]
    votos = {}
    for i in idx:
        votos[classes[y[i]]] = votos.get(classes[y[i]], 0) + 1.0 / (d[i] + 1e-6)
    best = max(votos, key=votos.get)
    conf = votos[best] / sum(votos.values())
    return best, conf


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "train":
        train()
    elif cmd == "predict":
        cls, conf = predict(Image.open(sys.argv[2]))
        print(f"{cls} conf={conf:.2f}")
