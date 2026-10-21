#!/usr/bin/env python3
"""Tarefas do projeto, iguais em Linux/macOS/Windows (so stdlib). Nao abre o Wine.

  python scripts/dev.py setup        cargo build + venv (tools/.venv-mcp) + deps + doctor
  python scripts/dev.py doctor       o que funciona / falta / como instalar
  python scripts/dev.py test         pytest (o E2E que abre o Wine so roda com CADE_E2E=1)
  python scripts/dev.py gate         gera e valida todos os exemplos + eval golden
  python scripts/dev.py mcp-config   imprime a config do MCP p/ Claude Code e opencode (caminhos absolutos)
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import cade_config as C  # noqa: E402


def run(cmd, **kw):
    print("$", " ".join(map(str, cmd)), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, **kw)
    if r.returncode:
        sys.exit(r.returncode)


def py():
    return str(C.venv_python() or sys.executable)


def setup():
    if not shutil.which("cargo"):
        sys.exit("Falta Rust/cargo: https://rustup.rs (no Windows: rustup-init.exe, toolchain MSVC)")
    run(["cargo", "build", "--quiet", "--manifest-path", "src/cade_cli/Cargo.toml"])
    venv = ROOT / "tools" / ".venv-mcp"
    if not C.venv_python():
        if shutil.which("uv"):
            run(["uv", "venv", "-q", venv])
        else:
            run([sys.executable, "-m", "venv", venv])
    if shutil.which("uv"):
        run(["uv", "pip", "install", "-q", "--python", C.venv_python(), "-r", "requirements.txt"])
    else:
        run([C.venv_python(), "-m", "pip", "install", "-q", "-r", "requirements.txt"])
    (ROOT / "out").mkdir(exist_ok=True)
    doctor()


def doctor():
    run([py(), "tools/doctor.py"])


def test():
    run([py(), "-m", "pytest", "tools", "-q"] + sys.argv[2:])


def gate():
    (ROOT / "out").mkdir(exist_ok=True)
    ruins = 0
    for f in sorted(glob.glob(str(ROOT / "tools" / "examples" / "*.layout.json"))):
        n = Path(f).name.replace(".layout.json", "")
        r = subprocess.run([py(), "tools/build_spec.py", f, str(ROOT / "out" / f"{n}.cad")], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ult = (r.stdout.strip().splitlines() or ["?"])[-1]
        print(f"{n:34s} {ult}")
        ruins += r.returncode != 0
    run([py(), "tools/eval/run_eval.py", "--golden"])
    if ruins:
        sys.exit(f"{ruins} exemplo(s) reprovado(s)")


def mcp_config():
    server = ROOT / "scripts" / "mcp_server.py"
    exe = sys.executable
    print("# Claude Code (escopo de usuario):")
    print(f'claude mcp add cade-simu -- "{exe}" "{server}"\n')
    print("# opencode (~/.config/opencode/opencode.json, chave \"mcp\"):")
    print(json.dumps({"cade-simu": {"type": "local", "command": [exe, str(server)], "enabled": True}}, indent=2))


TAREFAS = {"setup": setup, "doctor": doctor, "test": test, "gate": gate, "mcp-config": mcp_config}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TAREFAS:
        print(__doc__)
        sys.exit(2)
    os.environ.setdefault("PYTHONUTF8", "1")
    TAREFAS[sys.argv[1]]()
