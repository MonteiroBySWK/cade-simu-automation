#!/usr/bin/env python3
"""Sobe o servidor MCP `cade-simu` (stdio) com o Python do venv do projeto. Portavel (so stdlib).

Use com qualquer Python 3.10+: `python scripts/mcp_server.py`. Mensagens vao para o stderr
(o stdout e o canal do protocolo MCP).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import cade_config as C  # noqa: E402

vpy = C.venv_python()
if not vpy:
    sys.exit(f"[cade-simu] venv ausente: rode `python scripts/dev.py setup` em {ROOT}")
if not C.cli_path().exists():
    subprocess.run(["cargo", "build", "--quiet", "--manifest-path", str(ROOT / "src/cade_cli/Cargo.toml")],
                   stdout=sys.stderr, check=False)
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
sys.exit(subprocess.call([str(vpy), str(ROOT / "tools" / "cade_mcp.py")], env=env))
