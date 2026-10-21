#!/usr/bin/env python3
import os
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
import cade_config  # noqa: E402
"""Abre um .cad no CADe_SIMU (Wine) e digita a senha 4962 sozinho — rápido.

Localiza a janela do teclado de senha (CADE SIMU 4.0, ~176x189) e clica os
dígitos + OK relativo à própria geometria da janela (robusto a posição/escala).

Uso:
  python3 tools/cade_open.py <arquivo.cad> [--display :1] [--timeout 40]
"""
import subprocess
import sys
import time
from pathlib import Path

EXE_DIR = cade_config.cade_dir()
EXE = "CADe_SIMU 4.0 [BR].exe"
# frações (x,y) do teclado dentro da janela do diálogo — calibradas em 176x189
TECLA = {
    "4": (0.375, 0.598), "9": (0.665, 0.720), "6": (0.665, 0.598), "2": (0.517, 0.481),
    "OK": (0.375, 0.841),
}
SENHA = ["4", "9", "6", "2", "OK"]


def xdo(disp, *args):
    return subprocess.run(["xdotool", *args], env={"DISPLAY": disp, **__import__("os").environ},
                          capture_output=True, text=True).stdout


def achar_teclado(disp):
    """Devolve (x, y, w, h) da janela do teclado, ou None."""
    for w in xdo(disp, "search", "--name", "CADE SIMU 4.0").split():
        g = xdo(disp, "getwindowgeometry", w)
        pos = geom = None
        for ln in g.splitlines():
            ln = ln.strip()
            if ln.startswith("Position:"):
                pos = ln.split()[1].split(",")
            elif ln.startswith("Geometry:"):
                geom = ln.split()[1].split("x")
        if pos and geom and geom[0] == "176" and geom[1] == "189":
            return int(pos[0]), int(pos[1]), int(geom[0]), int(geom[1])
    return None


def main(argv):
    cad = Path(argv[0])
    disp = ":1"
    timeout = 40
    if "--display" in argv:
        disp = argv[argv.index("--display") + 1]
    if "--timeout" in argv:
        timeout = int(argv[argv.index("--timeout") + 1])
    dst = EXE_DIR / "wv_tmp.cad"
    dst.write_bytes(cad.read_bytes())
    subprocess.Popen(["wine", EXE, "wv_tmp.cad"], cwd=str(EXE_DIR),
                     env={"DISPLAY": disp, **__import__("os").environ},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    # espera o teclado aparecer e digita
    t0 = time.time()
    while time.time() - t0 < timeout:
        geo = achar_teclado(disp)
        if geo:
            x, y, w, h = geo
            for k in SENHA:
                fx, fy = TECLA[k]
                xdo(disp, "mousemove", str(int(x + fx * w)), str(int(y + fy * h)), "click", "1")
                time.sleep(0.15)
            print(f"senha enviada em {time.time()-t0:.1f}s")
            return 0
        time.sleep(0.3)
    print("aviso: teclado de senha não apareceu (já liberado?)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
