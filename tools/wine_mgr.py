#!/usr/bin/env python3
"""Gerencia o CADe_SIMU no Wine: subir, desbloquear, maximizar, screenshot, matar.

Evita o footgun clássico (pkill casando a própria linha de comando): mata por PID,
excluindo o próprio processo e ancestrais.

Uso:
  python3 tools/wine_mgr.py up [arq.cad] [--display :1]   # abre (+senha sozinha)
  python3 tools/wine_mgr.py status                        # janelas + processos
  python3 tools/wine_mgr.py shot [saida.png]              # screenshot da janela
  python3 tools/wine_mgr.py max                           # maximiza a filha (duplo-clique)
  python3 tools/wine_mgr.py ws 10                       # move p/ o workspace 10 (Hyprland)
  python3 tools/wine_mgr.py down                          # mata tudo com segurança (por PID)
  python3 tools/wine_mgr.py logs                          # mostra os últimos logs

Logs em logs/ (NÃO versionado).
"""
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGDIR = ROOT / "logs"
EXE_DIR = Path(os.environ.get("CADE_DIR", "/home/monteiro/Downloads/CADe_SIMU 4.0 [BR]/CADe_SIMU 4.0 [BR]"))
EXE = "CADe_SIMU 4.0 [BR].exe"
# frações (x,y) do teclado 4962+OK dentro da janela do diálogo (176x189)
TECLAS = {"4": (0.375, 0.598), "9": (0.665, 0.720), "6": (0.665, 0.598),
          "2": (0.517, 0.481), "OK": (0.375, 0.841)}
DISP = os.environ.get("DISPLAY", ":1")


def log(msg):
    LOGDIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOGDIR / "wine_mgr.log", "a") as f:
        f.write(line + "\n")


def xdo(*args, disp=None):
    env = dict(os.environ, DISPLAY=disp or DISP)
    r = subprocess.run(["xdotool", *args], env=env, capture_output=True, text=True)
    return r.stdout


def pids_cade():
    """PIDs rodando o EXE (exclui este processo e ancestrais — sem footgun)."""
    forbidden = {os.getpid(), os.getppid()}
    try:
        forbidden.add(os.getppid())
    except Exception:
        pass
    out = []
    for p in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            pid = int(p.parent.name)
        except ValueError:
            continue
        if pid in forbidden:
            continue
        try:
            cmd = p.read_bytes().decode("latin1", "replace")
        except Exception:
            continue
        if "CADe_SIMU 4.0 [BR].exe" in cmd and "wine_mgr" not in cmd and "xdotool" not in cmd:
            out.append(pid)
    return out


def cmd_down():
    for pid in pids_cade():
        try:
            os.kill(pid, 15)
            log(f"SIGTERM {pid}")
        except ProcessLookupError:
            pass
    time.sleep(2)
    for pid in pids_cade():
        try:
            os.kill(pid, 9)
            log(f"SIGKILL {pid}")
        except ProcessLookupError:
            pass
    log("down: nenhum processo do CADe restante" if not pids_cade() else "down: RESTAM processos!")


def janela_principal(disp):
    wins = xdo("search", "--name", "CADe_SIMU", disp=disp).split()
    return wins[-1].strip() if wins else None


