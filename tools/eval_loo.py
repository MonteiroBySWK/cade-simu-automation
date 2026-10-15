#!/usr/bin/env python3
"""Avaliação honesta leave-one-case-out do detector kNN no dataset minerado.

Para cada caso do manifesto, treina com TODOS os outros e mede nesse (held-out).
Uso: python3 tools/eval_loo.py [--regras]
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import classifier as C  # noqa: E402
import detect_symbols as D  # noqa: E402
from label_dataset import load_manifest, sheet_img  # noqa: E402


def main(argv):
    casos = load_manifest()
    so_regras = "--regras" in argv
    tc = td = tv = 0
    for caso in casos:
        cid = caso["arq"][:-4]
        png = sheet_img(Path(D.ROOT) / "out" / "ds" / caso["arq"].replace(".cad", ".png"))
        if so_regras:
            dets = D.detect(png)
        else:
            X, y = [], []
            for ci, cls in enumerate(C.CLASSES):
                for f in sorted((C.DATA / cls).glob("*.png")):
                    if f.name.split("_")[0] == cid:
                        continue
                    v = C.features(Image.open(f))
                    if v is not None:
                        X.append(v); y.append(ci)
            X, y = np.array(X), np.array(y)
            C.load = lambda X=X, y=y: (X, y, C.CLASSES)
            dets = D.detect_knn(png)
        det = Counter(m["classe"] for m in dets)
        verdade = Counter(s["classe"] for s in caso["simbolos"])
        pc = sum(min(det.get(k, 0), v) for k, v in verdade.items())
        pv, pd = sum(verdade.values()), sum(det.values())
        tc += pc; td += pd; tv += pv
        print(f"{cid}: P={pc/max(pd,1):.2f} R={pc/max(pv,1):.2f}")
    modo = "REGRAS" if so_regras else "KNN (LOO)"
    print(f"{modo} TOTAL: P={tc/max(td,1):.2f} R={tc/max(tv,1):.2f}  (n={tv})")


if __name__ == "__main__":
    main(sys.argv[1:])
