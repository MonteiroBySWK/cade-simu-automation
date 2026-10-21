"""Localizacao dos arquivos do CADe_SIMU (OPCIONAIS) — nada de caminho pessoal no codigo.

Ordem: variavel de ambiente -> locais comuns. Sem o app/acervo o nucleo (layout, gate, MCP,
testes) funciona; so as ferramentas de RE/Wine/aprendizado precisam deles (veja docs/DEPENDENCIAS.md).

  CADE_DIR     pasta do app (contem 'CADe_SIMU 4.0 [BR].exe' e as subpastas de exemplos)
  CADE_EXE     caminho do .exe (default: CADE_DIR/CADe_SIMU 4.0 [BR].exe)
  CADE_ACERVO  pasta com os .cad de exemplo do curso (default: dentro de CADE_DIR)
"""
import os
from pathlib import Path

EXE_NOME = "CADe_SIMU 4.0 [BR].exe"
_ACERVO_REL = Path("Atividades para Simular") / "115 arquivos CADe_SIMU" / "Arquivos .cad"
AUSENTE = Path("/__CADE_NAO_CONFIGURADO__")      # inexistente de proposito: .is_dir()/.is_file() = False


def _candidatos():
    home = Path.home()
    for base in (home / "Downloads", home, Path("/opt"), Path("/usr/share")):
        for pat in ("CADe_SIMU*", "CADe_SIMU*/CADe_SIMU*"):
            for p in sorted(base.glob(pat)) if base.is_dir() else []:
                yield p


def cade_dir():
    if os.environ.get("CADE_DIR"):
        return Path(os.environ["CADE_DIR"])
    for p in _candidatos():
        if (p / EXE_NOME).is_file():
            return p
    return AUSENTE


def exe():
    if os.environ.get("CADE_EXE"):
        return Path(os.environ["CADE_EXE"])
    return cade_dir() / EXE_NOME


def acervo():
    if os.environ.get("CADE_ACERVO"):
        return Path(os.environ["CADE_ACERVO"])
    return cade_dir() / _ACERVO_REL


def exemplos_imagem():
    return cade_dir() / "Exemplos (diagramas)"


def exigir(path, o_que, var):
    """Para scripts de dev: erro claro (em vez de FileNotFoundError cripto) se faltar o recurso."""
    if not Path(path).exists():
        raise SystemExit(f"[cade] {o_que} nao encontrado. Defina {var} (veja docs/DEPENDENCIAS.md). "
                         f"Procurado em: {path}")
    return Path(path)