def cmd_up(cad=None, disp=None):
    disp = disp or DISP
    if cad:
        dst = EXE_DIR / "wv_tmp.cad"
        dst.write_bytes(Path(cad).read_bytes())
        arg = "wv_tmp.cad"
    else:
        arg = None
    out = open(LOGDIR / "wine_app.log", "ab")
    cmd = ["wine", EXE] + ([arg] if arg else [])
    subprocess.Popen(cmd, cwd=str(EXE_DIR), env=dict(os.environ, DISPLAY=disp),
                     stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    log(f"up: {arg or '(sem arquivo)'} no display {disp}")
    t0 = time.time()
    while time.time() - t0 < 45:
        wins = xdo("search", "--name", "CADE SIMU 4.0", disp=disp).split()
        for w in wins:
            g = xdo("getwindowgeometry", w, disp=disp)
            pos = geo = None
            for ln in g.splitlines():
                s = ln.strip()
                if s.startswith("Position:"):
                    pos = s.split()[1].split(",")
                elif s.startswith("Geometry:"):
                    geo = s.split()[1].split("x")
            if pos and geo == ["176", "189"]:
                x, y = int(pos[0]), int(pos[1])
                for k in ["4", "9", "6", "2", "OK"]:
                    fx, fy = TECLAS[k]
                    xdo("mousemove", str(int(x + fx * 176)), str(int(y + fy * 189)),
                        "click", "1", disp=disp)
                    time.sleep(0.15)
                log(f"senha enviada em {time.time()-t0:.1f}s")
                return 0
        time.sleep(0.4)
    log("teclado de senha não apareceu (já liberado?)")
    return 0


def cmd_status(disp=None):
    disp = disp or DISP
    print("processos:", pids_cade() or "nenhum")
    for w in xdo("search", "--name", "", disp=disp).split():
        n = xdo("getwindowname", w, disp=disp).strip()
        if n and "IME" not in n:
            print(f"  [{w}] {n}")


def cmd_shot(out=None, disp=None):
    disp = disp or DISP
    w = janela_principal(disp)
    if not w:
        print("sem janela do CADe"); return 1
    out = out or str(LOGDIR / f"shot-{datetime.now():%H%M%S}.png")
    subprocess.run(["import", "-window", w, out], env=dict(os.environ, DISPLAY=disp))
    print(out)


def cmd_max(disp=None):
    disp = disp or DISP
    w = janela_principal(disp)
    if not w:
        print("sem janela do CADe"); return 1
    # duplo-clique na barra da filha = maximiza (botão □ não responde ao xdotool)
    g = xdo("getwindowgeometry", w, disp=disp)
    px = py = None
    for ln in g.splitlines():
        s = ln.strip()
        if s.startswith("Position:"):
            px, py = (int(v) for v in s.split()[1].split(","))
            break
    xdo("mousemove", str(px + 600), str(py + 85), "click", "--repeat", "2", "--delay", "150", "1", disp=disp)
    time.sleep(2)
    print("max: duplo-clique enviado")


def cmd_ws(ws, disp=None):
    """Move a janela do CADe para o workspace N (Hyprland, via socket Lua)."""
    import socket
    w = janela_principal(disp or DISP)
    if not w:
        print("sem janela do CADe"); return 1
    addr = None
    try:
        import json as _j
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(os.path.expandvars("$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock"))
        s.sendall(b"j/clients")
        data = b""
        while True:
            ch = s.recv(65536)
            if not ch:
                break
            data += ch
        s.close()
        for c in _j.loads(data.decode()):
            if "CADe_SIMU" in c.get("title", ""):
                addr = c["address"]; break
    except Exception as e:
        print(f"ws: falha ao listar ({e})"); return 1
    if not addr:
        print("ws: janela não achada no compositor"); return 1
    try:
        # o move age na janela focada: garante o foco antes
        xdo("windowactivate", w, disp=disp or DISP)
        time.sleep(0.5)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(os.path.expandvars("$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock"))
        s.sendall(f"dispatch hl.dsp.window.move{{workspace={ws}}}".encode())
        resp = s.recv(256).decode(errors="replace")
        s.close()
        print(f"ws {ws}: {resp.strip()}")
    except Exception as e:
        print(f"ws: falha ({e})"); return 1
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 2
    cmd, rest = argv[0], argv[1:]
    disp = ":1"
    if "--display" in rest:
        disp = rest[rest.index("--display") + 1]
    if cmd == "up":
        cad = next((a for a in rest if not a.startswith("--")), None)
        return cmd_up(cad, disp)
    if cmd == "down":
        return cmd_down() or 0
    if cmd == "status":
        return cmd_status(disp) or 0
    if cmd == "shot":
        out = next((a for a in rest if not a.startswith("--")), None)
        return cmd_shot(out, disp)
    if cmd == "max":
        return cmd_max(disp)
    if cmd == "ws":
        ws = next((a for a in rest if not a.startswith("--")), "10")
        return cmd_ws(ws, disp)
    if cmd == "logs":
        for f in sorted(LOGDIR.glob("*.log")):
            print(f"--- {f.name}"); print(open(f).read()[-1500:])
        return 0
    print(f"comando desconhecido: {cmd}"); return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
