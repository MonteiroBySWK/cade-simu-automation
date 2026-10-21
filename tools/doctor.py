#!/usr/bin/env python3
"""Diagnostico do ambiente: o que funciona, o que falta e como instalar. Nao abre o Wine.

Uso: python3 tools/doctor.py        (exit 1 so se faltar algo do NUCLEO)
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cade_config  # noqa: E402

VENV_PY = ROOT / "tools" / ".venv-mcp" / "bin" / "python"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
falta_nucleo = []


def linha(ok, nome, detalhe="", nucleo=True, dica=""):
    marca = "ok     " if ok else ("FALTA  " if nucleo else "opcion.")
    print(f"  [{marca}] {nome}" + (f" — {detalhe}" if detalhe else ""))
    if not ok and dica:
        print(f"            como resolver: {dica}")
    if not ok and nucleo:
        falta_nucleo.append(nome)


def pymod(m):
    r = subprocess.run([PY, "-c", f"import {m}"], capture_output=True)
    return r.returncode == 0


print("NUCLEO (obrigatorio)")
v = sys.version_info
linha(v >= (3, 10), f"Python >= 3.10", f"{v.major}.{v.minor}.{v.micro}", dica="instale Python 3.10+")
linha(bool(shutil.which("cargo")), "Rust/cargo (compila o cade_cli)", shutil.which("cargo") or "",
      dica="https://rustup.rs")
cli = ROOT / "src" / "cade_cli" / "target" / "debug" / "cade_cli"
linha(cli.is_file(), "cade_cli compilado", str(cli.relative_to(ROOT)),
      dica="cargo build --manifest-path src/cade_cli/Cargo.toml  (ou: make setup)")
for m, pkg in (("mcp", "mcp<2"), ("PIL", "pillow"), ("numpy", "numpy"), ("pytest", "pytest")):
    linha(pymod(m), f"python: {pkg}", dica="make setup  (cria tools/.venv-mcp com requirements.txt)")
print("  interpretador usado:", PY)

print("OPCIONAL — so para engenharia reversa, aprendizado e verificacao no app real")
d, e, a = cade_config.cade_dir(), cade_config.exe(), cade_config.acervo()
linha(e.is_file(), "CADe_SIMU 4.0 [BR].exe", str(e) if e.is_file() else "nao encontrado", False,
      "baixe o app (shareware) e defina CADE_DIR=<pasta> (ou CADE_EXE=<exe>)")
linha(a.is_dir(), "acervo de .cad do curso", f"{len(list(a.glob('*.cad')))} arquivos" if a.is_dir() else
      "nao encontrado (o catalogo de simbolos ja vem em tools/symbol_lib.json)", False,
      "defina CADE_ACERVO=<pasta com os .cad> (so p/ regenerar catalogo/pinos)")
for b, para in (("wine", "app_sim / validacao no app"), ("xdotool", "app_sim"), ("import", "app_sim (ImageMagick)"),
                ("uv", "setup mais rapido (fallback: python -m venv)")):
    linha(bool(shutil.which(b)), b, para, False, f"instale '{b}' pelo gerenciador de pacotes")
gh = Path("/opt/ghidra/support/analyzeHeadless")
linha(gh.exists() or bool(shutil.which("analyzeHeadless")), "Ghidra (analyzeHeadless)", "so p/ refazer a RE", False,
      "https://ghidra-sre.org (Java 21+)")

print()
if falta_nucleo:
    print("NUCLEO INCOMPLETO:", ", ".join(falta_nucleo), "\n  -> rode `make setup` e depois `make doctor`.")
    sys.exit(1)
print("Nucleo ok. Proximo passo: `make test` e `make gate`.  Integracao com agentes: docs/integracao.md")
