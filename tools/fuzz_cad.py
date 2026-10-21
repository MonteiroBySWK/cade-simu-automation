#!/usr/bin/env python3
"""Fuzzing diferencial: 1 campo por vez -> abre no Wine -> registra janelas+shot.

Uso: python3 tools/fuzz_cad.py   (gera out/fuzz/caso-N.cad + roda cada um no Wine)
Requer: Wine+Xvfb+xdotool+import. Cada caso: timeout 25s.
Veredito final é visual (contact sheet) + títulos de janela gravados em out/fuzz/log.txt.
"""
import re, shutil, subprocess, time, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys as _s
from pathlib import Path as _P
_s.path.insert(0, str(_P(__file__).resolve().parent))
import cade_config  # noqa: E402
EXE = cade_config.exe()
APPDIR = EXE.parent
FZ = ROOT / "out" / "fuzz"

CASES = [
    ("00-controle", lambda d: d),
    ("01-modo-9", lambda d: d.replace("CADe_SIMU*0*3004#", "CADe_SIMU*9*3004#", 1)),
    ("02-versao-9999", lambda d: d.replace("CADe_SIMU*0*3004#", "CADe_SIMU*0*9999#", 1)),
    ("03-k1-x200", lambda d: re.sub(r"(\*2001#-K1##1#3#5#2#4#6#\*[01](?:\*[01]){6}\*)123\*(108)\*", r"\g<1>323*\g<2>*", d, count=1)),
    ("04-flag-9", lambda d: re.sub(r"(\*2001#-K1##1#3#5#2#4#6#\*)+1(\*(?:[01]\*?){7}123\*108)", r"\g<1>9\g<2>", d, count=1)),
    ("05-fio-x500", lambda d: d.replace("*141*72*141*129*", "*141*72*641*129*", 1)),
    ("06-label-ZZ", lambda d: d.replace("1000#M1#", "1000#ZZ#", 1)),
    ("07-trunca", lambda d: d[:len(d)//2]),
    ("08-net-99", lambda d: d.replace("*25*26", "*99*26", 1)),
    ("09-w-210", lambda d: re.sub(r"(\*6007#-F2##1#3#5#2#4#6##\*[01](?:\*[01]){6}\*153\*159\*0\*0\*-15\*-3\*)21(\*15)", r"\g<1>210\g<2>", d, count=1)),
]

def run_case(cad):
    name = cad.stem
    dst = APPDIR / f"fz_{name}.cad"
    shutil.copyfile(cad, dst)
    shot = FZ / f"{name}.png"
    scr = f"""wine "{EXE}" "fz_{name}.cad" & sleep 11
xdotool key Return; sleep 2
for i in 1 2 3 4 5 6 7 8; do
  if xdotool search --name "SENHA" >/dev/null 2>&1; then xdotool type 4962; xdotool key Return; sleep 4; break; fi
  sleep 2
done
sleep 3
echo "JANElAS:{name}:"
for w in $(xdotool search --name "" 2>/dev/null); do xdotool getwindowname $w 2>/dev/null; done
import -window root "{shot}"
"""
    r = subprocess.run(["xvfb-run", "-a", "sh", "-c", scr], cwd=str(APPDIR),
                       capture_output=True, text=True, timeout=120)
    return r.stdout + r.stderr

def main():
    FZ.mkdir(parents=True, exist_ok=True)
    log = []
    base = (ROOT / "corpus" / "Arranque_1.cad").read_bytes().decode('latin1')
    for name, fn in CASES:
        cad = FZ / f"{name}.cad"
        cad.write_bytes(fn(base).encode('latin1'))
        print(f"== {name}", flush=True)
        out = run_case(cad)
        wins = [l for l in out.splitlines() if l and not l.startswith(('0', 'MESA', 'X connection')) and 'fixme' not in l and 'JANElAS' not in l]
        log.append(f"{name}: {wins}")
        print("   ", wins)
    (FZ / "log.txt").write_text("\n".join(log))
    print("LOG:", FZ / "log.txt")

if __name__ == '__main__':
    main()
