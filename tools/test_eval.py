"""Testes do harness tools/eval/run_eval.py e do benchmark held-out (eixo B do TODO)."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
EVAL = TOOLS / "eval"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(EVAL))
import run_eval  # noqa: E402

HELDOUT = EVAL / "heldout"
CAMPOS = {"id", "titulo", "dificuldade", "enunciado", "restricoes", "obrigatorios", "testes"}


def _heldout():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(HELDOUT.glob("*.json"))]


def test_heldout_tem_12_casos_no_formato():
    casos = _heldout()
    assert len(casos) == 12, [c.get("id") for c in casos]
    ids = [c["id"] for c in casos]
    assert len(set(ids)) == 12
    for c in casos:
        assert CAMPOS <= set(c), c["id"]
        assert "golden" not in c, c["id"]
        assert c.get("dsl", "ladder/1") == "ladder/1" or "dsl" not in c, c["id"]
        assert c["testes"], c["id"]
        assert (c.get("obrigatorios") or {}).get("classes"), c["id"]


def test_heldout_sem_solucao_no_repo():
    """Nenhum .cad/.layout.json/.ladder.json de solucao dos held-out pode existir no repo."""
    proibidos = []
    for caso in _heldout():
        base = caso["id"]
        for p in list(TOOLS.rglob(f"{base}.cad")) + list(TOOLS.rglob(f"{base}.layout.json")) \
                + list(TOOLS.rglob(f"{base}.ladder.json")):
            if ".venv" not in p.parts:
                proibidos.append(str(p))
    assert proibidos == []


def test_todos_os_casos_exclui_heldout():
    casos = run_eval.todos_os_casos()
    ids = [c["id"] for c in casos]
    assert not any(i.startswith("h_") for i in ids)
    assert len(casos) == 17, ids  # 12 rele + 5 ladder (estrela_triangulo sem golden fica "pulado")
    com_golden = [c for c in casos if c.get("golden")]
    assert len(com_golden) == 16, [c["id"] for c in com_golden]  # 11 rele + 5 ladder


def test_carregar_caso_resolve_heldout_e_ladder():
    assert run_eval.carregar_caso("h_partida_direta")["id"] == "h_partida_direta"
    assert run_eval.carregar_caso("reversao_ladder")["id"] == "reversao_ladder"
    with pytest.raises(FileNotFoundError):
        run_eval.carregar_caso("caso_que_nao_existe_xyz")


def test_ladder_golden_pontua_100():
    caso = run_eval.carregar_caso("partida_direta_ladder")
    assert run_eval.eh_ladder(caso)
    with tempfile.TemporaryDirectory() as t:
        cad = run_eval.construir_golden(caso, t)
        assert cad is not None
        r = run_eval.pontuar(cad, caso)
    assert r["total"] == 100, r
    assert all(v == 1.0 for v in r["criterios"].values()), r


def test_sem_cad_nao_e_pontuado_por_engano():
    caso = run_eval.carregar_caso("h_partida_direta")
    r = run_eval.pontuar("/tmp/cad_inexistente_xyz.cad", caso)
    assert r["total"] == 0
    assert r["criterios"]["abre"] == 0.0


def test_cad_trocado_nao_passa_em_caso_ladder():
    """Golden de outro caso nao atinge 100 (discriminacao do scorer)."""
    alvo = run_eval.carregar_caso("partida_direta_ladder")
    outro = run_eval.carregar_caso("reversao_ladder")
    with tempfile.TemporaryDirectory() as t:
        cad = run_eval.construir_golden(outro, t)
        assert cad is not None
        r = run_eval.pontuar(cad, alvo)
    assert r["total"] < 100, r
