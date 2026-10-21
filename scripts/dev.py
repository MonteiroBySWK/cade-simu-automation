#!/usr/bin/env python3
"""Tarefas do projeto, iguais em Linux/macOS/Windows (so stdlib). Nao abre o Wine.

  python scripts/dev.py setup        cargo build + venv (tools/.venv-mcp) + deps + doctor
  python scripts/dev.py doctor       o que funciona / falta / como instalar
  python scripts/dev.py test         pytest (o E2E que abre o Wine so roda com CADE_E2E=1)
  python scripts/dev.py gate         gera e valida todos os exemplos + eval golden
  python scripts/dev.py mcp-config   imprime a config do MCP p/ Claude Code e opencode (caminhos absolutos)
  python scripts/dev.py install-mcp  registra o MCP + skill no Claude Code e no opencode pelos PROPRIOS CLIs
  python scripts/dev.py uninstall-mcp  remove o registro (MCP + link da skill) dos dois
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
    run(["cargo", "build", "--quiet", "-p", "cade_cli"])
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


NOME = "cade-simu"
SKILL = ROOT / "skills" / "automacao-industrial"
OPENCODE_CFG = Path.home() / ".config" / "opencode" / "opencode.json"
SKILL_DIRS = {"claude": Path.home() / ".claude" / "skills", "opencode": Path.home() / ".config" / "opencode" / "skills"}


def _cmd_servidor():
    # Python absoluto (o mesmo que roda este script) + launcher absoluto: nao depende de PATH nem de cwd
    return [sys.executable, str(ROOT / "scripts" / "mcp_server.py")]


def _quieto(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _opencode_remover():
    """`opencode mcp` nao tem 'remove': tira a chave do JSON global (backup .bak ao lado)."""
    if not OPENCODE_CFG.is_file():
        return
    d = json.loads(OPENCODE_CFG.read_text(encoding="utf-8"))
    mcp = d.get("mcp", {})
    # opencode v2 grava em mcp.servers.<nome>; v1 usava mcp.<nome>
    alvos = [m for m in (mcp.get("servers", {}), mcp) if isinstance(m, dict) and NOME in m]
    if alvos:
        shutil.copy(OPENCODE_CFG, OPENCODE_CFG.with_suffix(".json.bak"))
        for m in alvos:
            del m[NOME]
        OPENCODE_CFG.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"opencode: '{NOME}' removido de {OPENCODE_CFG} (backup .bak)")


def _skill(link):
    for alvo, base in SKILL_DIRS.items():
        dst = base / SKILL.name
        if dst.is_symlink() or dst.exists():
            if dst.is_symlink():
                dst.unlink()
            elif not link:
                print(f"{alvo}: {dst} nao e link — deixei como esta")
                continue
        if link and base.is_dir():
            try:
                dst.symlink_to(SKILL, target_is_directory=True)
                print(f"{alvo}: skill -> {dst}")
            except OSError:   # Windows sem permissao de symlink
                shutil.copytree(SKILL, dst)
                print(f"{alvo}: skill copiada -> {dst} (sem symlink; rode de novo apos atualizar o repo)")


def uninstall_mcp():
    if shutil.which("claude"):
        for esc in ("user", "local", "project"):
            r = _quieto(["claude", "mcp", "remove", NOME, "-s", esc])
            if r.returncode == 0:
                print(f"claude: '{NOME}' removido (escopo {esc})")
    _opencode_remover()
    _skill(link=False)


def install_mcp():
    if not C.venv_python():
        sys.exit("rode `python scripts/dev.py setup` antes")
    uninstall_mcp()                              # idempotente: sempre parte do zero
    cmd = _cmd_servidor()
    if shutil.which("claude"):
        run(["claude", "mcp", "add", "-s", "user", NOME, "--", *cmd])
    else:
        print("claude CLI ausente; quando instalar: claude mcp add -s user", NOME, "--", *cmd)
    if shutil.which("opencode"):
        run(["opencode", "mcp", "add", "--global", NOME, "--", *cmd])
    else:
        print("opencode CLI ausente; quando instalar: opencode mcp add --global", NOME, "--", *cmd)
    _skill(link=True)
    print("\nConfira: `claude mcp get cade-simu` e `opencode mcp list` (devem mostrar connected).")


TAREFAS = {"install-mcp": install_mcp, "uninstall-mcp": uninstall_mcp, "setup": setup, "doctor": doctor, "test": test, "gate": gate, "mcp-config": mcp_config}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TAREFAS:
        print(__doc__)
        sys.exit(2)
    os.environ.setdefault("PYTHONUTF8", "1")
    TAREFAS[sys.argv[1]]()
