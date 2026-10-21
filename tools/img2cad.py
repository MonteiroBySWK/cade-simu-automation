#!/usr/bin/env python3
"""Imagem → cade.json (inventário de símbolos) → .cad aproximado.

Detecta símbolos (kNN sobre dataset minerado) e inventaria. Para screenshots do
próprio CADe_SIMU (mesma janela/zoom do dataset) também gera um .cad colocando
uma entidade doadora por símbolo detectado (coords via transform inverso).

Uso:
  python3 tools/img2cad.py <imagem.png> -o out/from_img.json [--cad out/from_img.cad]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_symbols as D  # noqa: E402
from label_dataset import OX, OY, SX, SY  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def screen_to_cad(px, py):
    return int(round((px - OX) / SX - 9)), int(round((py - OY) / SY - 7))


def main(argv):
    if not argv:
        print(__doc__); return 2
    src = Path(argv[0])
    out_json = Path("out/from_img.json")
    out_cad = None
    if "-o" in argv:
        out_json = Path(argv[argv.index("-o") + 1])
    if "--cad" in argv:
        out_cad = Path(argv[argv.index("--cad") + 1])
    dets = D.detect_knn(src)
    inv = []
    for d in dets:
        cx, cy = screen_to_cad(d["x"], d["y"])
        inv.append({"classe": d["classe"], "nome": d["nome"], "x_img": d["x"], "y_img": d["y"],
                    "x": cx, "y": cy, "escore": d["escore"]})
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"fonte": str(src), "n": len(inv), "simbolos": inv}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(inv)} símbolos -> {out_json}")
    for s in inv:
        print(f"  {s['classe']} {s['nome']} @ cad({s['x']},{s['y']}) conf={s['escore']}")
    if out_cad:
        import mk_dataset as M
        header, protos, footer, wire = M.load_donor()
        pl = [(s["classe"], s["x"], s["y"]) for s in inv if s["classe"] in protos]
        out_cad.write_bytes(M.build(pl, header, protos, footer, wire).encode("latin1"))
        print(f".cad aprovado -> {out_cad} ({len(pl)} entidades)")


if __name__ == "__main__":
    main(sys.argv[1:])
